# 接入自己的 MCP 数据服务

## 两个方向不要混淆

1. **外部数据 → 数据云仓**：在配置中心填写上游MCP地址和授权，云仓查询被授权的数据。
2. **数据云仓 → 开发/业务智能体**：云仓签发独立的访问凭据，经审批后，让智能体只读取云仓内被授权的数据。

上游授权密钥绝不能作为云仓智能体密钥转发。演示页中的所有密钥样例无效，配置保存、同步、AI都仅模拟，不会连外部。

## A. 本地连接与验证

1. 启动完整本地系统，管理员登录，进入“配置中心 → MCP 服务”。
2. 新建连接，填自己的服务名称、Streamable HTTP端点，选择Bearer认证并填自己的Token。不要填尖括号；界面可以接受原始Token或带`Bearer `前缀的值。
3. 启用连接，测试/发现工具。确认工具清单成功，再以只读店铺查询验证授权范围。协议层支持JSON-RPC与SSE响应，不代表适配了所有服务的业务结构。
4. 如果需要采集经营数据，填写自己的企业名称，启用该连接的数据同步功能。先选择单店、单月做一次小范围同步，核对金额、订单、日期/时区、退款和利润口径。
5. 只有确认正确后，才启用定时同步。同步可能替换同组织/店铺/月份的数据快照，不要拿未知测试数据覆盖已有业务。

默认没有预填真实供应商地址。示例 `https://example.invalid/mcp` 有意不可访问，必须换成你的地址。公网服务应使用HTTPS。连接到你控制的本机HTTP服务时，需明确打开该连接的`allow_private_network`，不能为了省事给未知服务器放开内网访问。

核心配置字段（后台接口`POST /api/v1/configuration/mcp-servers/`）：

```json
{
  "name": "我的数据服务",
  "endpoint_url": "https://example.invalid/mcp",
  "auth_type": "bearer",
  "auth_token": "在本地填写，不提交仓库",
  "enabled": true,
  "data_sync_enabled": true,
  "organization_name": "我的企业"
}
```

这只是配置结构，不能直接执行以上示例连通服务。身份凭据由后台使用本地独立加密密钥加密；请备份自己的加密密钥，不导入其他安装的加密数据库。

## B. 哪些 MCP 可以直接生成看板

当前适配器的业务协议如下，代码以`backend/apps/warehouse/services/mcp_sync.py`及`realtime.py`为准。适配器不内置任何供应商账号或数据。

| 工具 | 业务用途 | 预期核心返回 |
| --- | --- | --- |
| `data_insight_list_stores` | 授权店铺 | `{stores:[{store_id,store_name,platform_type}]}` |
| `data_insight_query` | 月度商品/店铺数据 | `{items:[...],has_next:boolean}` |
| `data_insight_compare` | 今日与昨日指标 | `{metrics:{paid_amount:{current,compare,change_rate},...}}` |
| `data_insight_daily_report` | 实时商品榜单 | `{top_items:{items:[...]}}` |

工具数据从MCP `structuredContent` 或 `content` 中JSON文本取出；错误响应不能被当成成功同步。`data_insight_query`的月度调用参数包括：

```json
{
  "dataset": "item",
  "granularity": "summary",
  "date_from": "2025-01-01",
  "date_to": "2025-01-31",
  "event_type": "PAID",
  "fields": ["item_id", "store_id", "store_name", "platform_type", "title", "paid_amount", "paid_units", "trade_count"],
  "page": 1,
  "page_size": 1000,
  "filters": {"store_id": ["自己的店铺标识"]}
}
```

完整请求字段以代码`SYNC_FIELDS`为准；示例只展示结构。记录至少要有稳定的`item_id`和`store_id`，建议完整返回店名、平台、标题、成交金额、销量、订单数；其他指标缺失应保留缺失语义，不能从无关字段编造。实时店铺查询使用`dataset:'shop'`。

仅支持任意工具发现/只读查询，并不意味着能直接导入其结果。不同工具名、分页、金额单位或字段结构，需要新增独立适配器及测试，不能简单更换URL后假称兼容。

**小时销售趋势与商品档案额外字段**：上述通用月报/实时工具不保证提供逐小时销售、商品创建时间、货号及图片。本模板没有内置小时级数据来源，小时趋势在接入前显示不可用。如果你的MCP提供这些字段，可以扩展适配器（小时趋势入口在`realtime.py`的`_hourly_trend`）并补测试；没有实测前不可承诺自动获得。

## C. 每5分钟轮询（用户选择后启用）

先完成一次手动同步，再配置连接的`enabled=true`、`data_sync_enabled=true`、`schedule_enabled=true`和`schedule_interval_minutes=5`。执行器为：

```bash
# 项目backend目录；使用本项目虚拟环境中的Python
python manage.py sync_mcp_data
```

它只处理已启用且到期的同步配置，不会凭空创建连接。Linux可由用户创建每5分钟调度，并加文件锁避免重入；macOS用launchd，Windows用任务计划程序。`dev.py`不会自动安装系统级任务。

采用Docker时，调度命令为在项目目录运行`docker compose exec -T backend python manage.py sync_mcp_data`。请自行指定项目目录、锁路径和私有日志目录，不将日志上传仓库。电脑休眠/关机后本地任务不会执行；需全天运行则另行部署常驻服务。

## D. 让 Codex / Accio 读取本地云仓

1. 使用配置中心的智能体密钥/接入包功能，新建一个明确命名的智能体申请。
2. 管理员审核，设置只读工具白名单、可访问店铺、字段和有效期；未批准的Token不可使用。
3. 客户端MCP端点为你自己的`http://127.0.0.1:8000/api/v1/mcp/business/`（Docker可用本机8080端口），请求头`Authorization: Bearer <在客户端本地安全填写的云仓访问凭据>`。括号只是说明，不要复制为Token。
4. 本系统提供`list_business_dimensions`、`query_monthly_metrics`、`query_realtime_metrics`三个只读工具。先列工具，再执行一个已授权范围的小查询核对结果。

云端智能体通常不能访问你电脑的`127.0.0.1`；需要客户端支持本地MCP连接，或另行部署安全可达的服务。不要直接将开发服务器或含密钥的URL暴露到公网。工具能否在Codex/Accio中直接添加，取决于对应客户端的MCP支持与权限。
