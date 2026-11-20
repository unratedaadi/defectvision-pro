from io import BytesIO
from pathlib import Path

from fastapi import UploadFile
from fastapi.responses import JSONResponse
from PIL import Image, ImageOps, UnidentifiedImageError
from starlette.datastructures import Headers
from starlette.formparsers import MultiPartException
from starlette.types import ASGIApp, Receive, Scope, Send

from app.config import ROOT, Settings
from app.errors import ApiError

FORMATS = ("JPEG", "PNG", "WEBP")


class UploadBodyLimit:
    def __init__(self, app: ASGIApp, settings: Settings):
        self.app = app
        self.settings = settings

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http" or scope["method"] != "POST":
            await self.app(scope, receive, send)
            return
        path = scope["path"].rstrip("/")
        if path not in {"/api/inspect", "/api/inspect/batch", "/api/inspect/webcam"}:
            await self.app(scope, receive, send)
            return
        count = self.settings.max_batch_images if path.endswith("/batch") else 1
        limit = count * self.settings.max_upload_bytes + 64 * 1024
        received = 0
        exceeded = False
        rejected = JSONResponse({"detail": {
            "code": "request_too_large", "message": "Multipart request exceeds the configured upload limit.",
        }}, status_code=413)
        length = Headers(scope=scope).get("content-length", "")
        if length.isascii() and length.isdecimal() and (len(length) > 18 or int(length) > limit):
            await rejected(scope, receive, send)
            return

        async def bounded_receive():
            nonlocal received, exceeded
            message = await receive()
            received += len(message.get("body", b""))
            if received > limit:
                exceeded = True
                # Let the multipart parser close any files it has already opened.
                raise MultiPartException("Multipart request exceeded the upload limit.")
            return message

        async def bounded_send(message):
            if not exceeded:
                await send(message)
            elif message["type"] == "http.response.start":
                await rejected(scope, receive, send)

        await self.app(scope, bounded_receive, bounded_send)


def display_name(upload: UploadFile) -> str:
    name = (upload.filename or "image").replace("\\", "/").rsplit("/", 1)[-1]
    return "".join(c for c in name if c.isprintable())[:255] or "image"


def decode(upload: UploadFile, settings: Settings, *, pixel_limit: int | None = None) -> Image.Image:
    content = upload.file.read(settings.max_upload_bytes + 1)
    if len(content) > settings.max_upload_bytes:
        raise ApiError(413, "file_too_large", "Image exceeds the configured file-size limit.")
    try:
        with Image.open(BytesIO(content), formats=FORMATS) as image:
            if image.width * image.height > min(settings.max_image_pixels, pixel_limit or settings.max_image_pixels):
                raise ApiError(413, "image_too_large", "Image exceeds the configured pixel limit.")
            if getattr(image, "is_animated", False):
                raise ApiError(422, "invalid_image", "Upload a single-frame image.")
            pixels = ImageOps.exif_transpose(image).convert("RGB")
            clean = Image.new("RGB", pixels.size)
            clean.paste(pixels)
            return clean
    except Image.DecompressionBombError as error:
        raise ApiError(413, "image_too_large", "Image exceeds safe decoding limits.") from error
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError) as error:
        raise ApiError(422, "invalid_image", "Upload a readable JPEG, PNG, or WebP image.") from error


def storage_path(settings: Settings, name: str) -> Path:
    root = (ROOT / settings.image_storage.expanduser()).resolve()
    path = (root / name).resolve()
    if path.parent != root:
        raise ApiError(404, "image_not_found", "Image is unavailable.")
    return path
