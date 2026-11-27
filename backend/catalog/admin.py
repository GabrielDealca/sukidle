from django.contrib import admin

from catalog.models import Branch, Category, PriceSnapshot, Product, Retailer
from ingest.money import format_php


@admin.register(Retailer)
class RetailerAdmin(admin.ModelAdmin):
    list_display = ["name", "slug"]


@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ["code", "name", "retailer", "city", "is_reference"]
    list_filter = ["retailer", "is_reference"]
    search_fields = ["code", "name"]


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["slug", "name", "parent", "puzzle_weight"]
    list_editable = ["puzzle_weight"]
    search_fields = ["slug", "name"]


class PriceSnapshotInline(admin.TabularInline):
    model = PriceSnapshot
    extra = 0
    fields = ["observed_on", "branch", "source", "price_centavos", "sale_price_centavos"]
    ordering = ["-observed_on"]


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    """The curation screen: mark items puzzle-worthy, fix names, set brand/difficulty/tags."""

    list_display = [
        "name",
        "brand",
        "size_text",
        "category",
        "latest_price",
        "is_puzzle_eligible",
        "difficulty",
    ]
    list_editable = ["is_puzzle_eligible", "difficulty"]
    list_filter = ["is_puzzle_eligible", "retailer", "category"]
    search_fields = ["name", "brand", "sku", "barcode", "source_product_id"]
    readonly_fields = ["created_at", "updated_at"]
    inlines = [PriceSnapshotInline]
    actions = ["mark_eligible", "mark_ineligible"]

    @admin.display(description="Latest regular price")
    def latest_price(self, obj: Product) -> str:
        snap = obj.prices.order_by("-observed_on").first()
        return format_php(snap.price_centavos) if snap else "-"

    @admin.action(description="Mark selected as puzzle-eligible")
    def mark_eligible(self, request, queryset):
        queryset.update(is_puzzle_eligible=True)

    @admin.action(description="Mark selected as NOT puzzle-eligible")
    def mark_ineligible(self, request, queryset):
        queryset.update(is_puzzle_eligible=False)


@admin.register(PriceSnapshot)
class PriceSnapshotAdmin(admin.ModelAdmin):
    list_display = [
        "product",
        "branch",
        "observed_on",
        "source",
        "price_centavos",
        "sale_price_centavos",
    ]
    list_filter = ["source", "branch", "observed_on"]
    search_fields = ["product__name"]
    raw_id_fields = ["product", "scrape_run"]
