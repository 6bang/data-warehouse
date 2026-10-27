import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.warehouse.models import ImportBatch, ProductData
from apps.warehouse.services.anomalies import detect_anomalies
from apps.warehouse.services.importers import FeishuBaseAdapter, import_rows


DATA_TYPES = ("shop", "product", "paid")


class Command(BaseCommand):
    help = "Synchronize the configured monthly product, paid, and shop-summary tables from Feishu Base."

    def add_arguments(self, parser):
        parser.add_argument("--shop", required=True, help="Your shop name")
        parser.add_argument("--config", required=True, help="JSON array of {type, month, url}; every URL must identify your own Base table")
        parser.add_argument("--month", action="append", dest="months", help="YYYY-MM; may be supplied more than once")
        parser.add_argument("--type", action="append", dest="types", choices=DATA_TYPES, help="data type; may be supplied more than once")
        parser.add_argument("--detect", action="store_true", help="detect anomalies on the last imported day of each month")

    def handle(self, *args, **options):
        shop = options["shop"]
        months = set(options["months"] or [])
        data_types = options["types"] or ["shop", "product", "paid"]
        try:
            entries = json.loads(Path(options["config"]).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise CommandError("Cannot read the supplied JSON table configuration.") from exc
        if not isinstance(entries, list) or not entries:
            raise CommandError("Configuration must be a nonempty JSON array of {type, month, url}.")
        tables = {key: [] for key in DATA_TYPES}
        for entry in entries:
            if not isinstance(entry, dict) or entry.get("type") not in DATA_TYPES or not entry.get("month") or not entry.get("url"):
                raise CommandError("Each entry requires type (shop/product/paid), month (YYYY-MM or all), and your own table URL.")
            tables[entry["type"]].append((entry["month"], entry["url"]))
        adapter = FeishuBaseAdapter()
        imported_months = set()
        totals = {"success": 0, "failed": 0}

        for data_type in data_types:
            for month, url in tables[data_type]:
                if months and month != "all" and month not in months:
                    continue
                self.stdout.write(f"[{data_type}] {month}: reading configured table")
                batch = ImportBatch.objects.create(
                    source=ImportBatch.Source.FEISHU,
                    data_type=data_type,
                    source_name=url,
                    shop=shop,
                )
                try:
                    rows, metadata = adapter.read(url)
                    batch.source_name = f"{url}#{metadata['table_id']}"
                    batch.save(update_fields=["source_name", "updated_at"])
                    import_rows(rows, batch)
                except Exception as exc:
                    batch.status = ImportBatch.Status.FAILED
                    batch.error_summary = [{"message": str(exc)}]
                    batch.save(update_fields=["status", "error_summary", "updated_at"])
                    raise CommandError(f"{data_type} {month} sync failed: {exc}") from exc

                totals["success"] += batch.success_rows
                totals["failed"] += batch.failed_rows
                if month != "all":
                    imported_months.add(month)
                self.stdout.write(self.style.SUCCESS(
                    f"[{data_type}] {month}: {batch.success_rows}/{batch.total_rows} rows imported"
                ))

        if options["detect"]:
            for month in sorted(imported_months):
                year, number = map(int, month.split("-"))
                last_day = (ProductData.objects.filter(shop=shop, date__year=year, date__month=number)
                            .order_by("-date").values_list("date", flat=True).first())
                if last_day:
                    count = len(detect_anomalies(last_day, shop))
                    self.stdout.write(f"[anomaly] {month} {last_day}: {count} records")

        self.stdout.write(self.style.SUCCESS(
            f"Feishu monthly sync complete: {totals['success']} succeeded, {totals['failed']} failed"
        ))

