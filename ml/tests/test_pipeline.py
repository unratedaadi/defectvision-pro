import subprocess
import sys
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from time import monotonic, sleep

import numpy as np
import pytest
from PIL import Image

from ml.artifacts import read_json, write_json
from ml.dataset import ROOT, digest, discover


def save(path, color, size=(48, 32)):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color).save(path)
    return path


@pytest.fixture
def dataset(tmp_path):
    bottle = tmp_path / "dataset" / "bottle"
    for index in range(8):
        save(bottle / "train" / "good" / f"{index}.png", (index * 8, 20, 40))
    save(bottle / "test" / "good" / "normal.png", (8, 21, 40))
    save(bottle / "test" / "broken" / "defect.png", (255, 255, 255))
    mask = bottle / "ground_truth" / "broken" / "defect_mask.png"
    mask.parent.mkdir(parents=True)
    pixels = Image.new("L", (48, 32))
    pixels.paste(255, (8, 8, 20, 20))
    pixels.save(mask)
    return bottle.parent


def test_split_is_reproducible_and_rejects_test_leakage(dataset):
    manifest = discover(dataset, "bottle")
    assert manifest == discover(dataset, "bottle")
    splits = [{row["sha256"] for row in manifest[name]} for name in ("fit", "calibration", "test")]
    assert sum(map(len, splits)) == len(set.union(*splits))
    assert all("/train/good/" in row["path"] for name in ("fit", "calibration") for row in manifest[name])
    fit = dataset / manifest["fit"][0]["path"]
    (dataset / "bottle/test/good/copy.png").write_bytes(fit.read_bytes())
    with pytest.raises(ValueError, match="identical content"):
        discover(dataset, "bottle")


def test_requires_correct_mask_dimensions(dataset):
    save(dataset / "bottle/ground_truth/broken/defect_mask.png", "white", size=(16, 16))
    with pytest.raises(ValueError, match="dimensions"):
        discover(dataset, "bottle")


