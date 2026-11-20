from datetime import datetime
from types import SimpleNamespace

from PIL import Image

from app.config import Settings
from app.services.reports import inspection_pdf


def test_inspection_pdf_embeds_original_and_heatmap_and_handles_missing(tmp_path):
    Image.new("RGB", (320, 160), "blue").save(tmp_path / "original.png")
    Image.new("RGB", (320, 160), "red").save(tmp_path / "heatmap.png")
    record = SimpleNamespace(id="sample-001", prediction="defective", category="bottle",
                             created_at=datetime(2026, 11, 12, 12), source="upload",
                             filename="sample.png", model_version="fixture",
                             anomaly_score=0.8, threshold_used=0.5, original_image_path="original.png",
                             heatmap_path="heatmap.png", overlay_path=None)
    settings = Settings(image_storage=tmp_path)
    pdf = inspection_pdf(record, settings)
    assert pdf.startswith(b"%PDF")
    assert pdf.count(b"/Subtype /Image") == 2
    record.heatmap_path = "missing.png"
    assert inspection_pdf(record, settings).count(b"/Subtype /Image") == 1
    Image.new("RGBA", (320, 160), (255, 0, 0, 80)).save(tmp_path / "overlay.png")
    record.overlay_path = "overlay.png"
    assert b"/SMask " in inspection_pdf(record, settings)
