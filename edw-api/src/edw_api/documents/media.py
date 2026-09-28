"""Bounded image normalization and private object-store access for editor resources."""

import base64
from io import BytesIO
from hashlib import sha256

import boto3
from botocore.config import Config
from PIL import Image, ImageOps, UnidentifiedImageError

from ..errors import ApiError


MAX_IMAGE_BYTES = 5 * 1024 * 1024
Image.MAX_IMAGE_PIXELS = 16_000_000


def prepare_image(encoded: str):
    if not isinstance(encoded, str) or len(encoded) > 7_000_000:
        raise ApiError(422, "INVALID_DOCUMENT_MEDIA", "图片超过大小限制")
    try:
        original = base64.b64decode(encoded, validate=True)
        if not 0 < len(original) <= MAX_IMAGE_BYTES:
            raise ValueError("oversized")
        with Image.open(BytesIO(original)) as source:
            if source.format not in {"PNG", "JPEG", "WEBP"}:
                raise ValueError("unsupported")
            if (not 0 < source.width <= 8192 or not 0 < source.height <= 8192
                    or source.width * source.height > 16_000_000):
                raise ValueError("dimensions")
            image = ImageOps.exif_transpose(source)
            image.load()
            if image.mode not in {"RGB", "RGBA"}:
                image = image.convert("RGBA" if "A" in image.getbands() else "RGB")
            width, height = image.size
            output = BytesIO()
            image.save(output, format="PNG", optimize=True)
            data = output.getvalue()
        if not 0 < len(data) <= MAX_IMAGE_BYTES:
            raise ValueError("normalized image oversized")
    except (ValueError, OSError, UnidentifiedImageError, Image.DecompressionBombError) as exc:
        raise ApiError(422, "INVALID_DOCUMENT_MEDIA", "图片类型、尺寸或内容无效") from exc
    return data, sha256(data).hexdigest(), width, height


def object_client(settings, *, quarantine=False):
    return boto3.client("s3", endpoint_url=settings.s3_endpoint_url,
                        aws_access_key_id=settings.attachment_access_key if quarantine else settings.s3_access_key,
                        aws_secret_access_key=settings.attachment_secret_key if quarantine else settings.s3_secret_key,
                        config=Config(connect_timeout=2, read_timeout=5,
                                      retries={"max_attempts": 1}))