def test_bottle_checkpoint_calibration_evaluation_and_http(dataset, tmp_path, monkeypatch):
    from ml.patchcore import Predictor, fit, load_model, preprocessing, read_image, torch

    torch.set_num_threads(2)
    manifest = discover(dataset, "bottle")
    config = {
        "category": "bottle", "backbone": "resnet18", "layers": ["layer2", "layer3"],
        "image_size": 64, "batch_size": 2, "max_patches": 256, "coreset_ratio": 0.2,
        "num_neighbors": 3, "seed": 42, "calibration_quantile": 0.95, "pixel_metric_size": 32,
    }
    root = tmp_path / "models"
    run = root / "bottle" / "test-only"
    run.mkdir(parents=True)
    fit_paths = [dataset / row["path"] for row in manifest["fit"]]
    model = fit(config, fit_paths, "cpu", pretrained=False)
    torch.save(model.state_dict(), run / "patchcore.pt")
    write_json(run / "config.yaml", config)
    write_json(run / "split.json", manifest)
    write_json(run / "model.json", {
        "category": "bottle", "version": run.name, "created_at": datetime.now(UTC).isoformat(),
        "packages": {"anomalib": "2.7.0"},
        "sha256": {name: digest(run / name) for name in ("patchcore.pt", "config.yaml", "split.json")},
    })
    for command in ("calibrate", "evaluate"):
        subprocess.run([sys.executable, "-m", f"ml.{command}", "--category", "bottle",
                        "--data", str(dataset), "--models", str(root), "--version", run.name,
                        "--device", "cpu"], cwd=ROOT, check=True, timeout=120)

    pytest.importorskip("fastapi")
    from alembic import command
    from alembic.config import Config
    from fastapi.testclient import TestClient

    monkeypatch.syspath_prepend(str(ROOT / "backend"))
    from app.config import Settings
    from app.main import create_app
    from app.services.patchcore import layers

    database = tmp_path / "integration.db"
    monkeypatch.setenv("DV_DATABASE_PATH", str(database))
    command.upgrade(Config(str(ROOT / "backend/alembic.ini")), "head")
    settings = Settings(models_path=root, image_storage=tmp_path / "uploads",
                        patchcore_enabled=True, patchcore_device="cpu")
    source = dataset / "bottle/test/broken/defect.png"
    predictor = Predictor(load_model(run / "patchcore.pt", config, "cpu"), config)
    tensor = preprocessing(config)(Image.new("RGB", (37, 17), (255, 0, 0)))
    assert tensor.shape == (3, 64, 64)
    torch.testing.assert_close(tensor[:, 0, 0], torch.tensor([
        (1 - 0.485) / 0.229, -0.456 / 0.224, -0.406 / 0.225,
    ]))
    expected_score, raw_map = predictor(read_image(source))
    assert raw_map.shape == (64, 64)
    assert np.isfinite(raw_map).all()
    heatmap, overlay = layers(np.array([[0, 1], [0, 1]], dtype=np.float32), (48, 32))
    assert heatmap.size == overlay.size == (48, 32)
    assert overlay.getpixel((0, 16))[3] == 0
    assert overlay.getpixel((47, 16))[3] == 255

    app = create_app(settings)
    with TestClient(app) as client:
        data = {"category": "bottle"}
        files = {"file": ("fixture.png", source.read_bytes(), "image/png")}
        response = client.post("/api/inspect", data=data, files=files)
        assert response.status_code == 201, response.text
        row = response.json()
        assert row["score"] == pytest.approx(expected_score)
        assert row["prediction"] == ("defective" if expected_score >= row["threshold"] else "normal")
        for url, mode in ((row["imageUrl"], "RGB"), (row["heatmapUrl"], "RGB"), (row["overlayUrl"], "RGBA")):
            with Image.open(BytesIO(client.get(url).content)) as actual:
                assert actual.size == (48, 32)
                assert actual.mode == mode
        cached = app.state.inference.cache["bottle"][1]
        assert client.post("/api/inspect", data=data, files=files).status_code == 201
        assert app.state.inference.cache["bottle"][1] is cached
        assert client.get("/api/evaluation/bottle").status_code == 200
        evaluation = client.get("/api/evaluation/bottle").json()
        assert evaluation["provenance"]["calibration"]["split"] == "held-out train/good"
        assert evaluation["provenance"]["test_count"] == 2
        assert evaluation["metrics"]["average_inference_latency_ms"] > 0
        assert evaluation["metrics"]["confusion_matrix"]
        assert (run / "roc.png").is_file() and (run / "confusion.png").is_file()
        sample_url = evaluation["provenance"]["samples"][0]["url"]
        assert "version=test-only" in sample_url
        with Image.open(BytesIO(client.get(sample_url).content)) as sample:
            assert sample.width == 768
        assert client.get("/api/evaluation/bottle/samples/1?version=other").status_code == 404
        Image.new("RGB", (2, 2)).save(run / "localization-1.png")
        assert client.get(sample_url).status_code == 404
        assert client.get(f"/api/inspections/{row['id']}").json() == row
        frame_response = client.post("/api/inspect/webcam", data=data, files=files)
        assert frame_response.status_code == 200, frame_response.text
        frame = frame_response.json()
        assert frame["score"] == pytest.approx(expected_score)
        assert frame["overlayUrl"].startswith("data:image/png;base64,")
        saved = client.post(f"/api/inspect/webcam/{frame['id']}/save").json()
        assert saved["score"] == frame["score"]
        assert client.get(saved["overlayUrl"]).status_code == 200
        submitted = client.post("/api/inspect/batch", data=data,
                                files={"files": files["file"]})
        assert submitted.status_code == 202, submitted.text
        job = submitted.json()
        deadline = monotonic() + 5
        while job["status"] == "processing" and monotonic() < deadline:
            sleep(0.025)
            job = client.get(submitted.headers["location"]).json()
        assert job["status"] == "completed"
        assert job["items"][0]["score"] == pytest.approx(expected_score)
    report_path = run / "evaluation.json"
    malformed_report = read_json(report_path)
    malformed_report["metrics"]["image_auroc"] = []
    write_json(report_path, malformed_report)
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/evaluation/bottle").status_code == 404
        assert next(row for row in client.get("/api/models").json() if row["category"] == "bottle")["ready"]
        (run / "patchcore.pt").unlink()
        unavailable = client.post("/api/inspect", data=data, files=files)
        assert unavailable.status_code == 503
        assert unavailable.json()["detail"]["code"] == "model_not_ready"
