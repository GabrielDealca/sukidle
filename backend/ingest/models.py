from django.db import models
from django.utils import timezone


class ScrapeRun(models.Model):
    class Status(models.TextChoices):
        RUNNING = "running"
        SUCCEEDED = "succeeded"
        FAILED = "failed"

    branch = models.ForeignKey("catalog.Branch", on_delete=models.PROTECT, related_name="runs")
    source = models.CharField(max_length=30)
    started_at = models.DateTimeField(default=timezone.now)
    finished_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.RUNNING)
    products_seen = models.PositiveIntegerField(default=0)
    products_upserted = models.PositiveIntegerField(default=0)
    errors = models.JSONField(default=list, blank=True)

    def __str__(self) -> str:
        return f"ScrapeRun #{self.pk} {self.source} {self.status}"


class RawPayload(models.Model):
    """The raw response, kept so we can re-parse without re-fetching."""

    scrape_run = models.ForeignKey(ScrapeRun, on_delete=models.CASCADE, related_name="payloads")
    url = models.TextField()
    fetched_at = models.DateTimeField(default=timezone.now)
    payload = models.JSONField()

    def __str__(self) -> str:
        return f"RawPayload #{self.pk} (run {self.scrape_run_id})"
