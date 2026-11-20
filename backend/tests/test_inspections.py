from io import BytesIO
from datetime import datetime
from pathlib import Path
from threading import Event
from time import monotonic, sleep
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy.orm import Session

from app.config import Settings
from app.main import create_app
from app.models import BatchJob, Inspection, ModelRegistry
from app.services import inspections
from app.services.inspections import InferenceResult


class TestAdapter:
    __test__ = False

    def predict(self, image, model):
        return InferenceResult(0.8, heatmap=image.copy())


def image_file(format="PNG", size=(8, 8), name="sample.png"):
    content = BytesIO()
    Image.new("RGB", size).save(content, format)
    return name, content.getvalue(), "application/octet-stream"


@pytest.fixture
def settings(tmp_path, monkeypatch):
    monkeypatch.setenv("DV_DATABASE_PATH", str(tmp_path / "test.db"))
    command.upgrade(Config(str(Path(__file__).resolve().parents[1] / "alembic.ini")), "head")
    return Settings(image_storage=tmp_path / "images", max_image_pixels=100,
                    max_upload_bytes=2048, max_batch_images=2)


@pytest.fixture
def ready(settings, tmp_path):
    app = create_app(settings, TestAdapter())
    checkpoint = tmp_path / "fixture.ckpt"
    checkpoint.touch()
    with TestClient(app) as client:
        with Session(app.state.engine) as db:
            db.add(ModelRegistry(id=str(uuid4()), category="tile", model_version="test-only",
                                 checkpoint_path=str(checkpoint), calibrated_threshold=0.5,
                                 status="ready", evaluation_metrics={"image_auroc": 0.9}))
            db.commit()
        yield client, app


def test_untrained_api_has_real_empty_data(settings):
    with TestClient(create_app(settings)) as client:
        health = client.get("/api/health")
        assert health.status_code == 200
        assert health.headers["x-request-id"]
        assert all(not row["ready"] and row["auroc"] is None for row in client.get("/api/models").json())
        assert client.get("/api/inspections").json() == {"items": [], "total": 0}
        assert client.get("/api/analytics/summary").json() == {
            "total": 0, "normal": 0, "defective": 0, "defectPercentage": None,
            "categories": [], "averageInferenceLatencyMs": None, "timedInspections": 0,
        }
        assert client.get("/api/analytics/trends").json() == []
        assert client.get("/api/evaluation/tile").status_code == 404
        for path, files in [("/api/inspect", {"file": image_file()}),
                            ("/api/inspect/batch", {"files": image_file()})]:
            response = client.post(path, data={"category": "tile"}, files=files)
            assert response.status_code == 503
            assert response.json()["detail"]["code"] == "model_not_ready"
        assert not settings.image_storage.exists()
        assert client.get("/api/inspections/missing").status_code == 404
        assert client.delete("/api/inspections/missing").status_code == 404
        assert client.get("/api/reports/missing").status_code == 404


@pytest.mark.parametrize(("file", "status", "code"), [
    (("bad.png", b"not a real image", "image/png"), 422, "invalid_image"),
    (("large.png", b"x" * 2049, "image/png"), 413, "file_too_large"),
    (image_file(size=(11, 10)), 413, "image_too_large"),
    (image_file(format="GIF"), 422, "invalid_image"),
])
def test_upload_validation(settings, file, status, code):
    with TestClient(create_app(settings)) as client:
        response = client.post("/api/inspect", data={"category": "tile"}, files={"file": file})
    assert response.status_code == status
    assert response.json()["detail"]["code"] == code


@pytest.mark.parametrize("format", ["JPEG", "PNG", "WEBP"])
def test_persist_query_media_report_and_delete(ready, settings, format):
    client, _app = ready
    response = client.post("/api/inspect", data={"category": "tile", "source": "webcam"},
                           files={"file": image_file(format, name="../../sample.png")})
    assert response.status_code == 201, response.text
    row = response.json()
    assert row["filename"] == "sample.png"
    assert row["prediction"] == "defective"
    assert row["source"] == "webcam"
    assert row["createdAt"].endswith("+00:00")
    assert row["inferenceLatencyMs"] >= 0
    assert client.get(row["imageUrl"]).headers["content-type"] == "image/png"
    assert client.get(row["heatmapUrl"]).status_code == 200
    assert client.get(f"/api/inspections/{row['id']}").json() == row
    assert client.get("/api/inspections", params={"search": "sample", "category": "tile",
                      "prediction": "defective", "date": row["createdAt"][:10]}).json()["items"] == [row]
    assert client.get("/api/inspections", params={"page": 2, "pageSize": 1}).json() == {"items": [], "total": 1}
    assert client.get("/api/analytics/summary").json()["defective"] == 1
    trend = client.get("/api/analytics/trends").json()
    assert sum(day["total"] for day in trend) == 1
    assert next(day for day in trend if day["date"] == row["createdAt"][:10])["defective"] == 1
    assert client.get("/api/evaluation/tile").json()["metrics"] == {"image_auroc": 0.9}
    assert client.get(f"/api/reports/{row['id']}").content.startswith(b"%PDF")
    assert client.get("/api/reports/inspections.pdf").content.startswith(b"%PDF")
    assert client.delete(f"/api/inspections/{row['id']}").status_code == 204
    assert not list(settings.image_storage.iterdir())
    assert client.get(row["imageUrl"]).status_code == 404


