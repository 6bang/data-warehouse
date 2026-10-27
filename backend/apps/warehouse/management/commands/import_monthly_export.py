from django.core.management.base import BaseCommand, CommandError

from apps.warehouse.services.monthly_export import import_monthly_product_export


class Command(BaseCommand):
    help = "导入兼容字段格式的商品月度 Excel 到独立月度事实表"

    def add_arguments(self, parser):
        parser.add_argument("--file", required=True)
        parser.add_argument("--organization", required=True)
        parser.add_argument("--month", required=True)

    def handle(self, *args, **options):
        try:
            job = import_monthly_product_export(options["file"], options["organization"], options["month"])
        except Exception as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS(
            f"同步完成 job={job.id} rows={job.success_rows}/{job.total_rows} summary={job.summary}"
        ))
