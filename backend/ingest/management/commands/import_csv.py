from django.core.management.base import BaseCommand, CommandError

from catalog.models import PriceSnapshot
from ingest.csv_import import import_csv


class Command(BaseCommand):
    help = "Import products + prices from a manual CSV (README §4.4)."

    def add_arguments(self, parser):
        parser.add_argument("path")
        parser.add_argument(
            "--source",
            default=PriceSnapshot.Source.MANUAL_INSTORE,
            choices=PriceSnapshot.Source.values,
        )
        parser.add_argument("--branch", help="Default branch code for rows without one")
        parser.add_argument("--dry-run", action="store_true", help="Validate only")

    def handle(self, *args, **opts):
        with open(opts["path"], encoding="utf-8-sig", newline="") as fh:
            result = import_csv(
                fh, source=opts["source"], default_branch=opts["branch"], dry_run=opts["dry_run"]
            )
        if result.errors:
            for error in result.errors:
                self.stderr.write(self.style.ERROR(error))
            raise CommandError(f"{len(result.errors)} error(s); nothing was imported.")
        if opts["dry_run"]:
            self.stdout.write(self.style.SUCCESS(f"OK: {result.rows} valid row(s) (dry run)."))
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Imported {result.rows} row(s): "
                    f"{result.created} new, {result.updated} updated."
                )
            )
