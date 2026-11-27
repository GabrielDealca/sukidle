"""smmarkets.ph adapter (Magento 2 GraphQL). See docs/discovery.md.

Store/branch is selected with the ``Store`` header; "default" sends no header.
"""

import json
from collections.abc import Iterator

from ingest.money import php_to_centavos
from ingest.names import clean_name, split_size_suffix
from ingest.sources.base import CategoryRef, NormalizedProduct, RawPage, SourceAdapter, SourceError
from ingest.sources.http import PoliteClient

BASE_URL = "https://smmarkets.ph"
GRAPHQL_URL = f"{BASE_URL}/graphql"

PRODUCT_FIELDS = """
id sku name url_key stock_status
price_range { minimum_price {
  regular_price { value currency }
  final_price { value currency }
} }
special_price
small_image { url }
categories { uid name url_path }
"""


class SMMarketsAdapter(SourceAdapter):
    source = "smmarkets_online"
    retailer_slug = "sm-markets"
    retailer_name = "SM Markets"

    def __init__(self, client: PoliteClient, *, store_code: str = "default", page_size: int = 50):
        self.client = client
        self.store_code = store_code
        self.page_size = page_size

    # --- transport ----------------------------------------------------------
    def _query(self, query: str) -> tuple[str, dict]:
        headers = {} if self.store_code == "default" else {"Store": self.store_code}
        response = self.client.get(GRAPHQL_URL, params={"query": query}, headers=headers)
        if "json" not in response.headers.get("content-type", ""):
            raise SourceError(f"Expected JSON from {GRAPHQL_URL}, got {response.headers}")
        payload = response.json()
        if payload.get("errors") and not payload.get("data"):
            raise SourceError(f"GraphQL errors: {payload['errors']}")
        return str(response.url), payload

    # --- SourceAdapter ------------------------------------------------------
    def list_categories(self) -> list[CategoryRef]:
        _, config = self._query("{ storeConfig { root_category_uid } }")
        root_uid = config["data"]["storeConfig"]["root_category_uid"]
        uid = json.dumps(root_uid)
        _, data = self._query(
            f"{{ categories(filters: {{ parent_category_uid: {{ eq: {uid} }} }}) "
            "{ items { uid name url_path } } }"
        )
        items = data["data"]["categories"]["items"]
        return [CategoryRef(key=i["uid"], slug=i["url_path"], name=i["name"]) for i in items]

    def iter_pages(self, category: CategoryRef) -> Iterator[RawPage]:
        page = 1
        while True:
            uid = json.dumps(category.key)
            query = (
                f"{{ products(filter: {{ category_uid: {{ eq: {uid} }} }}, "
                f"pageSize: {self.page_size}, currentPage: {page}, sort: {{ name: ASC }}) "
                "{ total_count page_info { current_page total_pages } "
                f"items {{ {PRODUCT_FIELDS} }} }} }}"
            )
            url, payload = self._query(query)
            yield RawPage(url=url, payload=payload)
            info = (payload.get("data") or {}).get("products", {}).get("page_info") or {}
            if page >= int(info.get("total_pages") or 0):
                break
            page += 1

    def extract_items(self, payload: dict) -> list[dict]:
        products = (payload.get("data") or {}).get("products") or {}
        return products.get("items") or []

    def parse(self, raw: dict) -> NormalizedProduct:
        base_name, size_text = split_size_suffix(raw["name"])
        prices = raw["price_range"]["minimum_price"]
        regular = php_to_centavos(prices["regular_price"]["value"])
        final = php_to_centavos(prices["final_price"]["value"])

        sale: int | None = final if 0 < final < regular else None
        special = raw.get("special_price")
        if sale is None and special:
            special_c = php_to_centavos(special)
            if 0 < special_c < regular:
                sale = special_c

        image = (raw.get("small_image") or {}).get("url") or ""
        if "placeholder" in image:
            image = ""

        return NormalizedProduct(
            source_product_id=str(raw["id"]),
            sku=str(raw.get("sku") or ""),
            name=clean_name(base_name),
            size_text=size_text,
            price_centavos=regular,
            sale_price_centavos=sale,
            category_path=_category_path(raw.get("categories") or []),
            image_url=image,
            product_url=f"{BASE_URL}/{raw['url_key']}.html" if raw.get("url_key") else "",
        )


def _category_path(categories: list[dict]) -> tuple[tuple[str, str], ...]:
    """Pick the deepest category and expand it into (slug, name) pairs from the top."""
    paths = [c for c in categories if c.get("url_path")]
    if not paths:
        return ()
    names = {c["url_path"]: c["name"] for c in paths}
    deepest = max(paths, key=lambda c: c["url_path"].count("/"))["url_path"]
    parts = deepest.split("/")
    result = []
    for i in range(1, len(parts) + 1):
        slug = "/".join(parts[:i])
        result.append((slug, names.get(slug, parts[i - 1].replace("-", " ").title())))
    return tuple(result)
