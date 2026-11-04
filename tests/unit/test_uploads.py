import io

import pytest
from django.core.exceptions import RequestDataTooBig, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from marketplace.uploads import BoundedUploadHandler, _path, copy_stored_image, store_image, validate_image


def image_upload(size=(8, 8), name="example.png"):
    buffer = io.BytesIO()
    Image.new("RGB", size, color="blue").save(buffer, format="PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="text/plain")


def test_decoded_image_type_and_immutable_copy(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path / "public"
    settings.PRIVATE_MEDIA_ROOT = tmp_path / "private"
    validated = validate_image(image_upload(name="untrusted.exe"))
    assert validated["content_type"] == "image/png"
    assert validated["width"] == 8
    first = store_image(validated, private=True)
    second = copy_stored_image(first, source_private=True)
    assert first["storage_key"] != second["storage_key"]
    assert _path(first["storage_key"], True).is_file()
    assert _path(second["storage_key"]).read_bytes() == validated["content"]
    _path(first["storage_key"], True).write_bytes(b"tampered")
    with pytest.raises(ValidationError, match="verification"):
        copy_stored_image(first, source_private=True)
    with pytest.raises(ValidationError, match="Invalid storage"):
        _path("../../outside")


def test_malformed_oversized_and_dimension_limited_images(settings):
    with pytest.raises(ValidationError, match="valid supported"):
        validate_image(SimpleUploadedFile("x.png", b"<script>bad</script>"))
    settings.UPLOAD_MAX_BYTES = 10
    with pytest.raises(ValidationError, match="5 MiB"):
        validate_image(image_upload())
    settings.UPLOAD_MAX_BYTES = 5242880
    settings.UPLOAD_MAX_PIXELS = 4
    with pytest.raises(ValidationError, match="dimensions"):
        validate_image(image_upload())


def test_streamed_aggregate_limit_does_not_trust_header(settings):
    settings.DATA_UPLOAD_MAX_MEMORY_SIZE = 10
    handler = BoundedUploadHandler()
    handler.handle_raw_input(None, {}, 5, None)
    assert handler.receive_data_chunk(b"123456", 0) == b"123456"
    with pytest.raises(RequestDataTooBig):
        handler.receive_data_chunk(b"12345", 0)
    with pytest.raises(RequestDataTooBig):
        BoundedUploadHandler().handle_raw_input(None, {}, 11, None)
