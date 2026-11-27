"""Manual CSV import (README §4.4). All-or-nothing: any bad row means nothing is written.

Columns: name, brand, size_text, price_php, branch, observed_on, photo_path, barcode, category
Only ``name`` and ``price_php`` are required. ``category`` may be a path: "Pantry > Noodles".
"""

import csv
from dataclasses import dataclass, field
from datetime import date
from typing import TextIO

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from catalog.models import PriceSnapshot
from ingest.money import MoneyError, php_to_centavos
from ingest.names import clean_name
from ingest.normalize import ensure_branch, ensure_retailer, upsert_product
from ingest.sources.base import NormalizedProduct

COLUMNS = [
    "name",
    "brand",
    "size_text",
    "price_php",
    "branch",
    "observed_on",
    "photo_path",
    "barcode",
    "category",
]
REQUIRED = ["name", "price_php"]


@dataclass
class ImportResult:
    rows: int = 0
    created: int = 0
    updated: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass
class _Row:
    norm: NormalizedProduct
    branch_code: str
    observed_on: date
    photo_path: str


def _category_path(text: str) -> tuple[tuple[str, str], ...]:
    parts = [p.strip() for p in text.replace("›", ">").split(">") if p.strip()]
    path, slugs = [], []
    for part in parts:
        slugs.append(slugify(part))
        path.append(("/".join(slugs), part))
    return tuple(path)


def _parse_row(raw: dict[str, str], default_branch: str) -> _Row:
    get = lambda key: (raw.get(key) or "").strip()  # noqa: E731
    name = clean_name(get("name"))
    if not name:
        raise ValueError("name is required")
    try:
        price = php_to_centavos(get("price_php"), strict=True)
    except MoneyError as exc:
        raise ValueError(str(exc)) from exc
    if price <= 0:
        raise ValueError("price_php must be greater than 0")
    observed_text = get("observed_on")
    try:
        observed_on = date.fromisoformat(observed_text) if observed_text else timezone.localdate()
    except ValueError as exc:
        raise ValueError(f"observed_on must be YYYY-MM-DD, got {observed_text!r}") from exc

    brand, size_text, barcode = get("brand"), get("size_text"), get("barcode")
    source_id = barcode or "manual:" + slugify(f"{brand} {name} {size_text}")
    norm = NormalizedProduct(
        source_product_id=source_id,
        name=name,
        brand=brand,
        size_text=size_text,
        barcode=barcode,
        price_centavos=price,
        category_path=_category_path(get("category")),
    )
    return _Row(norm, get("branch") or default_branch, observed_on, get("photo_path"))


def import_csv(
    fileobj: TextIO,
    *,
    retailer_slug: str = "sm-markets",
    retailer_name: str = "SM Markets",
    source: str = PriceSnapshot.Source.MANUAL_INSTORE,
    default_branch: str | None = None,
    dry_run: bool = False,
) -> ImportResult:
    result = ImportResult()
    default_branch = default_branch or settings.REFERENCE_BRANCH_CODE
    reader = csv.DictReader(fileobj)
    headers = [h.strip() for h in (reader.fieldnames or [])]
    missing = [c for c in REQUIRED if c not in headers]
    if missing:
        result.errors.append(f"Missing required column(s): {', '.join(missing)}")
        return result
    unknown = [h for h in headers if h not in COLUMNS]
    if unknown:
        result.errors.append(f"Unknown column(s): {', '.join(unknown)}")
        return result

    rows: list[_Row] = []
    for line_no, raw in enumerate(reader, start=2):  # line 1 is the header
        if not any((v or "").strip() for v in raw.values()):
            continue  # skip blank lines
        result.rows += 1
        try:
            rows.append(_parse_row({k.strip(): v for k, v in raw.items() if k}, default_branch))
        except ValueError as exc:
            result.errors.append(f"line {line_no}: {exc}")

    if result.errors or dry_run:
        return result

    with transaction.atomic():
        retailer = ensure_retailer(retailer_slug, retailer_name)
        for row in rows:
            branch = ensure_branch(retailer, row.branch_code)
            product, created = upsert_product(
                row.norm,
                retailer=retailer,
                branch=branch,
                observed_on=row.observed_on,
                source=source,
            )
            if row.photo_path and not product.image_key:
                product.image_key = row.photo_path
                product.license_note = product.license_note or "own photo"
                product.save(update_fields=["image_key", "license_note", "updated_at"])
            if created:
                result.created += 1
            else:
                result.updated += 1
    return result
