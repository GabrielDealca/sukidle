from django.conf import settings
from django.db import connection
from django.http import HttpRequest, JsonResponse


def health(request: HttpRequest) -> JsonResponse:
    """Liveness + DB check, used by the deploy script's health check."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        db_ok = True
    except Exception:  # noqa: BLE001 - any DB failure means unhealthy
        db_ok = False
    status = 200 if db_ok else 503
    return JsonResponse(
        {"status": "ok" if db_ok else "error", "db": db_ok, "version": settings.GIT_SHA},
        status=status,
    )
