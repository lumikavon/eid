"""发现接口的有界输入、响应及共享 JSON Schema。"""
from datetime import datetime, timedelta
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    AfterValidator, AwareDatetime, BaseModel, ConfigDict, Field, StrictBool,
    StrictInt, field_validator,
)


def utc_only(value: datetime) -> datetime:
    if value.utcoffset() != timedelta(0):
        raise ValueError("时间必须为 UTC")
    return value


UtcTime = Annotated[AwareDatetime, AfterValidator(utc_only)]
Positive = Annotated[StrictInt, Field(ge=1, le=9007199254740991)]
Nonnegative = Annotated[StrictInt, Field(ge=0, le=9007199254740991)]
Epoch = Annotated[list[Positive], Field(min_length=3, max_length=3)]
Kind = Literal["document", "knowledge", "reference"]
DocumentType = Literal["technical", "proposal", "report", "manual", "other"]
Lifecycle = Literal["DRAFT", "IN_REVIEW", "APPROVED", "ARCHIVED"]
Visibility = Literal["visible", "recycled"]
Tab = Literal["recent", "created", "participating", "favorites"]
Collection = Literal["all", "todo", "references"]
ShortText = Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[^\x00]+$")]
Cursor = Annotated[str, Field(min_length=1, max_length=2048, pattern=r"^[A-Za-z0-9_-]+$")]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Filters(StrictModel):
    tab: Tab = "recent"
    collection: Collection = "all"
    kind: Kind | None = None
    document_type: DocumentType | None = None
    lifecycle: Lifecycle | None = None
    visibility: Visibility = "visible"
    limit: int = Field(default=20, ge=1, le=50)
    cursor: Cursor | None = None


class SearchRequest(Filters):
    limit: int = Field(default=20, ge=1, le=50, strict=True)
    query: str = Field(min_length=1, max_length=128, pattern=r"^[^\x00]+$")

    @field_validator("query", mode="before")
    @classmethod
    def trim_query(cls, value):
        if not isinstance(value, str):
            raise ValueError("关键词必须为文本")
        return value.strip()


class FavoriteCommand(StrictModel):
    favorite: StrictBool
    expected_revision: Nonnegative


class RestoreCommand(StrictModel):
    expected_revision: Positive
    policy_version: ShortText


class Context(StrictModel):
    actor_id: UUID
    workspace_id: UUID
    policy_epoch: Epoch


class Item(StrictModel):
    id: UUID
    workspace_id: UUID
    title: str = Field(min_length=1, max_length=512)
    kind: Kind
    document_type: DocumentType | None
    lifecycle: Lifecycle
    visibility: Visibility
    created_by: UUID
    created_at: UtcTime
    updated_at: UtcTime
    version_label: str | None = Field(max_length=128)
    revision: Positive
    resource_epoch: Positive
    favorite: StrictBool
    favorite_revision: Nonnegative
    participating: StrictBool


class Storage(StrictModel):
    metadata_bytes: Nonnegative
    measured_at: UtcTime
    scope: Literal["authorized_filtered_record_metadata"]
    definition: Literal["pg_column_size(discovery_record)+pg_column_size(access_resource.title)"]
    visibility: Visibility
    attachment_bytes: None = None
    quota_bytes: None = None


class Page(StrictModel):
    items: list[Item] = Field(max_length=50)
    total_count: Nonnegative
    next_cursor: Cursor | None
    context: Context
    storage: Storage


class ListResponse(StrictModel):
    data: Page


class FunctionResult(StrictModel):
    id: Literal["documents", "favorites", "references", "recycle", "project"]
    title: str = Field(min_length=1, max_length=128)
    route: Literal["documents", "favorites", "references", "recycle", "project"]
    workspace_id: UUID


class SearchPage(Page):
    functions: list[FunctionResult] = Field(max_length=5)


class SearchResponse(StrictModel):
    data: SearchPage


class Actions(StrictModel):
    favorite: StrictBool
    restore: StrictBool
    restore_policy_version: ShortText | None


class Detail(StrictModel):
    item: Item
    context: Context
    resource_context: Context
    actions: Actions
    content_state: Literal["metadata_only"]


class DetailResponse(StrictModel):
    data: Detail


class Workspace(StrictModel):
    id: UUID
    name: str = Field(max_length=512)
    slug: str = Field(max_length=128)
    project_id: ShortText
    customer_id: ShortText
    product_id: ShortText
    department: ShortText
    classification: int = Field(ge=0, le=3, strict=True)


class WeekMetric(StrictModel):
    value: Nonnegative
    window_start: UtcTime
    window_end: UtcTime
    definition: Literal["authorized_filtered_documents_created_since_utc_monday"]


class FuturePanel(StrictModel):
    id: Literal["review", "ai_words", "quality", "templates", "recommendations", "creation"]
    value: None = None
    state: Literal["not_collected", "not_evaluated", "unavailable"]
    reason: str = Field(min_length=1, max_length=256)
    owner: str = Field(min_length=1, max_length=32)


class Summary(StrictModel):
    context: Context
    workspace: Workspace
    total_count: Nonnegative
    storage: Storage
    week_new_documents: WeekMetric
    todo_count: Nonnegative
    last_activity_at: UtcTime | None
    future_panels: list[FuturePanel] = Field(min_length=6, max_length=6)


class SummaryResponse(StrictModel):
    data: Summary


class Receipt(StrictModel):
    operation_id: UUID
    action: Literal["favorite.set", "restore_visibility"]
    resource_id: UUID
    replayed: StrictBool
    occurred_at: UtcTime
    context: Context
    # 始终是锁内当前状态，历史回执只保留操作身份。
    current: Item


class CommandResponse(StrictModel):
    data: Receipt


def contract_schema():
    models = (Filters, SearchRequest, FavoriteCommand, RestoreCommand, ListResponse,
              SearchResponse, DetailResponse, SummaryResponse, CommandResponse)
    definitions = {}
    for model in models:
        schema = model.model_json_schema(ref_template="#/$defs/{model}")
        definitions.update(schema.pop("$defs", {}))
        definitions[model.__name__] = schema
    return {"$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "https://eid.local/contracts/discovery.schema.json",
            "title": "工作区发现契约", "$defs": definitions,
            "oneOf": [{"$ref": f"#/$defs/{name}"} for name in
                      ("ListResponse", "SearchResponse", "DetailResponse", "SummaryResponse",
                       "CommandResponse")]}
