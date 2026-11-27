"""Pluggable source adapters. Downstream code only sees NormalizedProduct."""

from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass, field


class SourceError(RuntimeError):
    """The source returned something we can't use (HTML instead of JSON, API errors...)."""


@dataclass(frozen=True)
class CategoryRef:
    key: str  # source-specific id (e.g. Magento category uid)
    slug: str  # path slug, e.g. "pantry/canned-goods"
    name: str


@dataclass(frozen=True)
class RawPage:
    url: str
    payload: dict


@dataclass(frozen=True)
class NormalizedProduct:
    source_product_id: str
    name: str
    price_centavos: int  # regular price
    sale_price_centavos: int | None = None
    sku: str = ""
    barcode: str = ""
    brand: str = ""
    size_text: str = ""
    # (slug, name) pairs from top-level category down to the leaf.
    category_path: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    image_url: str = ""
    product_url: str = ""


class SourceAdapter(ABC):
    source: str  # PriceSnapshot.Source value
    retailer_slug: str
    retailer_name: str

    @abstractmethod
    def list_categories(self) -> list[CategoryRef]: ...

    @abstractmethod
    def iter_pages(self, category: CategoryRef) -> Iterator[RawPage]: ...

    @abstractmethod
    def extract_items(self, payload: dict) -> list[dict]: ...

    @abstractmethod
    def parse(self, raw: dict) -> NormalizedProduct: ...

    def iter_products(self, category: CategoryRef) -> Iterator[NormalizedProduct]:
        for page in self.iter_pages(category):
            for item in self.extract_items(page.payload):
                yield self.parse(item)
