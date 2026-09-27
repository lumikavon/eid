"""Bounded manual outline input; template requirement flags are never client input."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class OutlineSection(Strict):
    id: UUID
    title: str = Field(min_length=1, max_length=256)
    template_section_id: UUID | None = None

    @field_validator("title")
    @classmethod
    def clean_title(cls, value):
        value = value.strip()
        if not value or any(ord(char) < 32 or 0xD800 <= ord(char) <= 0xDFFF for char in value):
            raise ValueError("必须填写有效章节标题")
        return value


class OutlineSnapshot(Strict):
    sections: list[OutlineSection] = Field(min_length=1, max_length=128)


class SaveOutline(Strict):
    base_outline_version_id: UUID | None
    outline_revision: int = Field(ge=0, le=9007199254740990)
    document_version_id: UUID
    document_revision: int = Field(ge=1, le=9007199254740991)
    context_version_id: UUID
    template_version_id: UUID
    snapshot: OutlineSnapshot


class ConfirmOutline(Strict):
    version_id: UUID
    document_version_id: UUID
    document_revision: int = Field(ge=1, le=9007199254740991)
    context_version_id: UUID
    template_version_id: UUID
