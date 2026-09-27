"""Deterministic, no-extraction validation of untrusted development template packages.

This is a Worker-side parser, not publication authority. Only JSON manifests and
raster images are accepted; DOCX, macros, SVG, HTML and executable templates are
intentionally unsupported until a separate sandbox/format policy is approved.
"""

from __future__ import annotations

import io
import json
import re
from dataclasses import dataclass
from hashlib import sha256
from uuid import UUID
from zipfile import BadZipFile, ZipFile

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_PACKAGE = 5 * 1024 * 1024
MAX_ENTRIES = 16
MAX_UNCOMPRESSED = 8 * 1024 * 1024
MAX_ASSET = 2 * 1024 * 1024
MAX_NORMALIZED = 8 * 1024 * 1024
MAX_MANIFEST = 128 * 1024
MAX_PIXELS = 8_000_000
ASSET_PATH = re.compile(r"assets/[a-z0-9][a-z0-9._-]{0,80}\.(?:png|jpe?g|webp)\Z")
RULE_KEYS = frozenset({"retrieval_profile_id", "prompt_version_id", "reviewer_rule_version_id",
                       "render_theme_version_id", "approval_policy_version_id"})
MANIFEST_KEYS = frozenset({"schema_version", "name", "description", "category",
                           "document_type", "sections", "rules", "assets"})
DOCUMENT_TYPES = frozenset({"technical_solution", "bid", "prd", "test_plan", "project_summary",
                            "technical_requirements", "quality_outline", "project_plan",
                            "functional_test_outline", "performance_test_outline",
                            "production_form"})


