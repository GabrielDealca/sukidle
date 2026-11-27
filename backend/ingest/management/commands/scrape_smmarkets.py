from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from ingest.scrape import run_scrape
from ingest.sources.http import PoliteClient
from ingest.sources.smmarkets import SMMarketsAdapter


def build_adapter(store_code: str, page_size: int) -> SMMarketsAdapter:
    if not settings.SCRAPE_CONTACT_EMAIL:
        raise CommandError("Set SCRAPE_CONTACT_EMAIL (it goes in the honest User-Agent).")
    user_agent = f"{settings.APP_NAME}Bot/0.1 (+mailto:{settings.SCRAPE_CONTACT_EMAIL})"
    return SMMarketsAdapter(PoliteClient(user_agent), store_code=store_code, page_size=page_size)


class Command(BaseCommand):
    help = "Snapshot products + prices from smmarkets.ph (~1 req/s, backs off, stops if blocked)."

    def add_arguments(self, parser):
        parser.add_argument("--branch", help="Store code (default: REFERENCE_BRANCH_CODE)")
        parser.add_argument("--category", action="append", help="Category url_path; repeatable")
        parser.add_argument("--max-pages", type=int, default=None, help="Stop after N pages")
        parser.add_argument("--page-size", type=int, default=50)
        parser.add_argument(
            "--dry-run", action="store_true", help="List categories only; write nothing"
        )

    def handle(self, *args, **opts):
        if not settings.INGEST_ENABLED:
            raise CommandError("INGEST_ENABLED is false; scraping is switched off.")
        branch = opts["branch"] or settings.REFERENCE_BRANCH_CODE
        adapter = build_adapter(branch, opts["page_size"])
        try:
            if opts["dry_run"]:
                for category in adapter.list_categories():
                    self.stdout.write(f"{category.slug}\t{category.name}")
                return
            run = run_scrape(
                adapter,
                branch_code=branch,
                category_slugs=opts["category"],
                max_pages=opts["max_pages"],
            )
        finally:
            self.stdout.write(f"HTTP requests made: {adapter.client.request_count}")
            adapter.client.close()
        style = self.style.SUCCESS if run.status == "succeeded" else self.style.ERROR
        self.stdout.write(
            style(
                f"ScrapeRun #{run.pk} {run.status}: {run.products_upserted} products, "
                f"{len(run.errors)} error(s)."
            )
        )
