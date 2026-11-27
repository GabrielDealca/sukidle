"""NormalizedProduct -> Product / PriceSnapshot upserts. Never overwrites curated fields."""

from datetime import date

from django.conf import settings

from catalog.models import Branch, Category, PriceSnapshot, Product, Retailer
from ingest.models import ScrapeRun
from ingest.packsize import parse_pack_size
from ingest.sources.base import NormalizedProduct

# Fields filled from the source only while they are still empty, so admin edits survive re-imports.
_FILL_IF_BLANK = ["sku", "barcode", "brand", "size_text", "size_unit", "source_url"]


def ensure_retailer(slug: str, name: str) -> Retailer:
    retailer, _ = Retailer.objects.get_or_create(slug=slug, defaults={"name": name})
    return retailer


def ensure_branch(retailer: Retailer, code: str) -> Branch:
    branch, _ = Branch.objects.get_or_create(
        retailer=retailer,
        code=code,
        defaults={"name": code, "is_reference": code == settings.REFERENCE_BRANCH_CODE},
    )
    return branch


def ensure_category_path(path: tuple[tuple[str, str], ...]) -> Category | None:
    parent = None
    for slug, name in path:
        category, _ = Category.objects.get_or_create(
            slug=slug, defaults={"name": name, "parent": parent}
        )
        parent = category
    return parent


def upsert_product(
    norm: NormalizedProduct,
    *,
    retailer: Retailer,
    branch: Branch,
    observed_on: date,
    source: str,
    scrape_run: ScrapeRun | None = None,
) -> tuple[Product, bool]:
    pack = parse_pack_size(norm.size_text or norm.name)
    values = {
        "sku": norm.sku,
        "barcode": norm.barcode,
        "brand": norm.brand,
        "name": norm.name,
        "size_text": norm.size_text or pack.size_text,
        "size_value": pack.size_value,
        "size_unit": pack.size_unit,
        "pack_count": pack.pack_count,
        "category": ensure_category_path(norm.category_path),
        "source_url": norm.product_url,
        "image_source_url": norm.image_url,
    }

    product = None
    if norm.barcode:
        product = Product.objects.filter(retailer=retailer, barcode=norm.barcode).first()
    if product is None:
        product, created = Product.objects.get_or_create(
            retailer=retailer, source_product_id=norm.source_product_id, defaults=values
        )
    else:
        created = False

    if not created:
        changed = []
        for field in _FILL_IF_BLANK:
            if not getattr(product, field) and values[field]:
                setattr(product, field, values[field])
                changed.append(field)
        for field in ("size_value", "category"):
            if getattr(product, field) is None and values[field] is not None:
                setattr(product, field, values[field])
                changed.append(field)
        if changed:
            product.save(update_fields=[*changed, "updated_at"])

    PriceSnapshot.objects.update_or_create(
        product=product,
        branch=branch,
        observed_on=observed_on,
        source=source,
        defaults={
            "price_centavos": norm.price_centavos,
            "sale_price_centavos": norm.sale_price_centavos,
            "scrape_run": scrape_run,
        },
    )
    return product, created
