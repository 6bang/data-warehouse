from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.warehouse.models import DataSyncJob, MCPServerConfig
from apps.warehouse.services.mcp_sync import is_sync_due, sync_month


class Command(BaseCommand):
    help = "执行到期的经营数据接口自动同步"

    def add_arguments(self, parser):
        parser.add_argument("--month", default="")
        parser.add_argument("--force", action="store_true")
        parser.add_argument("--config-id", type=int)

    def handle(self, *args, **options):
        now = timezone.localtime()
        queryset = MCPServerConfig.objects.filter(
            enabled=True,
            data_sync_enabled=True,
            schedule_enabled=True,
        ).order_by("id")
        if options["config_id"]:
            queryset = queryset.filter(pk=options["config_id"])

        succeeded = failed = skipped = 0
        for config in queryset:
            if not options["force"] and not options["month"] and not is_sync_due(config, now):
                skipped += 1
                continue
            months = [options["month"] or now.strftime("%Y-%m")]
            if not options["month"] and now.day <= 3:
                previous_month = (now.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
                already_backfilled_today = DataSyncJob.objects.filter(
                    organization=config.organization_name,
                    source_system="mcp_sync",
                    period=previous_month,
                    status=DataSyncJob.Status.SUCCEEDED,
                    finished_at__date=now.date(),
                ).exists()
                if not already_backfilled_today:
                    months.append(previous_month)

            for month in months:
                try:
                    job = sync_month(config, month)
                    succeeded += 1
                    self.stdout.write(self.style.SUCCESS(
                        f"{config.name} {config.organization_name} {month}: {job.success_rows} 行"
                    ))
                except Exception as exc:
                    failed += 1
                    self.stderr.write(self.style.ERROR(f"{config.name} {month}: {exc}"))
                    break

        self.stdout.write(f"经营数据接口自动同步结束：成功 {succeeded}，失败 {failed}，未到期 {skipped}")
