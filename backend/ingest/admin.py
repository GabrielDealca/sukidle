from django.contrib import admin

from ingest.models import RawPayload, ScrapeRun


@admin.register(ScrapeRun)
class ScrapeRunAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "source",
        "branch",
        "status",
        "started_at",
        "finished_at",
        "products_seen",
        "products_upserted",
    ]
    list_filter = ["source", "status"]
    readonly_fields = ["errors"]


@admin.register(RawPayload)
class RawPayloadAdmin(admin.ModelAdmin):
    list_display = ["id", "scrape_run", "url", "fetched_at"]
    raw_id_fields = ["scrape_run"]
