"""C-3 wire models shared by API and Worker; no transport or storage imports."""
import hashlib
import json
from datetime import datetime, timezone
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, TypeAdapter, field_validator, model_validator

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
    state: Literal["QUEUED", "RUNNING", "RETRY_WAIT", "SUCCEEDED", "BLOCKED", "FAILED",
                   "CANCELLED", "DEAD_LETTER"]
    stage: Literal["waiting", "inventory", "working", "retry_wait", "done", "blocked", "failed",
                   "cancelled", "dead_letter"]
    category: Literal["generation", "retrieval", "review", "parse_ocr", "render", "integration"]
    operation: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")]
    parent_task_id: UUID | None = None
    attempt: Annotated[int, Field(strict=True, ge=0, le=9007199254740991)]
    fence_token: Annotated[int, Field(strict=True, ge=0, le=9007199254740991)] = 0
    current_seq: SafeInteger
    retention_floor: SafeInteger = 1
    progress: None = None
    result_ref: UUID | None
    error: Literal[
        "AUTHORIZATION_EXPIRED_OR_REVOKED", "DEPENDENCY_BLOCKED", "INVALID_INVENTORY_INPUT",
        "TRANSIENT_DEPENDENCY", "FORMAT_REPAIRABLE", "LEASE_EXPIRED", "ATTEMPTS_EXHAUSTED",
        "CANCELLED_BY_ACTOR", "OUTBOX_POISONED"
    ] | None
    error_class: Literal[
        "TRANSIENT", "FORMAT", "PERMANENT", "LEASE_EXPIRED", "ATTEMPTS_EXHAUSTED"
    ] | None = None
    next_retry_at: datetime | None = None
    cancel_requested: StrictBool = False
    external_effect_state: Literal["none", "receipt_pending", "unknown", "confirmed"] = "none"
    created_at: datetime
    updated_at: datetime
    status_url: str
    result_url: str | None
    can_cancel: StrictBool = False
    can_retry: StrictBool = False
    action_reason: Literal[
        "OPERATION_UNAVAILABLE", "EXTERNAL_EFFECT_UNKNOWN", "TASK_TERMINAL",
        "TASK_NOT_TERMINAL"
    ] | None = None

    @model_validator(mode="after")
    def state_bindings(self):
        stages = {
            "QUEUED": "waiting", "RETRY_WAIT": "retry_wait",
            "SUCCEEDED": "done", "BLOCKED": "blocked", "FAILED": "failed",
            "CANCELLED": "cancelled", "DEAD_LETTER": "dead_letter",
        }
        inventory = self.operation == "inventory" and self.category == "integration"
        expected_stage = ("inventory" if inventory else "working") if self.state == "RUNNING" else stages[self.state]
        if self.stage != expected_stage:
            raise ValueError("Task state and stage mismatch")
        if inventory != (self.result_url is not None):
            raise ValueError("Task result URL and handler mismatch")
        if (self.state == "SUCCEEDED") != (self.result_ref is not None):
            raise ValueError("Task result and state mismatch")
        if (self.state in {"BLOCKED", "FAILED", "DEAD_LETTER"}) != (self.error is not None):
            raise ValueError("Task error and state mismatch")
        if (self.state == "RETRY_WAIT") != (self.next_retry_at is not None):
            raise ValueError("Task retry plan and state mismatch")
        return self


class TaskResponse(Contract):
    data: TaskSnapshot


class TaskPage(Contract):
    data: list[TaskSnapshot] = Field(max_length=25)
    next_cursor: UUID | None = None


class TaskEventView(Contract):
    task_id: UUID
    seq: SafeInteger
    event_type: Literal[
        "task.queued", "task.running", "task.retry_wait", "task.succeeded",
        "task.blocked", "task.failed", "task.cancelled", "task.dead_letter",
        "task.cancel_requested"
    ]
    state: Literal[
        "QUEUED", "RUNNING", "RETRY_WAIT", "SUCCEEDED", "BLOCKED",
        "FAILED", "CANCELLED", "DEAD_LETTER"
    ]
    occurred_at: datetime


class EventPage(Contract):
    data: list[TaskEventView] = Field(max_length=64)
    current_seq: SafeInteger
    retention_floor: SafeInteger
    reset_required: StrictBool = False


class NotificationView(Contract):
    notification_id: UUID
    task_id: UUID
    event_seq: SafeInteger
    event_type: Literal[
        "task.succeeded", "task.blocked", "task.failed", "task.cancelled",
        "task.dead_letter"
    ]
    state: Literal["SUCCEEDED", "BLOCKED", "FAILED", "CANCELLED", "DEAD_LETTER"]
    created_at: datetime
    read_at: datetime | None = None


class NotificationPage(Contract):
    data: list[NotificationView] = Field(max_length=25)
    next_cursor: UUID | None = None


class NotificationResponse(Contract):
    data: NotificationView


class NotificationUnreadResponse(Contract):
    has_unread: StrictBool


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
    schema = TypeAdapter(SubmitTask | TaskEnvelope | TaskResponse | ResultResponse |
                         TaskPage | EventPage | NotificationPage | NotificationResponse |
                         NotificationUnreadResponse).json_schema()
    return {"$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "https://eid.local/contracts/task.schema.json", **schema}
