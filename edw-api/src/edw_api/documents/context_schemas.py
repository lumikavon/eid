"""Bounded, explicit manual project context wire types."""
import re
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


def text(value):
    value = value.strip()
    if not value or any(ord(char) < 32 or 0xD800 <= ord(char) <= 0xDFFF for char in value):
        raise ValueError("必须填写有效文本")
    return value


# Locators are inert manual notes, never object identifiers or fetch targets.
# This positive grammar excludes URI schemes, hosts with ports and paths while
# permitting ordinary document names such as requirements.pdf.
_MANUAL_LOCATION = re.compile(r"[\w .,'’\"()\[\]#\-，。、；（）【】《》]+")


class Source(Strict):
    locator: str = Field(min_length=1, max_length=512)
    resource_id: UUID | None = None

    @field_validator("locator")
    @classmethod
    def clean(cls, value):
        value = text(value)
        if not value.startswith("manual:"):
            raise ValueError("来源定位必须使用 manual: 手工文本；外部引用只使用资源 ID")
        location = text(value[len("manual:"):])
        if not _MANUAL_LOCATION.fullmatch(location):
            raise ValueError("来源定位只能填写手工文本；外部引用只使用资源 ID")
        return f"manual:{location}"


class Fact(Strict):
    key: str = Field(min_length=1, max_length=128)
    value: str = Field(min_length=1, max_length=2048)
    unit: str | None = Field(default=None, max_length=64)
    source: Source
    owner_id: UUID
    confirmed: bool = False

    @field_validator("key", "value")
    @classmethod
    def clean(cls, value):
        return text(value)

    @field_validator("unit")
    @classmethod
    def clean_unit(cls, value):
        return text(value) if value is not None else None


class Term(Strict):
    term: str = Field(min_length=1, max_length=128)
    definition: str = Field(min_length=1, max_length=2048)

    @field_validator("term", "definition")
    @classmethod
    def clean(cls, value):
        return text(value)


class Constraint(Strict):
    text: str = Field(min_length=1, max_length=2048)
    source: Source

    @field_validator("text")
    @classmethod
    def clean(cls, value):
        return text(value)


class Missing(Strict):
    key: str = Field(min_length=1, max_length=128)
    required: bool = True
    resolved: bool = False

    @field_validator("key")
    @classmethod
    def clean(cls, value):
        return text(value)


class ContextSnapshot(Strict):
    intent: str = Field(max_length=2048)
    facts: list[Fact] = Field(max_length=100)
    glossary: list[Term] = Field(max_length=100)
    constraints: list[Constraint] = Field(max_length=100)
    missing: list[Missing] = Field(max_length=100)
    zero_facts: bool = False

    @field_validator("intent")
    @classmethod
    def clean_intent(cls, value):
        return text(value) if value.strip() else ""

    @model_validator(mode="after")
    def consistent(self):
        if self.zero_facts and self.facts:
            raise ValueError("零事实声明不能包含事实")
        return self


class SaveContext(Strict):
    base_context_version_id: UUID | None
    context_revision: int = Field(ge=0, le=9007199254740990)
    document_version_id: UUID
    document_revision: int = Field(ge=1, le=9007199254740991)
    snapshot: ContextSnapshot


class ConfirmContext(Strict):
    version_id: UUID
    document_version_id: UUID
    document_revision: int = Field(ge=1, le=9007199254740991)
    zero_facts_acknowledged: bool = False


# Contract state values deliberately do not imply a generation or model workflow.
ContextState = Literal["CONTEXT_READY", "CONTEXT_PENDING"]