def test_history_range_sort_id_search_and_dashboard_reconcile(ready, settings, monkeypatch):
    client, app = ready
    monkeypatch.setattr(inspections, "utc_now", lambda: datetime(2026, 11, 12, 12))
    cases = [
        ("outside", "tile", "normal", "2026-11-09T23:59:59.999999", 999),
        ("tile%001", "tile", "normal", "2026-11-10T00:00:00", 10),
        ("tileX001", "tile", "defective", "2026-11-12T00:00:00", None),
        ("tile-end", "tile", "defective", "2026-11-12T23:59:59.999999", 30),
        ("bottle-end", "bottle", "normal", "2026-11-12T23:59:59.999999", 60),
        ("future", "tile", "defective", "2026-11-13T00:00:00", 999),
    ]
    with Session(app.state.engine) as db:
        db.add_all([
            Inspection(id=id, category=category, prediction=prediction, inference_latency_ms=latency,
                       created_at=datetime.fromisoformat(created), filename="sample.png", source="upload",
                       model_version="fixture", threshold_used=0.5,
                       anomaly_score=0.7 if prediction == "defective" else 0.2,
                       original_image_path=f"{id}.png")
            for id, category, prediction, created, latency in cases
        ])
        db.commit()
    settings.image_storage.mkdir()
    Image.new("RGB", (400, 200)).save(settings.image_storage / "tile-end.png")

    params = {"category": "tile", "dateFrom": "2026-11-10", "dateTo": "2026-11-12"}
    page = client.get("/api/inspections", params={**params, "pageSize": 1, "page": 2}).json()
    assert page["total"] == 3 and page["items"][0]["id"] == "tileX001"
    oldest = client.get("/api/inspections", params={**params, "sort": "oldest", "prediction": "defective"}).json()
    assert [item["id"] for item in oldest["items"]] == ["tileX001", "tile-end"]
    search = client.get("/api/inspections", params={"search": "TILE%001"}).json()
    assert [item["id"] for item in search["items"]] == ["tile%001"]
    assert client.get("/api/inspections", params={"dateFrom": "2026-11-13", "dateTo": "2026-11-12"}).status_code == 422
    assert client.get("/api/inspections", params={"dateFrom": "2026-02-30"}).status_code == 422

    response = client.get("/api/analytics/dashboard", params={"days": 3, "category": "tile"})
    assert response.status_code == 200, response.text
    data = response.json()
    assert (data["dateFrom"], data["dateTo"]) == (params["dateFrom"], params["dateTo"])
    assert (data["total"], data["normal"], data["defective"]) == (page["total"], 1, 2)
    assert data["defectPercentage"] == pytest.approx(200 / 3)
    assert data["timedInspections"] == 2
    assert data["averageInferenceLatencyMs"] == 20
    assert [item["id"] for item in data["recent"]] == ["tile-end", "tileX001", "tile%001"]
    assert [(row["date"], row["total"], row["defectPercentage"]) for row in data["trend"]] == [
        ("2026-11-10", 1, 0), ("2026-11-11", 0, None), ("2026-11-12", 2, 100),
    ]
    assert data["categories"][0]["total"] == data["total"]
    assert client.get("/api/analytics/trends", params={"days": 3, "category": "tile"}).json() == data["trend"]
    all_categories = client.get("/api/analytics/summary", params={"days": 3}).json()
    assert sum(row["total"] for row in all_categories["categories"]) == all_categories["total"] == 4
    assert all_categories["averageInferenceLatencyMs"] == pytest.approx(100 / 3)

    with Image.open(BytesIO(client.get("/api/inspections/tile-end/media/thumbnail").content)) as thumbnail:
        assert thumbnail.size == (120, 60)
    assert client.get("/api/inspections/tile-end/media/heatmap").status_code == 404
    assert client.delete("/api/inspections/tile-end").status_code == 204
    assert client.get("/api/inspections/tile-end").status_code == 404
    assert client.get("/api/inspections/tile-end/media/thumbnail").status_code == 404
    assert client.get("/api/inspections", params=params).json()["total"] == 2
    assert client.get("/api/analytics/dashboard", params={"days": 3, "category": "tile"}).json()["total"] == 2


