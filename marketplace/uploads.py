"""Decoded image validation and immutable storage for listings and private evidence."""
from __future__ import annotations

import hashlib
import io
import warnings
from pathlib import Path
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.exceptions import RequestDataTooBig
from django.core.files.uploadhandler import FileUploadHandler
from PIL import Image, UnidentifiedImageError

FORMATS = {"JPEG": ("image/jpeg", ".jpg"), "PNG": ("image/png", ".png"), "WEBP": ("image/webp", ".webp")}


class BoundedUploadHandler(FileUploadHandler):
    """Bound streamed file bytes before memory/tempfile handlers consume them."""
    def __init__(self, request=None):
        super().__init__(request)
        self.total_bytes = 0

    def handle_raw_input(self, input_data, META, content_length, boundary, encoding=None):
        if content_length and content_length > settings.DATA_UPLOAD_MAX_MEMORY_SIZE:
            raise RequestDataTooBig("The upload request exceeds the configured limit.")

    def receive_data_chunk(self, raw_data, start):
        self.total_bytes += len(raw_data)
        if self.total_bytes > settings.DATA_UPLOAD_MAX_MEMORY_SIZE:
            raise RequestDataTooBig("The streamed upload exceeds the configured limit.")
        return raw_data

    def file_complete(self, file_size):
        return None


def validate_image(upload):
    """Read a bounded stream, decode its actual format, and strip embedded metadata."""
    limit = settings.UPLOAD_MAX_BYTES
    content = upload.read(limit + 1)
    if not content or len(content) > limit:
        raise ValidationError("Each image must contain between 1 byte and 5 MiB.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(content)) as image:
                image_format = image.format
                if image_format not in FORMATS or getattr(image, "n_frames", 1) != 1:
                    raise ValidationError("Use a single-frame JPEG, PNG or WebP image.")
                width, height = image.size
                if width <= 0 or height <= 0 or width * height > settings.UPLOAD_MAX_PIXELS:
                    raise ValidationError("The image dimensions exceed the configured limit.")
                image.verify()
            with Image.open(io.BytesIO(content)) as image:
                image.load()
                clean = image.convert("RGB" if image_format == "JPEG" else "RGBA")
                output = io.BytesIO()
                clean.save(output, format=image_format)
                content = output.getvalue()
    except ValidationError:
        raise
    except (OSError, ValueError, SyntaxError, UnidentifiedImageError, Image.DecompressionBombWarning,
            Image.DecompressionBombError) as exc:
        raise ValidationError("This file is not a valid supported image.") from exc
    if len(content) > limit:
        raise ValidationError("The decoded image exceeds the configured size limit.")
    mime, suffix = FORMATS[image_format]
    return {"content": content, "content_type": mime, "suffix": suffix, "byte_size": len(content),
            "content_sha256": hashlib.sha256(content).hexdigest(), "width": width, "height": height}


def _path(storage_key, private=False):
    root = Path(settings.PRIVATE_MEDIA_ROOT if private else settings.MEDIA_ROOT).resolve()
    target = (root / storage_key).resolve()
    if root not in target.parents:
        raise ValidationError("Invalid storage reference.")
    return target


def store_image(validated, private=False):
    key = f"{'private' if private else 'listings'}/{uuid4().hex}{validated['suffix']}"
    path = _path(key, private)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(validated["content"])
    return {name: validated[name] for name in ("content_type", "byte_size", "content_sha256", "width", "height")} | {"storage_key": key}


def copy_stored_image(metadata, source_private=False):
    path = _path(metadata["storage_key"], source_private)
    with path.open("rb") as stream:
        content = stream.read(settings.UPLOAD_MAX_BYTES + 1)
    if len(content) != metadata["byte_size"] or hashlib.sha256(content).hexdigest() != metadata["content_sha256"]:
        raise ValidationError("Stored image verification failed. Upload a replacement.")
    suffix = next(suffix for mime, suffix in FORMATS.values() if mime == metadata["content_type"])
    return store_image(metadata | {"content": content, "suffix": suffix})


def remove_stored(metadata, private=False):
    """Only for newly written rollback files or consumed private draft files."""
    _path(metadata["storage_key"], private).unlink(missing_ok=True)
