from django.core.management.base import BaseCommand, CommandError

from apps.warehouse.models import MCPServerConfig
from apps.warehouse.services.product_images import backfill_product_images


class Command(BaseCommand):
    help = "补齐商品图片（只更新图片字段，不改变经营指标）"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="仅统计，不写入数据库")
        parser.add_argument("--organization", default="", help="精确限定企业组织")
        parser.add_argument("--config-id", type=int, help="按已配置的数据源确定组织范围")
        parser.add_argument("--source", choices=("", "mcp", "monthly", "export"), default="",
                            help="按事实来源筛选；默认处理全部历史事实和主档案")

    def handle(self, *args, **options):
        organization = options.get("organization", "").strip() or None
        config_id = options.get("config_id")
        if config_id:
            candidates = MCPServerConfig.objects.filter(pk=config_id).values_list("organization_name", flat=True)
            candidates = [item.strip() for item in candidates if item and item.strip()]
            if not candidates:
                raise CommandError(f"找不到配置 {config_id} 或配置尚未选择组织")
            if organization and organization not in candidates:
                raise CommandError("--organization 与 --config-id 的组织范围不一致")
            organization = organization or candidates[0]
        stats = backfill_product_images(
            organization=organization,
            source=options.get("source") or None,
            dry_run=bool(options.get("dry_run")),
        )
        mode = "预览" if options.get("dry_run") else "完成"
        self.stdout.write(
            f"商品图片同步{mode}：扫描 {stats['total']}，成功 {stats['success']}，缺失 {stats['missing']}，"
            f"更新 {stats['updated']}（facts {stats['facts_updated']}，catalog {stats['catalog_updated']}）"
        )
