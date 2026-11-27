import io
from datetime import date

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from catalog.models import Branch, Category, PriceSnapshot, Product
from ingest.csv_import import import_csv
from ingest.models import RawPayload, ScrapeRun
from ingest.scrape import normalize_run, run_scrape
from ingest.sources.base import CategoryRef, RawPage
from ingest.sources.smmarkets import SMMarketsAdapter
from tests.test_smmarkets import make_item

pytestmark = pytest.mark.django_db

HEADER = "name,brand,size_text,price_php,branch,observed_on,photo_path,barcode,category\n"


def csv_file(*rows: str) -> io.StringIO:
    return io.StringIO(HEADER + "\n".join(rows) + "\n")


# --- CSV import ---------------------------------------------------------------
def test_csv_import_creates_products_and_prices():
    result = import_csv(
        csv_file(
            "Pancit Canton Original,Lucky Me,60g x 6,89.75,sm_test,2026-11-20,photos/pc.jpg,"
            "4800016644290,Pantry > Noodles",
            "Evaporated Milk,Alaska,370ml,42.50,,2026-11-20,,,Pantry",
        ),
        default_branch="ref",
    )
    assert result.errors == []
    assert (result.created, result.updated) == (2, 0)

    canton = Product.objects.get(barcode="4800016644290")
    assert canton.brand == "Lucky Me"
    assert (canton.size_value, canton.size_unit, canton.pack_count) == (60, "g", 6)
    assert canton.category.slug == "pantry/noodles"
    assert canton.category.parent.slug == "pantry"
    assert canton.image_key == "photos/pc.jpg"
    snap = canton.prices.get()
    assert snap.price_centavos == 8975
    assert snap.source == PriceSnapshot.Source.MANUAL_INSTORE
    assert snap.observed_on == date(2026, 11, 20)
    assert snap.branch.code == "sm_test"

    milk = Product.objects.get(name="Evaporated Milk")
    assert milk.source_product_id.startswith("manual:")
    assert milk.prices.get().branch.code == "ref"


def test_csv_import_is_all_or_nothing():
    result = import_csv(
        csv_file(
            "Good Item,,100g,50.00,,2026-11-20,,,",
            "Bad Price,,100g,abc,,2026-11-20,,,",
            "Bad Date,,100g,10,,20-11-2026,,,",
            ",,100g,10,,2026-11-20,,,",
        )
    )
    assert len(result.errors) == 3
    assert result.errors[0].startswith("line 3:")
    assert Product.objects.count() == 0


def test_csv_import_rejects_unknown_and_missing_columns():
    assert import_csv(io.StringIO("name,cost\nX,1\n")).errors
    assert import_csv(io.StringIO("brand\nX\n")).errors


def test_csv_reimport_updates_price_but_keeps_curated_fields():
    row = "Pancit Canton,Lucky Me,60g,15.00,,2026-11-20,,,"
    import_csv(csv_file(row))
    product = Product.objects.get()
    product.name = "Pancit Canton Original (curated)"
    product.is_puzzle_eligible = True
    product.save()

    import_csv(csv_file("Pancit Canton,Lucky Me,60g,16.00,,2026-11-20,,,"))
    product.refresh_from_db()
    assert product.name == "Pancit Canton Original (curated)"
    assert product.is_puzzle_eligible
    assert product.prices.get().price_centavos == 1600  # same day+branch -> updated


def test_csv_dry_run_writes_nothing():
    result = import_csv(csv_file("Item,,1kg,10,,2026-11-20,,,"), dry_run=True)
    assert result.rows == 1 and not result.errors
    assert Product.objects.count() == 0


def test_import_csv_command(tmp_path):
    path = tmp_path / "prices.csv"
    path.write_text(HEADER + "Item,,1kg,10,,2026-11-20,,,\n", encoding="utf-8")
    call_command("import_csv", str(path))
    assert Product.objects.count() == 1

    bad = tmp_path / "bad.csv"
    bad.write_text(HEADER + "Item,,1kg,oops,,2026-11-20,,,\n", encoding="utf-8")
    with pytest.raises(CommandError):
        call_command("import_csv", str(bad))


