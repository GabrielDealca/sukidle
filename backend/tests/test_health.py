import pytest


@pytest.mark.django_db
def test_health_reports_db_and_version(client, settings):
    settings.GIT_SHA = "abc123"
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "db": True, "version": "abc123"}
