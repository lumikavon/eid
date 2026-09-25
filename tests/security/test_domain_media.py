"""Story 2.2 private image normalization checks; execution deferred by policy."""

import base64
from hashlib import sha256
from io import BytesIO

import pytest
from PIL import Image

from edw_api.documents.media import MAX_IMAGE_BYTES, prepare_image
from edw_api.errors import ApiError


def image_bytes(kind="JPEG"):
    image = Image.new("RGB", (4, 3), (20, 30, 40))
    buffer = BytesIO()
    image.save(buffer, format=kind)
    return buffer.getvalue()


@pytest.mark.parametrize("kind", ["JPEG", "WEBP", "PNG"])
def test_bounded_image_is_reencoded_to_private_png_without_original_bytes(kind):
    source = image_bytes(kind)
    data, digest, width, height = prepare_image(base64.b64encode(source).decode("ascii"))
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(data) <= MAX_IMAGE_BYTES
    assert digest == sha256(data).hexdigest()
    assert (width, height) == (4, 3)
    with Image.open(BytesIO(data)) as normalized:
        assert normalized.format == "PNG"
        assert normalized.info.get("exif") is None


@pytest.mark.parametrize("payload", ["not-base64", base64.b64encode(b"<svg/>").decode(),
                                      base64.b64encode(b"not an image").decode(),
                                      "A" * 7_000_001])
def test_invalid_or_oversized_media_rejects_without_receipt(payload):
    with pytest.raises(ApiError) as error:
        prepare_image(payload)
    assert error.value.status_code == 422
