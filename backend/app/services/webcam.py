from base64 import b64encode
from collections import OrderedDict
from dataclasses import dataclass
from io import BytesIO
from threading import Lock
from time import monotonic

from PIL import Image

from app.errors import ApiError
from app.models import Inspection
from app.schemas.inspection import WebcamPreview
from app.services import inspections as service

FRAME_TTL = 300
FRAME_LIMIT = 8


@dataclass
class Frame:
    record: Inspection
    image: Image.Image
    result: service.InferenceResult
    expires: float


def image_url(image):
    if image is None:
        return None
    with BytesIO() as buffer:
        image.save(buffer, format="PNG")
        return "data:image/png;base64," + b64encode(buffer.getvalue()).decode("ascii")


class WebcamFrames:
    def __init__(self):
        self.frames: OrderedDict[str, Frame] = OrderedDict()
        self.cache_lock = Lock()
        self.inference_slot = Lock()

    def prune(self):
        now = monotonic()
        while self.frames and next(iter(self.frames.values())).expires <= now:
            self.frames.popitem(last=False)

    def preview(self, adapter, model, image, filename):
        if not self.inference_slot.acquire(blocking=False):
            raise ApiError(429, "webcam_busy", "A camera frame is already being inspected.")
        try:
            result = service.infer(adapter, model, image)
            record = service.new_inspection(model, result, filename, "webcam")
            payload = service.serialize(record).model_dump()
            payload.update(imageUrl=image_url(image), heatmapUrl=image_url(result.heatmap),
                           overlayUrl=image_url(result.overlay))
            with self.cache_lock:
                self.prune()
                if len(self.frames) >= FRAME_LIMIT:
                    self.frames.popitem(last=False)
                self.frames[record.id] = Frame(record, image, result, monotonic() + FRAME_TTL)
            return WebcamPreview(**payload, expiresIn=FRAME_TTL)
        finally:
            self.inference_slot.release()

    def save(self, frame_id, db, settings):
        with self.cache_lock:
            existing = db.get(Inspection, frame_id)
            if existing is not None and existing.source == "webcam":
                return service.serialize(existing)
            self.prune()
            frame = self.frames.get(frame_id)
            if frame is None:
                raise ApiError(404, "frame_expired", "This frame expired. Capture a new frame to save.")
            record = service.save_inspection(db, settings, frame.record, frame.image, frame.result)
            self.frames.pop(frame_id)
            return service.serialize(record)
