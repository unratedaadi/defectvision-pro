from io import BytesIO

from PIL import Image
from reportlab.lib.colors import HexColor
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas

from app.errors import ApiError
from app.models import CATEGORIES
from app.services.images import storage_path

NAVY = HexColor("#12243a")
MUTED = HexColor("#425670")
PAPER = HexColor("#edf3f9")
DISCLAIMER = "Automated predictions require independent verification for safety-critical manufacturing."


def header(canvas, title):
    canvas.setTitle(f"DefectVision Pro | {title}")
    canvas.setFillColor(NAVY)
    canvas.rect(0, 732, 612, 60, fill=1, stroke=0)
    canvas.setFillColor(HexColor("#ffffff"))
    canvas.setFont("Helvetica-Bold", 20)
    canvas.drawString(40, 754, "DefectVision Pro")
    canvas.setFont("Helvetica", 11)
    canvas.drawRightString(572, 755, title)
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 9)
    canvas.drawString(40, 46, DISCLAIMER)
    canvas.drawRightString(572, 29, f"Page {canvas.getPageNumber()}")


def label(canvas, x, y, title, value, limit=51):
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 9)
    canvas.drawString(x, y, title)
    canvas.setFillColor(NAVY)
    canvas.setFont("Helvetica-Bold", 11)
    text = str(value)
    while canvas.stringWidth(text, "Helvetica-Bold", 11) > limit * 5.1:
        text = text[:-4] + "..."
    canvas.drawString(x, y - 16, text)


def panel(canvas, settings, x, title, name, *, background=None):
    canvas.setFillColor(NAVY)
    canvas.setFont("Helvetica-Bold", 12)
    canvas.drawString(x, 521, title)
    canvas.setFillColor(PAPER)
    canvas.roundRect(x, 287, 258, 220, 7, fill=1, stroke=0)
    if name:
        try:
            with Image.open(storage_path(settings, name)) as pixels:
                pixels.thumbnail((1040, 880))
                if background:
                    try:
                        with Image.open(storage_path(settings, background)) as original:
                            original = original.convert("RGB").resize(pixels.size, Image.Resampling.LANCZOS)
                            canvas.drawImage(ImageReader(original), x + 8, 295,
                                             width=242, height=204, preserveAspectRatio=True, anchor="c")
                    except (OSError, ValueError, Image.DecompressionBombError, ApiError):
                        pass
                mode = "RGBA" if "A" in pixels.getbands() or "transparency" in pixels.info else "RGB"
                canvas.drawImage(ImageReader(pixels.convert(mode)), x + 8, 295,
                                 width=242, height=204, preserveAspectRatio=True, anchor="c", mask="auto")
                return True
        except (OSError, ValueError, Image.DecompressionBombError, ApiError):
            pass
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 10)
    canvas.drawCentredString(x + 129, 393, "Image unavailable")
    return False


def inspection_pdf(record, settings):
    output = BytesIO()
    canvas = Canvas(output, pagesize=(612, 792))
    header(canvas, "Inspection report")
    defective = record.prediction == "defective"
    canvas.setFillColor(HexColor("#8b2441" if defective else "#176052"))
    canvas.roundRect(40, 667, 532, 39, 7, fill=1, stroke=0)
    canvas.setFont("Helvetica-Bold", 15)
    canvas.setFillColor(HexColor("#ffffff"))
    canvas.drawString(53, 680, record.prediction.upper())
    label(canvas, 40, 642, "Inspection ID", record.id)
    label(canvas, 314, 642, "Inspected at", f"{record.created_at:%Y-%m-%d %H:%M:%S} UTC")
    label(canvas, 40, 602, "Product category", dict(CATEGORIES).get(record.category, record.category))
    label(canvas, 314, 602, "AI model version", record.model_version)
    label(canvas, 40, 562, "Inspection source", record.source.capitalize())
    label(canvas, 314, 562, "Original filename", record.filename)
    panel(canvas, settings, 40, "Original product image", record.original_image_path)
    if not panel(canvas, settings, 314, "Defect heatmap", record.heatmap_path) and record.overlay_path:
        # The heatmap is the primary report layer. Older records may have only an overlay.
        canvas.setFillColor(HexColor("#ffffff"))
        canvas.rect(314, 284, 258, 251, fill=1, stroke=0)
        panel(canvas, settings, 314, "Defect overlay", record.overlay_path, background=record.original_image_path)
    label(canvas, 40, 252, "Raw anomaly score", record.anomaly_score)
    label(canvas, 314, 252, "Applied decision threshold", record.threshold_used)
    canvas.save()
    return output.getvalue()


def batch_pdf(job, items):
    output = BytesIO()
    canvas = Canvas(output, pagesize=(612, 792))
    for offset in range(0, max(1, len(items)), 24):
        header(canvas, "Batch inspection summary")
        label(canvas, 40, 700, "Batch ID", job.id)
        label(canvas, 314, 700, "Category", dict(CATEGORIES).get(job.category, job.category))
        label(canvas, 40, 655, "Status", job.status.capitalize())
        label(canvas, 314, 655, "Processed / failed / submitted", f"{job.processed_images} / {job.failed_images} / {job.total_images}")
        label(canvas, 40, 606, "Inspection ID", "")
        label(canvas, 314, 606, "Prediction", "")
        label(canvas, 458, 606, "Raw score", "")
        for index, row in enumerate(items[offset:offset + 24]):
            y = 581 - index * 20
            if index % 2 == 0:
                canvas.setFillColor(PAPER)
                canvas.rect(40, y - 5, 532, 18, fill=1, stroke=0)
            canvas.setFillColor(NAVY)
            canvas.setFont("Helvetica", 9)
            canvas.drawString(45, y, row.id)
            canvas.drawString(314, y, row.prediction.capitalize())
            canvas.drawString(458, y, str(row.score))
        if not items:
            canvas.drawString(40, 580, "No saved inspection results.")
        canvas.showPage()
    canvas.save()
    return output.getvalue()
