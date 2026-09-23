"""C-3 wire models shared by API and Worker; no transport or storage imports."""
import hashlib
import json
from datetime import datetime, timezone
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator, model_validator

MAX_ENVELOPE_BYTES = 8192
CONSUMER = "inventory-v1"
TASK_NAME = "eid.inventory.v1"
CATEGORIES = ("generation", "retrieval", "review", "parse_ocr", "render", "integration")
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
SafeInteger = Annotated[int, Field(strict=True, ge=1, le=9007199254740991)]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class InventoryInput(Contract):
    limit: Annotated[int, Field(strict=True, ge=1, le=50)] = 50


class SubmitTask(Contract):
    operation: Literal["inventory"]
    input: InventoryInput = Field(default_factory=InventoryInput)
    depends_on: list[UUID] = Field(default_factory=list, max_length=8)

    @field_validator("depends_on")
    @classmethod
    def unique_dependencies(cls, value):
        if len(set(value)) != len(value):
            raise ValueError("Duplicate dependency")
        return sorted(value, key=str)


class TaskEnvelope(Contract):
    message_schema_version: Literal["1.0"]
    source: Literal["eid-api"]
    event_id: UUID
    event_type: Literal["task.inventory.requested"]
    occurred_at: datetime
    aggregate_id: UUID
    aggregate_version: Literal[1]
    task_id: UUID
    category: Literal["integration"]
    input_ref: UUID
    input_hash: Digest
    actor_id: UUID
    workspace_id: UUID
    delegation_id: UUID
    request_id: Annotated[str, Field(pattern=r"^[A-Za-z0-9._-]{1,128}$")]
    trace_id: Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")]

    @model_validator(mode="after")
    def bindings(self):
        if self.aggregate_id != self.task_id or self.input_ref != self.task_id:
            raise ValueError("Task reference mismatch")
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset().total_seconds() != 0:
            raise ValueError("UTC timestamp required")
        if self.trace_id == "0" * 32:
            raise ValueError("Trace identifier required")
        return self


class InventoryItem(Contract):
    resource_id: UUID
    kind: Literal["document", "knowledge", "reference"]
    revision: SafeInteger
    resource_epoch: SafeInteger


class InventoryResult(Contract):
    result_id: UUID
    task_id: UUID
    workspace_id: UUID
    measured_at: datetime
    scope: Literal["first_authorized_visible_records"]
    limit: Annotated[int, Field(strict=True, ge=1, le=50)]
    items: list[InventoryItem] = Field(max_length=50)
    policy_epoch: tuple[SafeInteger, SafeInteger, SafeInteger]


class TaskSnapshot(Contract):
    task_id: UUID
    state: Literal["QUEUED", "RUNNING", "SUCCEEDED", "BLOCKED"]
    stage: Literal["waiting", "inventory", "done", "blocked"]
    category: Literal["integration"]
    operation: Literal["inventory"]
    attempt: Annotated[int, Field(strict=True, ge=0, le=9007199254740991)]
    current_seq: SafeInteger
    progress: None = None
    result_ref: UUID | None
    error: Literal[
        "AUTHORIZATION_EXPIRED_OR_REVOKED", "DEPENDENCY_BLOCKED", "INVALID_INVENTORY_INPUT"
    ] | None
    created_at: datetime
    updated_at: datetime
    status_url: str
    result_url: str


class TaskResponse(Contract):
    data: TaskSnapshot


class ResultResponse(Contract):
    data: InventoryResult


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf8")


def payload_hash(value) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def parse_envelope(value) -> TaskEnvelope:
    if len(canonical(value)) > MAX_ENVELOPE_BYTES:
        raise ValueError("Envelope exceeds limit")
    return TaskEnvelope.model_validate(value)


def wire_time(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def contract_schema():
    schema = TypeAdapter(SubmitTask | TaskEnvelope | TaskResponse | ResultResponse).json_schema()
    return {"$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "https://eid.local/contracts/task.schema.json", **schema}
