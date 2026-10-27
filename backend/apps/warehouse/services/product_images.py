"""Image-only helpers. Never join products on product_id without their full scope."""

import re
from urllib.parse import urlsplit

from django.db import transaction

from apps.warehouse.models import MonthlyProductFact, ProductCatalog


IMAGE_FIELDS = ("product_image_url", "pic_url", "vitem.pic_url", "商品图片URL", "商品图片", "图片")
ATTACHMENT_FIELDS = ("attachments", "images", "image", "url", "download_url", "src", "thumb_url")
IDENTITY_FIELDS = ("organization", "platform", "shop", "product_id")


def normalize_product_image_url(value):
    """Accept bounded HTTP(S) URLs only; protocol-relative CDN links become HTTPS."""
    if not isinstance(value, str):
        return ""
    value = value.strip()
    if value.startswith("//"):
        value = "https:" + value
    if not value or len(value) > 1000 or re.search(r"[\s<>\\\x00-\x1f\x7f]", value):
        return ""
    try:
        parsed = urlsplit(value)
        if parsed.scheme.lower() not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
            return ""
        # Accessing port detects malformed/non-numeric/out-of-range ports.
        parsed.port
    except ValueError:
        return ""
    return value


def _attachment_image(value, depth=0):
    if depth > 5:
        return ""
    if isinstance(value, str):
        return normalize_product_image_url(value)
    if isinstance(value, (list, tuple)):
        return next((url for item in value if (url := _attachment_image(item, depth + 1))), "")
    if isinstance(value, dict):
        for field in (*IMAGE_FIELDS, "url", "download_url", "src", "thumb_url", "attachments", "images", "value"):
            url = _attachment_image(value.get(field), depth + 1)
            if url:
                return url
    return ""


def _get(row, field, default=None):
    return row.get(field, default) if isinstance(row, dict) else getattr(row, field, default)


def resolve_product_image(row):
    """Read known source fields / attachment values, never arbitrary unrelated URLs."""
    if row is None:
        return ""
    for field in IMAGE_FIELDS:
        url = _attachment_image(_get(row, field))
        if url:
            return url
    for field in ATTACHMENT_FIELDS:
        url = _attachment_image(_get(row, field))
        if url:
            return url
    vitem = _get(row, "vitem")
    if isinstance(vitem, dict):
        url = _attachment_image(vitem.get("pic_url"))
        if url:
            return url
    raw = _get(row, "raw_payload")
    if isinstance(raw, dict) and raw is not row:
        # Only one raw-payload layer; malformed recursive objects cannot recurse forever.
        return resolve_product_image({key: value for key, value in raw.items() if key != "raw_payload"})
    return ""


def product_image_identity(row, organization=None):
    values = tuple(str(_get(row, key) or (organization if key == "organization" else "") or "").strip() for key in IDENTITY_FIELDS)
    return values if all(values) else None


def _image_candidates(identities):
    """Two queries per bounded batch; exact four-part keys are checked after loading."""
    candidates = {}
    identities = {key for key in identities if key}
    if not identities:
        return candidates
    scope = {
        "organization__in": {key[0] for key in identities},
        "product_id__in": {key[3] for key in identities},
    }
    # A valid catalog picture is the freshest retained master picture. Missing
    # catalog pictures fall back to the newest valid historical month, not row ID.
    for model, ordering, period_field in ((ProductCatalog, ("-last_seen_month", "-updated_at", "-pk"), "last_seen_month"),
                                          (MonthlyProductFact, ("-month", "-updated_at", "-pk"), "month")):
        fields = (*IDENTITY_FIELDS, "product_image_url", "raw_payload", "pk", "updated_at", period_field)
        for row in model.objects.filter(**scope).order_by(*ordering).values(*fields).iterator(chunk_size=500):
            key = product_image_identity(row)
            if key in identities:
                url = resolve_product_image(row)
                rank = (str(row.get(period_field) or ""), str(row.get("updated_at") or ""), str(row.get("pk") or ""))
                if url and (key not in candidates or rank > candidates[key][0]):
                    candidates[key] = (rank, url)
    return {key: value[1] for key, value in candidates.items()}


def enrich_product_images(rows, organization=None):
    """Mutate/return rows, normalizing images and filling gaps from exact-scope DB history.

    Supports dicts and model instances. No DB writes; at most two reads per 400
    input rows. Rows missing any identity component are never joined to history.
    """
    rows = list(rows)
    for start in range(0, len(rows), 400):
        batch = rows[start:start + 400]
        missing = [row for row in batch if not resolve_product_image(row)]
        candidates = _image_candidates(product_image_identity(row, organization) for row in missing)
        for row in batch:
            url = resolve_product_image(row) or candidates.get(product_image_identity(row, organization), "")
            if isinstance(row, dict):
                row["product_image_url"] = url
            else:
                row.product_image_url = url
    return rows


def backfill_product_images(*, organization=None, dry_run=False, source_images=None, source=None):
    """Only update image columns; source_images must be exact four-part identity keys."""
    stats = {"total": 0, "success": 0, "missing": 0, "updated": 0, "facts_updated": 0, "catalog_updated": 0}
    source_images = source_images or {}
    for model, counter in ((ProductCatalog, "catalog_updated"), (MonthlyProductFact, "facts_updated")):
        queryset = model.objects.all()
        if organization is not None:
            queryset = queryset.filter(organization=organization)
        if source:
            queryset = queryset.filter(source__icontains=source)
        last_pk = 0
        while True:
            batch = list(queryset.filter(pk__gt=last_pk).order_by("pk")[:400])
            if not batch:
                break
            last_pk = batch[-1].pk
            original = {row.pk: row.product_image_url for row in batch}
            enrich_product_images(batch)
            changed = []
            for row in batch:
                # Explicit source reads only fill missing images, never replace valid ones.
                url = row.product_image_url or normalize_product_image_url(source_images.get(product_image_identity(row)))
                stats["total"] += 1
                stats["success" if url else "missing"] += 1
                if url and url != original[row.pk]:
                    row.product_image_url = url
                    changed.append(row)
            stats["updated"] += len(changed)
            stats[counter] += len(changed)
            if changed and not dry_run:
                with transaction.atomic():
                    # Avoid overwriting a concurrent sync's newly supplied image.
                    current = {row.pk: row for row in model.objects.select_for_update().filter(pk__in=[row.pk for row in changed])}
                    safe = [row for row in changed if row.pk in current and current[row.pk].product_image_url == original[row.pk]]
                    model.objects.bulk_update(safe, ["product_image_url"], batch_size=400)
    return stats
