"""Run a scrape: fetch pages -> RawPayload rows -> normalize into Product/PriceSnapshot."""

import logging
from datetime import date

from django.db import transaction
from django.utils import timezone

from catalog.models import Branch
from ingest.models import RawPayload, ScrapeRun
from ingest.normalize import ensure_branch, ensure_retailer, upsert_product
from ingest.sources.base import SourceAdapter

log = logging.getLogger(__name__)


def run_scrape(
    adapter: SourceAdapter,
    *,
    branch_code: str,
    category_slugs: list[str] | None = None,
    max_pages: int | None = None,
    observed_on: date | None = None,
) -> ScrapeRun:
    retailer = ensure_retailer(adapter.retailer_slug, adapter.retailer_name)
    branch = ensure_branch(retailer, branch_code)
    run = ScrapeRun.objects.create(branch=branch, source=adapter.source)
    pages = 0
    try:
        categories = adapter.list_categories()
        if category_slugs:
            categories = [c for c in categories if c.slug in category_slugs]
        for category in categories:
            for page in adapter.iter_pages(category):
                RawPayload.objects.create(scrape_run=run, url=page.url, payload=page.payload)
                pages += 1
                if max_pages and pages >= max_pages:
                    break
            if max_pages and pages >= max_pages:
                break
        normalize_run(run, observed_on=observed_on, adapter=adapter, branch=branch)
        run.status = ScrapeRun.Status.SUCCEEDED
    except Exception as exc:
        log.exception("Scrape run %s failed", run.pk)
        run.errors = [*run.errors, {"error": repr(exc)}]
        run.status = ScrapeRun.Status.FAILED
    run.finished_at = timezone.now()
    run.save()
    return run


def normalize_run(
    run: ScrapeRun,
    *,
    adapter: SourceAdapter,
    observed_on: date | None = None,
    branch: Branch | None = None,
) -> ScrapeRun:
    """(Re-)parse every stored payload of a run. Safe to repeat."""
    branch = branch or run.branch
    retailer = branch.retailer
    observed_on = observed_on or timezone.localdate(run.started_at)
    seen: set[str] = set()
    upserted = 0
    errors = list(run.errors)
    with transaction.atomic():
        for raw_payload in run.payloads.order_by("id"):
            for item in adapter.extract_items(raw_payload.payload):
                try:
                    norm = adapter.parse(item)
                except (KeyError, TypeError, ValueError) as exc:
                    errors.append(
                        {"payload": raw_payload.pk, "item": item.get("id"), "error": repr(exc)}
                    )
                    continue
                if norm.source_product_id in seen:
                    continue
                seen.add(norm.source_product_id)
                upsert_product(
                    norm,
                    retailer=retailer,
                    branch=branch,
                    observed_on=observed_on,
                    source=adapter.source,
                    scrape_run=run,
                )
                upserted += 1
    run.products_seen = len(seen)
    run.products_upserted = upserted
    run.errors = errors
    run.save(update_fields=["products_seen", "products_upserted", "errors"])
    return run
