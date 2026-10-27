from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.warehouse.models import MonthlyProductFact
from apps.warehouse.services.strategies import run_enabled_strategies


class Command(BaseCommand):
    help = "运行已启用的运营策略规则并生成月度商品预警"

    def add_arguments(self, parser):
        parser.add_argument("--month", help="指定月份 YYYY-MM；默认使用最新数据月份")
        parser.add_argument("--force", action="store_true", help="忽略配置小时，运行全部已启用定时策略")

    def handle(self, *args, **options):
        month = options.get("month") or MonthlyProductFact.objects.order_by("-month").values_list("month", flat=True).first()
        if not month:
            self.stdout.write("没有可执行的月度商品数据")
            return
        due_hour = None if options["force"] else timezone.localtime().hour
        results = run_enabled_strategies(month, due_hour=due_hour)
        alerts = sum(item["alerts"] for item in results)
        self.stdout.write(self.style.SUCCESS(f"{month} 完成 {len(results)} 个策略，生成/刷新 {alerts} 条预警"))