class PackageRejected(ValueError):
    """Untrusted bytes cannot become a template candidate; never include raw content."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class SafeAsset:
    name: str
    source_sha256: str
    normalized_png_sha256: str
    width: int
    height: int
    normalized_png: bytes


@dataclass(frozen=True)
class ValidatedPackage:
    source_sha256: str
    manifest_sha256: str
    manifest: dict
    assets: tuple[SafeAsset, ...]
    validator_version: str = "template-archive-v1"
    development_only: bool = True


def _text(value: object, maximum: int) -> bool:
    return (isinstance(value, str) and 1 <= len(value) <= maximum and value == value.strip()
            and not any(ord(char) < 32 or 0xD800 <= ord(char) <= 0xDFFF for char in value))


def _uuid(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        return str(UUID(value)) == value.lower()
    except ValueError:
        return False


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise PackageRejected("INVALID_MANIFEST")
        result[key] = value
    return result


def _manifest(raw: bytes) -> dict:
    try:
        manifest = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise PackageRejected("INVALID_MANIFEST") from exc
    if (not isinstance(manifest, dict) or set(manifest) != MANIFEST_KEYS
            or manifest["schema_version"] != "1.0"
            or not _text(manifest["name"], 256)
            or not isinstance(manifest["description"], str)
            or len(manifest["description"]) > 1024
            or any(ord(char) < 32 or 0xD800 <= ord(char) <= 0xDFFF
                   for char in manifest["description"])
            or not _text(manifest["category"], 128)
            or not isinstance(manifest["document_type"], str)
            or manifest["document_type"] not in DOCUMENT_TYPES):
        raise PackageRejected("INVALID_MANIFEST")
    sections = manifest["sections"]
    if not isinstance(sections, list) or not 1 <= len(sections) <= 64:
        raise PackageRejected("INVALID_SECTIONS")
    seen = set()
    for section in sections:
        if (not isinstance(section, dict) or set(section) != {"id", "title", "mandatory"}
                or not _uuid(section["id"]) or not _text(section["title"], 256)
                or type(section["mandatory"]) is not bool or section["id"] in seen):
            raise PackageRejected("INVALID_SECTIONS")
        seen.add(section["id"])
    rules = manifest["rules"]
    if (not isinstance(rules, dict) or set(rules) != RULE_KEYS
            or any(value is not None and not _uuid(value) for value in rules.values())):
        raise PackageRejected("INVALID_RULES")
    # UUID syntax is not authority. No approved rule registry exists in this delivery.
    if any(value is not None for value in rules.values()):
        raise PackageRejected("RULE_REGISTRY_UNAVAILABLE")
    assets = manifest["assets"]
    if (not isinstance(assets, list) or len(assets) > MAX_ENTRIES - 1
            or any(not isinstance(item, str) or not ASSET_PATH.fullmatch(item)
                   for item in assets) or len(set(assets)) != len(assets)):
        raise PackageRejected("INVALID_ASSETS")
    return manifest


def _normalize_image(name: str, raw: bytes) -> SafeAsset:
    try:
        with Image.open(io.BytesIO(raw)) as source:
            expected = {"png": "PNG", "jpg": "JPEG", "jpeg": "JPEG", "webp": "WEBP"}
            if source.format != expected[name.rsplit(".", 1)[-1]]:
                raise PackageRejected("UNSUPPORTED_IMAGE")
            if getattr(source, "is_animated", False) or getattr(source, "n_frames", 1) != 1:
                raise PackageRejected("ANIMATED_IMAGE")
            width, height = source.size
            if (width < 1 or height < 1 or width > 4096 or height > 4096
                    or width * height > MAX_PIXELS):
                raise PackageRejected("IMAGE_LIMIT")
            source.load()
            converted = ImageOps.exif_transpose(source).convert(
                "RGBA" if source.mode in {"RGBA", "LA"} or "transparency" in source.info else "RGB")
            # A fresh image removes EXIF, ICC and other untrusted metadata from previews.
            image = Image.new(converted.mode, converted.size)
            image.paste(converted)
            width, height = image.size
            result = io.BytesIO()
            image.save(result, format="PNG", optimize=False)
            normalized = result.getvalue()
    except PackageRejected:
        raise
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError, RecursionError,
            Image.DecompressionBombError) as exc:
        raise PackageRejected("INVALID_IMAGE") from exc
    if len(normalized) > MAX_ASSET:
        raise PackageRejected("IMAGE_LIMIT")
    return SafeAsset(name, sha256(raw).hexdigest(), sha256(normalized).hexdigest(),
                     width, height, normalized)


def validate_template_package(raw: bytes) -> ValidatedPackage:
    """Inspect a bounded ZIP without extracting paths or evaluating embedded content."""
    if not isinstance(raw, bytes) or not 1 <= len(raw) <= MAX_PACKAGE:
        raise PackageRejected("PACKAGE_LIMIT")
    # Reject self-extracting prefixes, comments and trailing payloads before ZipFile,
    # which otherwise tolerates bytes outside the declared archive.
    if not raw.startswith(b"PK\x03\x04") or len(raw) < 22 or raw[-22:-18] != b"PK\x05\x06":
        raise PackageRejected("UNSAFE_ARCHIVE")
    try:
        with ZipFile(io.BytesIO(raw), "r", allowZip64=False) as archive:
            entries = archive.infolist()
            if not 1 <= len(entries) <= MAX_ENTRIES:
                raise PackageRejected("PACKAGE_LIMIT")
            if sum(item.file_size for item in entries) > MAX_UNCOMPRESSED:
                raise PackageRejected("PACKAGE_LIMIT")
            names = set()
            blobs = {}
            for item in entries:
                name = item.filename
                kind = (item.external_attr >> 16) & 0o170000
                if (name != "manifest.json" and not ASSET_PATH.fullmatch(name)
                        or name.casefold() in names or item.is_dir()
                        or item.flag_bits & 1 or item.compress_type not in {0, 8}
                        or item.file_size > (MAX_MANIFEST if name == "manifest.json" else MAX_ASSET)
                        or item.file_size > 50 * max(1, item.compress_size)
                        or kind not in {0, 0o100000}):
                    raise PackageRejected("UNSAFE_ARCHIVE")
                names.add(name.casefold())
                with archive.open(item, "r") as stream:
                    data = stream.read(item.file_size + 1)
                if len(data) != item.file_size:
                    raise PackageRejected("UNSAFE_ARCHIVE")
                blobs[name] = data
    except (BadZipFile, OSError, ValueError, RuntimeError, EOFError) as exc:
        if isinstance(exc, PackageRejected):
            raise
        raise PackageRejected("UNSAFE_ARCHIVE") from exc
    if "manifest.json" not in blobs:
        raise PackageRejected("INVALID_MANIFEST")
    manifest = _manifest(blobs["manifest.json"])
    if set(manifest["assets"]) != set(blobs) - {"manifest.json"}:
        raise PackageRejected("INVALID_ASSETS")
    assets = []
    total_normalized = 0
    for name in manifest["assets"]:
        asset = _normalize_image(name, blobs.pop(name))
        total_normalized += len(asset.normalized_png)
        if total_normalized > MAX_NORMALIZED:
            raise PackageRejected("IMAGE_LIMIT")
        assets.append(asset)
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=False, allow_nan=False).encode("utf-8")
    return ValidatedPackage(sha256(raw).hexdigest(), sha256(canonical).hexdigest(),
                            manifest, tuple(assets))
