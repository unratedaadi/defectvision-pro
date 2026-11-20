from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_migrated_database_and_allowed_origin(tmp_path, monkeypatch):
    monkeypatch.setenv("DV_DATABASE_PATH", str(tmp_path / "test.db"))
    command.upgrade(Config(str(Path(__file__).resolve().parents[1] / "alembic.ini")), "head")
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/health", headers={"Origin": "http://localhost:5173"})
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert response.json() == {
        "status": "ok",
        "database": "ready",
        "categories": [
            {"slug": "bottle", "name": "Bottle"},
            {"slug": "metal_nut", "name": "Metal Nut"},
            {"slug": "tile", "name": "Tile"},
        ],
    }


def test_unmigrated_database_and_disallowed_origin(tmp_path):
    settings = Settings(database_path=tmp_path / "empty.db")
    with TestClient(create_app(settings)) as client:
        response = client.get("/api/v1/health", headers={"Origin": "https://example.org"})
    assert response.status_code == 503
    assert "access-control-allow-origin" not in response.headers
    assert response.json() == {"status": "degraded", "database": "unavailable", "categories": []}


def test_health_rejects_partial_schema_until_upgrade(tmp_path, monkeypatch):
    monkeypatch.setenv("DV_DATABASE_PATH", str(tmp_path / "old.db"))
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(config, "0003")
    with TestClient(create_app()) as client:
        assert client.get("/api/health").status_code == 503
        assert client.get("/api/v1/health").status_code == 503
    command.upgrade(config, "head")
    with TestClient(create_app()) as client:
        assert client.get("/api/health").status_code == 200
        assert client.get("/api/inspections").json() == {"items": [], "total": 0}
