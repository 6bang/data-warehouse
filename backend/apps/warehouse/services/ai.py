import json
from datetime import date as date_type
from urllib import error, request

from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder

from apps.warehouse.models import AIAnalysisRun, AbnormalRecord, ProductCatalog
from apps.warehouse.services.dashboard import month_bounds, monthly_dashboard
from apps.warehouse.services.integrations import ai_provider_credentials, record_integration_event
from apps.warehouse.services.mcp import build_agent_mcp_tools, execute_agent_mcp_tool
from apps.warehouse.models import ProductData


def _rule_output(context):
    abnormal = context.get("abnormal", [])
    if not abnormal:
        return {
            "problems": ["当前范围未检测到达到阈值的经营异常"],
            "reasons": ["核心指标相对上一有效日波动未超过 20%"],
            "suggestions": ["保持观察，并补齐利润与库存数据以提高诊断完整度"],
            "actions": [],
        }
    problems, reasons, suggestions, actions = [], [], [], []
    for item in abnormal[:8]:
        problems.append(item["description"])
        reasons.append(item.get("ai_analysis") or f"{item['metric']} 相对基线出现显著变化")
        suggestions.append(item.get("suggestion") or "核对数据并安排负责人处理")
        actions.append({
            "task_name": f"处理{item['description'][:60]}",
            "product_id": item.get("product_id", ""),
            "product_image_url": item.get("product_image_url", ""),
            "problem": item["description"],
            "suggestion": item.get("suggestion", ""),
            "abnormal_record_id": item["id"],
        })
    return {"problems": problems, "reasons": reasons, "suggestions": suggestions, "actions": actions}


def _configured_provider():
    credentials = ai_provider_credentials()
    if credentials:
        return credentials
    if settings.AI_API_BASE_URL and settings.AI_API_KEY:
        return {
            "config": None,
            "base_url": settings.AI_API_BASE_URL.rstrip("/"),
            "api_key": settings.AI_API_KEY,
            "model": settings.AI_MODEL,
            "provider": "environment",
        }
    return None


def _parse_model_json(content):
    content = (content or "").strip().removeprefix("```json").removesuffix("```").strip()
    return json.loads(content)


def _model_output(context, question, credentials, ai_run):
    endpoint = credentials["base_url"] + "/chat/completions"
    prompt = (
        "你是电商经营分析Agent。只能依据给定JSON数据分析，输出严格JSON，字段为"
        "problems/reasons/suggestions/actions；前三项是字符串数组，actions是对象数组，"
        "每项包含task_name、product_id、problem、suggestion、abnormal_record_id。"
        "如有已授权的MCP查询工具，可先调用工具补充事实；只能调用系统提供的工具。"
        f"\n用户问题：{question or '分析经营异常并给出行动建议'}\n数据：{json.dumps(context, ensure_ascii=False, default=str)}"
    )
    messages = [{"role": "user", "content": prompt}]
    tools, mapping = build_agent_mcp_tools()
    combined_usage = {"prompt_tokens": 0, "completion_tokens": 0}
    for _ in range(4):
        body = {"model": credentials["model"], "messages": messages, "stream": False}
        if tools:
            body.update({"tools": tools, "tool_choice": "auto"})
        else:
            body["response_format"] = {"type": "json_object"}
        req = request.Request(
            endpoint,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {credentials['api_key']}"},
        )
        try:
            with request.urlopen(req, timeout=60) as response:
                payload = json.loads(response.read())
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise ValueError(f"模型接口返回 HTTP {exc.code}: {detail}") from exc
        usage = payload.get("usage", {})
        combined_usage["prompt_tokens"] += usage.get("prompt_tokens", 0)
        combined_usage["completion_tokens"] += usage.get("completion_tokens", 0)
        message = payload["choices"][0]["message"]
        tool_calls = message.get("tool_calls") or []
        if not tool_calls:
            return _parse_model_json(message.get("content")), combined_usage
        messages.append(message)
        for tool_call in tool_calls:
            function = tool_call.get("function", {})
            arguments = json.loads(function.get("arguments") or "{}")
            result = execute_agent_mcp_tool(function.get("name", ""), arguments, mapping, ai_run=ai_run)
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.get("id"),
                "content": json.dumps(result, ensure_ascii=False, default=str)[:30000],
            })
    raise ValueError("智能体 MCP 查询次数超过安全上限")


def run_analysis(user, day=None, month="", shop="", product_id="", question=""):
    month = month or (day.strftime("%Y-%m") if day else "")
    summary = monthly_dashboard(month, shop)
    month = summary.get("month") or month
    if month:
        start, end = month_bounds(month)
        data_qs = ProductData.objects.filter(date__gte=start, date__lt=end)
        if shop:
            data_qs = data_qs.filter(shop=shop)
        actual_day = data_qs.order_by("-date").values_list("date", flat=True).first()
        abnormal_qs = AbnormalRecord.objects.filter(date__gte=start, date__lt=end).exclude(status=AbnormalRecord.Status.RESOLVED)
    else:
        actual_day = None
        abnormal_qs = AbnormalRecord.objects.none()
    if shop:
        abnormal_qs = abnormal_qs.filter(shop=shop)
    if product_id:
        abnormal_qs = abnormal_qs.filter(product_id=product_id)
    abnormal = list(abnormal_qs.values("id", "type", "metric", "level", "product_id", "shop", "description", "current_value", "baseline_value", "change_rate", "ai_analysis", "suggestion")[:30])
    for item in abnormal:
        item["product_image_url"] = ProductCatalog.objects.filter(
            shop=item.get("shop", ""), product_id=item.get("product_id", "")
        ).exclude(product_image_url="").values_list("product_image_url", flat=True).first() or ""
    context = {"dashboard": summary, "abnormal": abnormal, "scope": {"month": month, "date": actual_day, "shop": shop, "product_id": product_id}}
    context = json.loads(json.dumps(context, cls=DjangoJSONEncoder))
    provider, model, usage = "rules", "", {}
    output = _rule_output(context)
    run = AIAnalysisRun.objects.create(
        requester=user,
        date=actual_day if isinstance(actual_day, date_type) else actual_day,
        month=month,
        shop=shop,
        product_id=product_id,
        question=question,
        input_context=context,
        output=output,
        provider=provider,
    )
    credentials = None
    try:
        credentials = _configured_provider()
    except Exception as exc:
        output["provider_notice"] = f"模型配置不可用，已使用规则分析：{exc}"
        provider = "rules_fallback"
    if credentials and credentials["api_key"]:
        try:
            output, usage = _model_output(context, question, credentials, run)
            provider = "openai_compatible"
            model = credentials["model"]
            record_integration_event("ai", credentials["config"], "analysis", actor=user, success=True, detail={"model": model}, ai_run=run)
        except Exception as exc:
            output["provider_notice"] = f"模型调用失败，已使用规则分析：{exc}"
            provider = "rules_fallback"
            record_integration_event("ai", credentials["config"], "analysis", actor=user, success=False, error_message=str(exc), ai_run=run)
    run.output = output
    run.provider = provider
    run.model = model if provider == "openai_compatible" else ""
    run.prompt_tokens = usage.get("prompt_tokens", 0)
    run.completion_tokens = usage.get("completion_tokens", 0)
    run.save(update_fields=["output", "provider", "model", "prompt_tokens", "completion_tokens", "updated_at"])
    return run