def test_batch_tracks_partial_results(ready):
    client, app = ready
    entered, release = Event(), Event()
    adapter = app.state.inference
    original = adapter.predict

    def gated(image, model):
        entered.set()
        assert release.wait(5)
        return original(image, model)

    adapter.predict = gated
    files = [("files", image_file()), ("files", ("sample.png", b"bad", "image/png"))]
    response = client.post("/api/inspect/batch", data={"category": "tile"}, files=files)
    assert response.status_code == 202, response.text
    path = response.headers["location"]
    try:
        assert entered.wait(3)
        running = client.get(path).json()
        assert running["status"] == "processing" and running["processed_images"] == 0
        assert client.get("/api/health").status_code == 200
        assert client.post("/api/inspect/batch", data={"category": "tile"}, files=files).status_code == 429
    finally:
        release.set()
    deadline = monotonic() + 4
    while monotonic() < deadline:
        job = client.get(path).json()
        if job["status"] != "processing":
            break
        sleep(0.02)
    assert (job["status"], job["processed_images"], job["failed_images"]) == ("partial", 1, 1)
    assert job["errors"][0]["index"] == 1
    assert job["items"][0]["batchId"] == job["id"]
    report = client.get(f"/api/reports/batch/{job['id']}")
    assert report.headers["content-type"] == "application/pdf"
    assert report.content.startswith(b"%PDF")
    assert client.get("/api/reports/batch/missing").status_code == 404
    assert job["items"][0]["batchIndex"] == 0
    assert client.get("/api/inspections").json()["total"] == 1
    with Session(app.state.engine) as db:
        assert db.get(BatchJob, job["id"]).completed_at is not None
    assert client.post("/api/inspect/batch", data={"category": "tile"}, files=files * 2).status_code == 413


def test_webcam_preview_saves_exact_frame_once(ready, settings):
    client, app = ready
    response = client.post("/api/inspect/webcam", data={"category": "tile"}, files={"file": image_file()})
    assert response.status_code == 200, response.text
    frame = response.json()
    assert frame["imageUrl"].startswith("data:image/png;base64,")
    assert frame["heatmapUrl"].startswith("data:image/png;base64,")
    assert frame["expiresIn"] == 300
    assert client.get("/api/inspections").json()["total"] == 0
    assert not settings.image_storage.exists()

    def unexpected(*_args):
        raise AssertionError("Saving must reuse the preview inference.")

    app.state.inference.predict = unexpected
    path = f"/api/inspect/webcam/{frame['id']}/save"
    saved = client.post(path)
    assert saved.status_code == 200, saved.text
    for key in ("id", "score", "prediction", "modelVersion", "createdAt"):
        assert saved.json()[key] == frame[key]
    assert client.get(saved.json()["imageUrl"]).status_code == 200
    assert client.post(path).json() == saved.json()
    assert client.get("/api/inspections").json()["total"] == 1
    assert client.post("/api/inspect/webcam/expired/save").json()["detail"]["code"] == "frame_expired"
    missing = client.post("/api/inspect/webcam", data={"category": "bottle"}, files={"file": image_file()})
    assert missing.status_code == 503
    assert missing.json()["detail"]["code"] == "model_not_ready"


def test_delete_cors_preflight(settings):
    with TestClient(create_app(settings)) as client:
        response = client.options("/api/inspections/test", headers={
            "Origin": "http://127.0.0.1:5173", "Access-Control-Request-Method": "DELETE",
        })
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"


@pytest.mark.parametrize("chunked", [False, True])
def test_multipart_request_cap(settings, chunked):
    with TestClient(create_app(settings)) as client:
        request = client.build_request("POST", "/api/inspect", data={"category": "tile"},
                                       files={"file": ("big.png", b"x" * 70_000, "image/png")})
        if chunked:
            request.headers.pop("content-length")
            request.headers["transfer-encoding"] = "chunked"
        response = client.send(request)
    assert response.status_code == 413, response.text
    assert response.json()["detail"]["code"] == "request_too_large"
