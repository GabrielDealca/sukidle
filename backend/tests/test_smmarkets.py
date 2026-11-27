from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from ingest.sources.base import CategoryRef, SourceError
from ingest.sources.http import BlockedError, PoliteClient
from ingest.sources.smmarkets import SMMarketsAdapter

PANTENE = {
    "id": 6277,
    "sku": "20386830",
    "name": "Pantene Conditioner 3 Minute Collagen Repair | 300ml",
    "url_key": "20386830-pantene-conditioner-3-minute-collagen-repair-300ml",
    "stock_status": "IN_STOCK",
    "price_range": {
        "minimum_price": {
            "regular_price": {"value": 345.0, "currency": "PHP"},
            "final_price": {"value": 345.0, "currency": "PHP"},
        }
    },
    "special_price": "0.00",
    "small_image": {"url": "https://smmarkets.ph/media/catalog/product/placeholder/default/x.png"},
    "categories": [
        {"uid": "MTA=", "name": "Health & Beauty", "url_path": "health-beauty"},
        {"uid": "MTE=", "name": "Hair", "url_path": "health-beauty/hair"},
    ],
}


def make_item(**overrides):
    item = {**PANTENE, **overrides}
    return item


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.sleeps: list[float] = []

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def make_client(handler, clock=None) -> PoliteClient:
    clock = clock or FakeClock()
    return PoliteClient(
        "TestBot/0.1",
        transport=httpx.MockTransport(handler),
        sleep=clock.sleep,
        clock=clock.time,
        jitter=0,
    )


# --- parse ------------------------------------------------------------------
def test_parse_regular_product():
    norm = SMMarketsAdapter(client=None).parse(PANTENE)
    assert norm.source_product_id == "6277"
    assert norm.sku == "20386830"
    assert norm.name == "Pantene Conditioner 3 Minute Collagen Repair"
    assert norm.size_text == "300ml"
    assert norm.price_centavos == 34500
    assert norm.sale_price_centavos is None
    assert norm.image_url == ""  # placeholder images are dropped
    assert norm.category_path == (
        ("health-beauty", "Health & Beauty"),
        ("health-beauty/hair", "Hair"),
    )
    assert norm.product_url.endswith("collagen-repair-300ml.html")


def test_parse_sale_price_from_final_price():
    item = make_item(
        price_range={
            "minimum_price": {
                "regular_price": {"value": 100.0},
                "final_price": {"value": 89.75},
            }
        }
    )
    norm = SMMarketsAdapter(client=None).parse(item)
    assert norm.price_centavos == 10000
    assert norm.sale_price_centavos == 8975


def test_parse_sale_price_from_special_price():
    item = make_item(special_price="299.50")
    norm = SMMarketsAdapter(client=None).parse(item)
    assert norm.price_centavos == 34500
    assert norm.sale_price_centavos == 29950


def test_parse_keeps_real_image_and_builds_missing_parent_names():
    item = make_item(
        small_image={"url": "https://smmarkets.ph/media/catalog/product/a/b.jpg"},
        categories=[{"uid": "x", "name": "Canned Goods", "url_path": "pantry/canned-goods"}],
    )
    norm = SMMarketsAdapter(client=None).parse(item)
    assert norm.image_url.endswith("b.jpg")
    assert norm.category_path == (("pantry", "Pantry"), ("pantry/canned-goods", "Canned Goods"))


# --- transport --------------------------------------------------------------
def _page(items, page, total_pages):
    return {
        "data": {
            "products": {
                "total_count": 3,
                "page_info": {"current_page": page, "total_pages": total_pages},
                "items": items,
            }
        }
    }


def test_iter_pages_paginates_and_sends_store_header():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        query = parse_qs(urlparse(str(request.url)).query)["query"][0]
        page = 1 if "currentPage: 1" in query else 2
        return httpx.Response(200, json=_page([make_item(id=page)], page, 2))

    adapter = SMMarketsAdapter(make_client(handler), store_code="sm_supermarket_x", page_size=1)
    pages = list(adapter.iter_pages(CategoryRef(key="MTA=", slug="pantry", name="Pantry")))
    assert len(pages) == 2
    assert all(r.headers["Store"] == "sm_supermarket_x" for r in seen)
    assert seen[0].headers["User-Agent"] == "TestBot/0.1"
    items = [i for p in pages for i in adapter.extract_items(p.payload)]
    assert [i["id"] for i in items] == [1, 2]


def test_default_store_sends_no_store_header():
    def handler(request):
        assert "Store" not in request.headers
        return httpx.Response(200, json=_page([], 1, 1))

    adapter = SMMarketsAdapter(make_client(handler))
    assert len(list(adapter.iter_pages(CategoryRef("k", "s", "n")))) == 1


def test_list_categories():
    def handler(request):
        query = parse_qs(urlparse(str(request.url)).query)["query"][0]
        if "storeConfig" in query:
            config = {"storeConfig": {"root_category_uid": "Mg=="}}
            return httpx.Response(200, json={"data": config})
        assert '"Mg=="' in query
        items = [{"uid": "MTA=", "name": "Pantry", "url_path": "pantry"}]
        return httpx.Response(200, json={"data": {"categories": {"items": items}}})

    cats = SMMarketsAdapter(make_client(handler)).list_categories()
    assert cats == [CategoryRef(key="MTA=", slug="pantry", name="Pantry")]


def test_html_response_is_an_error():
    def handler(request):
        html = {"content-type": "text/html"}
        return httpx.Response(200, text="<html>captcha</html>", headers=html)

    with pytest.raises(SourceError):
        SMMarketsAdapter(make_client(handler)).list_categories()


# --- politeness -------------------------------------------------------------
def test_client_waits_between_requests():
    clock = FakeClock()
    client = make_client(lambda r: httpx.Response(200, json={}), clock)
    client.get("https://example.test/a")
    client.get("https://example.test/b")
    assert clock.sleeps == [pytest.approx(1.0)]
    assert client.request_count == 2


def test_client_backs_off_on_429_then_succeeds():
    responses = [
        httpx.Response(429, headers={"Retry-After": "7"}),
        httpx.Response(503),
        httpx.Response(200, json={"ok": True}),
    ]
    clock = FakeClock()
    client = make_client(lambda r: responses.pop(0), clock)
    assert client.get("https://example.test").json() == {"ok": True}
    assert 7.0 in clock.sleeps
    assert 10.0 in clock.sleeps  # backoff_base * 2**1 for the 503


def test_client_stops_when_blocked():
    client = make_client(lambda r: httpx.Response(403))
    with pytest.raises(BlockedError):
        client.get("https://example.test")
    assert client.request_count == 1  # no retries, no workarounds


def test_client_gives_up_after_max_retries():
    client = make_client(lambda r: httpx.Response(500))
    with pytest.raises(httpx.HTTPStatusError):
        client.get("https://example.test")
    assert client.request_count == 5
