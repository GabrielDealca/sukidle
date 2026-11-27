from django.contrib.postgres.fields import ArrayField
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class Retailer(models.Model):
    """A source retailer. Internal label only; never shown as branding."""

    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)

    def __str__(self) -> str:
        return self.name


class Branch(models.Model):
    """A retailer store / store view. Prices in one snapshot come from one branch."""

    retailer = models.ForeignKey(Retailer, on_delete=models.PROTECT, related_name="branches")
    code = models.CharField(max_length=100)
    name = models.CharField(max_length=200, blank=True)
    city = models.CharField(max_length=100, blank=True)
    is_reference = models.BooleanField(default=False)

    class Meta:
        verbose_name_plural = "branches"
        constraints = [
            models.UniqueConstraint(fields=["retailer", "code"], name="uniq_branch_code")
        ]

    def __str__(self) -> str:
        return f"{self.retailer.slug}:{self.code}"


class Category(models.Model):
    name = models.CharField(max_length=200)
    # Full path slug, e.g. "pantry/canned-goods", so nested categories stay unique.
    slug = models.CharField(max_length=300, unique=True)
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="children"
    )
    puzzle_weight = models.PositiveSmallIntegerField(default=1)

    class Meta:
        verbose_name_plural = "categories"
        ordering = ["slug"]

    def __str__(self) -> str:
        return self.slug


class Product(models.Model):
    retailer = models.ForeignKey(Retailer, on_delete=models.PROTECT, related_name="products")
    source_product_id = models.CharField(max_length=100)
    sku = models.CharField(max_length=100, blank=True)
    barcode = models.CharField(max_length=50, blank=True, db_index=True)
    brand = models.CharField(max_length=100, blank=True)
    name = models.CharField(max_length=300)
    size_text = models.CharField(max_length=100, blank=True)
    size_value = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    size_unit = models.CharField(max_length=20, blank=True)
    pack_count = models.PositiveIntegerField(default=1)
    category = models.ForeignKey(
        Category, null=True, blank=True, on_delete=models.SET_NULL, related_name="products"
    )
    source_url = models.URLField(max_length=500, blank=True)
    image_key = models.CharField(max_length=300, blank=True)
    image_source_url = models.URLField(max_length=500, blank=True)
    license_note = models.CharField(max_length=300, blank=True)
    is_puzzle_eligible = models.BooleanField(default=False)
    difficulty = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    tags = ArrayField(models.CharField(max_length=50), default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["retailer", "source_product_id"], name="uniq_product_source_id"
            )
        ]

    def __str__(self) -> str:
        return f"{self.name} {self.size_text}".strip()


class PriceSnapshot(models.Model):
    class Source(models.TextChoices):
        SMMARKETS_ONLINE = "smmarkets_online", "SM Markets online"
        MANUAL_INSTORE = "manual_instore", "Manual (in-store)"
        MANUAL_ONLINE = "manual_online", "Manual (online)"

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="prices")
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name="prices")
    scrape_run = models.ForeignKey(
        "ingest.ScrapeRun", null=True, blank=True, on_delete=models.SET_NULL, related_name="prices"
    )
    price_centavos = models.PositiveIntegerField()  # regular price; always the puzzle answer
    sale_price_centavos = models.PositiveIntegerField(null=True, blank=True)
    observed_on = models.DateField()
    source = models.CharField(max_length=30, choices=Source.choices)

    class Meta:
        indexes = [models.Index(fields=["product", "-observed_on"], name="price_product_date_idx")]
        constraints = [
            models.UniqueConstraint(
                fields=["product", "branch", "observed_on", "source"], name="uniq_price_observation"
            )
        ]

    def __str__(self) -> str:
        return f"{self.product_id} {self.price_centavos}c on {self.observed_on}"
