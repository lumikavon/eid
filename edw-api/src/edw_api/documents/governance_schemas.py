"""模板治理命令及 Worker 校验收据；正式发布默认拒绝。"""
import base64
import binascii
from hashlib import sha256
import json
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .schemas import DocumentType, TemplateScope

Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @field_validator("confirmed", "development_only", mode="before", check_fields=False)
    @classmethod
    def explicit_true(cls, value):
        if value is not True:
            raise ValueError("Explicit boolean confirmation required")
        return value


class CandidateMetadata(StrictModel):
    template_id: UUID | None = None
    base_version_id: UUID | None = None
    version_label: str = Field(min_length=1, max_length=128)
    scope: TemplateScope
    classification: int = Field(ge=0, le=3)

    @field_validator("version_label")
    @classmethod
    def label(cls, value):
        if value != value.strip() or any(ord(c) < 32 or 0xD800 <= ord(c) <= 0xDFFF for c in value):
            raise ValueError("Invalid version label")
        return value

    @model_validator(mode="after")
    def base_pair(self):
        if self.template_id is None and self.base_version_id is not None:
            raise ValueError("A new family cannot reference an existing version")
        return self


class PublishCandidate(StrictModel):
    manifest_sha256: Digest
    mode: Literal["development", "formal"]
    confirmed: Literal[True]


class DeprecateVersion(StrictModel):
    reason: str = Field(min_length=1, max_length=512)
    confirmed: Literal[True]

    @field_validator("reason")
    @classmethod
    def reason_text(cls, value):
        if not value.strip() or any(ord(c) < 32 or 0xD800 <= ord(c) <= 0xDFFF for c in value):
            raise ValueError("Invalid reason")
        return value.strip()


class SectionRule(StrictModel):
    id: UUID
    title: str = Field(min_length=1, max_length=256)
    mandatory: bool = Field(strict=True)


class RuleReferences(StrictModel):
    retrieval_profile_id: UUID | None
    prompt_version_id: UUID | None
    reviewer_rule_version_id: UUID | None
    render_theme_version_id: UUID | None
    approval_policy_version_id: UUID | None


class Manifest(StrictModel):
    schema_version: Literal["1.0"]
    name: str = Field(min_length=1, max_length=256)
    description: str = Field(max_length=1024)
    category: str = Field(min_length=1, max_length=128)
    document_type: DocumentType
    sections: list[SectionRule] = Field(min_length=1, max_length=64)
    rules: RuleReferences
    assets: list[Annotated[str, Field(pattern=r"^assets/[a-z0-9][a-z0-9._-]{0,80}\.(png|jpe?g|webp)$")]] = Field(max_length=15)


class ReportAsset(StrictModel):
    name: str = Field(max_length=96)
    source_sha256: Digest
    sha256: Digest
    width: int = Field(strict=True, ge=1, le=4096)
    height: int = Field(strict=True, ge=1, le=4096)
    png_base64: str = Field(max_length=2796204)


class ValidationReport(StrictModel):
    source_sha256: Digest
    manifest_sha256: Digest
    validator_version: Literal["template-archive-v1"]
    development_only: Literal[True]
    manifest: Manifest
    assets: list[ReportAsset] = Field(max_length=15)

    @model_validator(mode="before")
    @classmethod
    def verify_original_manifest_hash(cls, value):
        if not isinstance(value, dict) or not isinstance(value.get("manifest"), dict):
            raise ValueError("Missing manifest")
        canonical = json.dumps(value["manifest"], sort_keys=True, separators=(",", ":"),
                               ensure_ascii=False, allow_nan=False).encode("utf-8")
        if sha256(canonical).hexdigest() != value.get("manifest_sha256"):
            raise ValueError("Manifest digest mismatch")
        return value

    @model_validator(mode="after")
    def assets_bound(self):
        names = [asset.name for asset in self.assets]
        if len(set(names)) != len(names) or names != self.manifest.assets:
            raise ValueError("Asset inventory mismatch")
        ids = [section.id for section in self.manifest.sections]
        if len(set(ids)) != len(ids):
            raise ValueError("Duplicate section identifiers")
        size = 0
        for asset in self.assets:
            try:
                raw = base64.b64decode(asset.png_base64, validate=True)
            except (binascii.Error, ValueError) as exc:
                raise ValueError("Invalid normalized asset receipt") from exc
            size += len(raw)
            if (len(raw) > 2 * 1024 * 1024 or not raw.startswith(b"\x89PNG\r\n\x1a\n")
                    or sha256(raw).hexdigest() != asset.sha256):
                raise ValueError("Invalid normalized asset receipt")
        if size > 8 * 1024 * 1024:
            raise ValueError("Asset receipt oversized")
        return self