# --- scrape pipeline (no network) ---------------------------------------------
class FakeSMMarkets(SMMarketsAdapter):
    """SMMarketsAdapter with the network replaced by canned pages."""

    def __init__(self, pages):
        super().__init__(client=None)
        self._pages = pages

    def list_categories(self):
        return [
            CategoryRef("A", "pantry", "Pantry"),
            CategoryRef("B", "beverage", "Beverage"),
        ]

    def iter_pages(self, category):
        for payload in self._pages.get(category.slug, []):
            yield RawPage(url=f"fake://{category.slug}", payload=payload)


def _payload(*items):
    return {"data": {"products": {"items": list(items)}}}


def test_run_scrape_end_to_end():
    adapter = FakeSMMarkets(
        {
            "pantry": [
                _payload(make_item(id=1, name="Corned Beef | 150g")),
                _payload(make_item(id=2)),
            ],
            # id=1 also appears in another category: counted once
            "beverage": [_payload(make_item(id=1, name="Corned Beef | 150g"))],
        }
    )
    run = run_scrape(adapter, branch_code="default", observed_on=date(2026, 11, 26))

    assert run.status == ScrapeRun.Status.SUCCEEDED
    assert run.finished_at is not None
    assert run.payloads.count() == 3
    assert (run.products_seen, run.products_upserted) == (2, 2)
    beef = Product.objects.get(source_product_id="1")
    assert (beef.size_value, beef.size_unit) == (150, "g")
    snap = beef.prices.get()
    assert snap.source == "smmarkets_online"
    assert snap.scrape_run == run
    assert snap.observed_on == date(2026, 11, 26)
    assert Branch.objects.get(code="default").is_reference  # REFERENCE_BRANCH_CODE default


def test_run_scrape_category_filter_and_max_pages():
    adapter = FakeSMMarkets(
        {"pantry": [_payload(make_item(id=1)), _payload(make_item(id=2))], "beverage": []}
    )
    run = run_scrape(adapter, branch_code="default", category_slugs=["pantry"], max_pages=1)
    assert run.payloads.count() == 1
    assert Product.objects.count() == 1


def test_normalize_run_is_repeatable():
    adapter = FakeSMMarkets({"pantry": [_payload(make_item(id=1))]})
    run = run_scrape(adapter, branch_code="default", observed_on=date(2026, 11, 26))
    normalize_run(run, adapter=adapter, observed_on=date(2026, 11, 26))
    assert Product.objects.count() == 1
    assert PriceSnapshot.objects.count() == 1


def test_bad_items_are_recorded_not_fatal():
    adapter = FakeSMMarkets({"pantry": [_payload({"id": 9, "name": "Broken"}, make_item(id=1))]})
    run = run_scrape(adapter, branch_code="default")
    assert run.status == ScrapeRun.Status.SUCCEEDED
    assert run.products_upserted == 1
    assert len(run.errors) == 1


def test_failed_fetch_marks_run_failed():
    class Exploding(FakeSMMarkets):
        def iter_pages(self, category):
            raise RuntimeError("network down")
            yield  # pragma: no cover

    run = run_scrape(Exploding({}), branch_code="default")
    assert run.status == ScrapeRun.Status.FAILED
    assert "network down" in run.errors[0]["error"]


def test_normalize_run_command_reparses_stored_payloads():
    adapter = FakeSMMarkets({"pantry": [_payload(make_item(id=5))]})
    run = run_scrape(adapter, branch_code="default")
    Product.objects.all().delete()
    call_command("normalize_run", str(run.pk))
    assert Product.objects.filter(source_product_id="5").exists()
    assert RawPayload.objects.count() == 1


def test_scrape_command_respects_kill_switch(settings):
    settings.INGEST_ENABLED = False
    with pytest.raises(CommandError, match="INGEST_ENABLED"):
        call_command("scrape_smmarkets", "--dry-run")


def test_scrape_command_requires_contact_email(settings):
    settings.SCRAPE_CONTACT_EMAIL = ""
    with pytest.raises(CommandError, match="SCRAPE_CONTACT_EMAIL"):
        call_command("scrape_smmarkets", "--dry-run")


def test_category_tree_is_created_once():
    adapter = FakeSMMarkets({"pantry": [_payload(make_item(id=1), make_item(id=2))]})
    run_scrape(adapter, branch_code="default")
    assert Category.objects.filter(slug="health-beauty/hair").count() == 1
