from fastapi.testclient import TestClient

from izchu.main import app


def test_health_and_root_are_available():
    with TestClient(app) as client:
        health = client.get("/healthz")
        root = client.get("/")

    assert health.status_code == 200
    assert health.json() == {"status": "ok"}
    assert root.status_code == 200
    assert root.json()["name"] == "izchu"
    assert root.json()["docs"] == "/docs"

