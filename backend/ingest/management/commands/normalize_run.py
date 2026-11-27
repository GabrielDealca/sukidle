from django.core.management.base import BaseCommand, CommandError

from ingest.models import ScrapeRun
from ingest.scrape import normalize_run
from ingest.sources.smmarkets import SMMarketsAdapter

ADAPTERS = {SMMarketsAdapter.source: SMMarketsAdapter}


class Command(BaseCommand):
    help = "Re-parse the stored raw payloads of a scrape run (no network requests)."

    def add_arguments(self, parser):
        parser.add_argument("scrape_run_id", type=int)

    def handle(self, *args, **opts):
        try:
            run = ScrapeRun.objects.select_related("branch__retailer").get(pk=opts["scrape_run_id"])
        except ScrapeRun.DoesNotExist as exc:
            raise CommandError("No such scrape run") from exc
        adapter_cls = ADAPTERS.get(run.source)
        if adapter_cls is None:
            raise CommandError(f"No adapter for source {run.source!r}")
        adapter = adapter_cls(client=None)  # parsing needs no client
        normalize_run(run, adapter=adapter)
        self.stdout.write(self.style.SUCCESS(f"Run #{run.pk}: {run.products_upserted} products."))
