"""Story 2.4 source-only negative fixtures; do not execute under current validation policy."""
import io
import json
import stat
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

import pytest
from PIL import Image

from edw_worker.template_assets import PackageRejected, validate_template_package


def manifest(assets=None):
    return {"schema_version": "1.0", "name": "开发模板", "description": "仅作开发示例",
            "category": "技术方案", "document_type": "technical_solution",
            "sections": [{"id": str(uuid4()), "title": "项目背景", "mandatory": True}],
            "rules": {name: None for name in (
                "retrieval_profile_id", "prompt_version_id", "reviewer_rule_version_id",
                "render_theme_version_id", "approval_policy_version_id")},
            "assets": assets or []}


def package(files):
    output = io.BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for name, contents in files:
            archive.writestr(name, contents)
    return output.getvalue()


def test_development_manifest_and_normalized_raster_asset():
    image = io.BytesIO()
    Image.new("RGB", (2, 3), (21, 51, 91)).save(image, format="PNG")
    raw = package([("manifest.json", json.dumps(manifest(["assets/cover.png"])).encode()),
                   ("assets/cover.png", image.getvalue())])
    checked = validate_template_package(raw)
    assert checked.development_only is True
    assert len(checked.manifest_sha256) == 64
    assert checked.assets[0].normalized_png.startswith(b"\x89PNG")
    assert checked.assets[0].width == 2


@pytest.mark.parametrize("filename", ["../outside.png", "assets/../outside.png", "/root/file.png",
                                      "C:/outside.png", "assets/evil.svg", "assets/evil.docm",
                                      "assets/sub/file.png", "assets/x\\y.png"])
def test_archive_paths_and_active_formats_fail_closed(filename):
    raw = package([("manifest.json", json.dumps(manifest()).encode()),
                   (filename, b"anything")])
    with pytest.raises(PackageRejected):
        validate_template_package(raw)


def test_self_extracting_prefix_and_trailing_payload_are_denied():
    raw = package([("manifest.json", json.dumps(manifest()).encode())])
    for tampered in (b"MZ" + raw, raw + b"payload"):
        with pytest.raises(PackageRejected) as rejected:
            validate_template_package(tampered)
        assert rejected.value.code == "UNSAFE_ARCHIVE"


def test_duplicate_or_colliding_entries_and_symlinks_are_denied():
    duplicated = package([("manifest.json", json.dumps(manifest()).encode()),
                          ("manifest.json", json.dumps(manifest()).encode())])
    with pytest.raises(PackageRejected):
        validate_template_package(duplicated)
    link = ZipInfo("assets/link.png")
    link.create_system = 3
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    raw = io.BytesIO()
    with ZipFile(raw, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest(["assets/link.png"])))
        archive.writestr(link, "outside")
    with pytest.raises(PackageRejected):
        validate_template_package(raw.getvalue())


def test_archive_bomb_and_ambiguous_manifest_rejected():
    bomb = package([("manifest.json", json.dumps(manifest(["assets/bomb.png"])).encode()),
                    ("assets/bomb.png", b"a" * (1024 * 1024))])
    with pytest.raises(PackageRejected):
        validate_template_package(bomb)
    duplicated_json = b'{"schema_version":"1.0","schema_version":"1.0"}'
    with pytest.raises(PackageRejected):
        validate_template_package(package([("manifest.json", duplicated_json)]))


def test_unknown_rules_and_image_extension_mismatch_rejected():
    m = manifest(["assets/sample.png"])
    m["rules"]["python_code"] = "__import__('os')"
    with pytest.raises(PackageRejected):
        validate_template_package(package([("manifest.json", json.dumps(m).encode()),
                                           ("assets/sample.png", b"not an image")]))
    m["rules"].pop("python_code")
    jpeg = io.BytesIO()
    Image.new("RGB", (2, 2)).save(jpeg, format="JPEG")
    with pytest.raises(PackageRejected) as rejected:
        validate_template_package(package([("manifest.json", json.dumps(m).encode()),
                                           ("assets/sample.png", jpeg.getvalue())]))
    assert rejected.value.code == "UNSUPPORTED_IMAGE"


def test_canonical_manifest_hash_independent_of_json_object_order():
    first = manifest()
    second = dict(reversed(list(first.items())))
    one = validate_template_package(package([("manifest.json", json.dumps(first).encode())]))
    two = validate_template_package(package([("manifest.json", json.dumps(second).encode())]))
    assert one.manifest_sha256 == two.manifest_sha256
    assert one.source_sha256 != two.source_sha256


def test_animated_raster_is_rejected_without_silent_frame_loss():
    manifest_data = manifest(["assets/animated.png"])
    image = io.BytesIO()
    Image.new("RGBA", (2, 2), (255, 0, 0, 255)).save(
        image, format="PNG", save_all=True,
        append_images=[Image.new("RGBA", (2, 2), (0, 0, 255, 255))], duration=100, loop=0)
    raw = package([("manifest.json", json.dumps(manifest_data).encode()),
                   ("assets/animated.png", image.getvalue())])
    with pytest.raises(PackageRejected) as rejected:
        validate_template_package(raw)
    assert rejected.value.code == "ANIMATED_IMAGE"


def test_invalid_raster_bytes_reject_after_valid_manifest():
    m = manifest(["assets/sample.png"])
    raw = package([("manifest.json", json.dumps(m).encode()),
                   ("assets/sample.png", b"not an image")])
    with pytest.raises(PackageRejected) as rejected:
        validate_template_package(raw)
    assert rejected.value.code == "INVALID_IMAGE"


def test_manifest_asset_inventory_mismatch_rejects():
    image = io.BytesIO()
    Image.new("RGB", (1, 1)).save(image, format="PNG")
    raw = package([("manifest.json", json.dumps(manifest()).encode()),
                   ("assets/extra.png", image.getvalue())])
    with pytest.raises(PackageRejected) as rejected:
        validate_template_package(raw)
    assert rejected.value.code == "INVALID_ASSETS"


@pytest.mark.parametrize("rule", ["retrieval_profile_id", "prompt_version_id",
                                  "reviewer_rule_version_id", "render_theme_version_id",
                                  "approval_policy_version_id"])
def test_syntactically_valid_rule_id_is_not_an_approved_reference(rule):
    value = manifest()
    value["rules"][rule] = str(uuid4())
    with pytest.raises(PackageRejected) as rejected:
        validate_template_package(package([("manifest.json", json.dumps(value).encode())]))
    assert rejected.value.code == "RULE_REGISTRY_UNAVAILABLE"
