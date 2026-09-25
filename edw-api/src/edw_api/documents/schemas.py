"""Bounded public wire models for template selection and initial document creation."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .domain import DOCUMENT_TYPES, KNOWLEDGE_SCOPES


DocumentType = Literal[
    "technical_solution", "bid", "prd", "test_plan", "project_summary",
    "technical_requirements", "quality_outline", "project_plan",
    "functional_test_outline", "performance_test_outline", "production_form",
]
KnowledgeScope = Literal["project_only", "project_enterprise_quality", "all_authorized"]
TemplateScope = Literal["enterprise", "department", "product_line", "project", "personal"]


def normalized_name(value):
    if not isinstance(value, str):
        raise ValueError("文档名称必须为文本")
    value = value.strip()
    if (not value or len(value) > 256
            or any(ord(char) < 32 or 0xD800 <= ord(char) <= 0xDFFF for char in value)):
        raise ValueError("文档名称无效")
    return value


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TemplateFilters(StrictModel):
    scope: TemplateScope | None = None
    query: str | None = Field(default=None, max_length=128)
    category: str | None = Field(default=None, max_length=128)
    document_type: DocumentType | None = None

    @field_validator("query", "category", mode="before")
    @classmethod
    def normalize_filter(cls, value):
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("筛选参数必须为文本")
        value = value.strip()
        if not value or any(ord(char) < 32 or 0xD800 <= ord(char) <= 0xDFFF for char in value):
            raise ValueError("筛选参数无效")
        return value


class CreateDocument(StrictModel):
    name: str = Field(min_length=1, max_length=256)
    document_type: DocumentType
    knowledge_scope: KnowledgeScope
    template_version_id: UUID

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, value):
        return normalized_name(value)


class CreateDocumentAtWorkspace(CreateDocument):
    workspace_id: UUID


class CreateDocumentFromTemplate(StrictModel):
    workspace_id: UUID
    title: str = Field(min_length=1, max_length=256)
    document_type: DocumentType
    template_id: UUID
    knowledge_scope: KnowledgeScope = "project_only"

    @field_validator("title", mode="before")
    @classmethod
    def normalize_title(cls, value):
        return normalized_name(value)


class TypeItem(StrictModel):
    id: DocumentType
    label: str
    workflow_state: Literal["catalog_only"] = "catalog_only"


class KnowledgeScopeItem(StrictModel):
    id: KnowledgeScope
    label: str
    available: bool


class CatalogData(StrictModel):
    types: list[TypeItem]
    knowledge_scopes: list[KnowledgeScopeItem]


class CatalogResponse(StrictModel):
    data: CatalogData


class TemplateCard(StrictModel):
    template_id: UUID
    version_id: UUID
    name: str
    description: str
    scope: TemplateScope
    category: str
    document_type: DocumentType
    version_label: str
    development_only: Literal[True]
    outline: list[str]


class TemplateDetail(TemplateCard):
    structure: dict


class TemplateListData(StrictModel):
    items: list[TemplateCard]


class TemplateListResponse(StrictModel):
    data: TemplateListData


class TemplateDetailResponse(StrictModel):
    data: TemplateDetail


class AstDocument(BaseModel):
    model_config = ConfigDict(extra="allow")

    metadata: dict
    sections: list[dict]
    claims: list[dict]
    citations: list[dict]
    review_state: dict


class DomainAst(BaseModel):
    # Editors may add supported future nodes without dropping their source data.
    model_config = ConfigDict(extra="allow")

    schema_version: Literal["1.0"]
    document: AstDocument


class DocumentData(StrictModel):
    id: UUID
    workspace_id: UUID
    name: str
    document_type: DocumentType
    knowledge_scope: KnowledgeScope
    template_version_id: UUID
    version_id: UUID
    base_version_id: UUID | None
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    revision: Annotated[int, Field(ge=1, le=9007199254740991)]
    ast: DomainAst
    replayed: bool = False


class DocumentResponse(StrictModel):
    data: DocumentData


class DocumentVersionSummary(StrictModel):
    id: UUID
    revision: Annotated[int, Field(ge=1, le=9007199254740991)]
    base_version_id: UUID | None
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    created_by: UUID
    created_at: datetime
    source: Literal["template_create", "manual_edit"]


class DocumentVersionList(StrictModel):
    items: list[DocumentVersionSummary]
    next_revision: int | None


class DocumentVersionListResponse(StrictModel):
    data: DocumentVersionList


def catalog_items(available):
    return {"types": [{"id": key, "label": label, "workflow_state": "catalog_only"}
                      for key, label in DOCUMENT_TYPES],
            "knowledge_scopes": [{"id": key, "label": label, "available": key in available}
                                 for key, label in KNOWLEDGE_SCOPES]}


def contract_schema():
    models = (TemplateFilters, CreateDocument, CreateDocumentAtWorkspace,
              CreateDocumentFromTemplate, CatalogResponse, TemplateListResponse,
              TemplateDetailResponse, DocumentResponse)
    definitions = {}
    for model in models:
        schema = model.model_json_schema(ref_template="#/$defs/{model}")
        definitions.update(schema.pop("$defs", {}))
        definitions[model.__name__] = schema
    return {"$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "https://eid.local/contracts/template-creation.schema.json",
            "title": "模板选择与文档创建契约", "$defs": definitions,
            "oneOf": [{"$ref": f"#/$defs/{name}"} for name in
                      ("CatalogResponse", "TemplateListResponse", "TemplateDetailResponse",
                       "DocumentResponse")]}
