from datetime import datetime
from typing import Literal
from uuid import UUID
from contextlib import contextmanager

import psycopg
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictBool, field_validator, model_validator

from ..auth import bearer_token
from ..db import connection
from ..errors import ApiError
from . import repository
from .policy import AccessDenied, ROLE_OPERATIONS


class MemberPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_epoch: list[StrictInt] = Field(min_length=3, max_length=3)
    active: StrictBool
    roles: list[str] = Field(max_length=7)
    project_scope: list[str] = Field(max_length=100)
    customer_scope: list[str] = Field(max_length=100)
    product_scope: list[str] = Field(max_length=100)
    department_scope: list[str] = Field(max_length=100)
    owner_scope: Literal["self", "any"]
    approval_states: list[Literal["draft", "in_review", "approved", "rejected"]] = Field(max_length=4)
    clearance: int = Field(ge=0, le=3, strict=True)
    valid_from: datetime
    valid_until: datetime | None

    @field_validator("roles")
    @classmethod
    def valid_roles(cls, roles):
        if any(role not in ROLE_OPERATIONS for role in roles) or len(set(roles)) != len(roles):
            raise ValueError("Unknown or duplicate role")
        return roles

    @field_validator("approval_states")
    @classmethod
    def unique_approval_states(cls, values):
        if len(set(values)) != len(values):
            raise ValueError("Duplicate approval state")
        return values

    @field_validator("project_scope", "customer_scope", "product_scope", "department_scope")
    @classmethod
    def valid_scopes(cls, values):
        if any(not value or len(value) > 128 or "\x00" in value for value in values) or len(set(values)) != len(values):
            raise ValueError("Invalid scope")
        return values

    @model_validator(mode="after")
    def valid_dates(self):
        if self.valid_from.tzinfo is None or (self.valid_until is not None and
                (self.valid_until.tzinfo is None or self.valid_until <= self.valid_from)):
            raise ValueError("Invalid validity interval")
        if any(value < 1 for value in self.expected_epoch):
            raise ValueError("Invalid epoch")
        return self


class DelegationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    resource_id: UUID | None = None
    operation: str = Field(max_length=64)
    purpose: str = Field(min_length=1, max_length=128)

    @field_validator("purpose")
    @classmethod
    def valid_purpose(cls, value):
        if "\x00" in value:
            raise ValueError("Invalid purpose")
        return value


def create_router(settings, verify):
    router = APIRouter(prefix="/api/v1/access")

    def actor(token: str = Depends(bearer_token)):
        return verify(token)

    @contextmanager
    def database():
        try:
            with connection(settings) as conn:
                yield conn
        except AccessDenied as exc:
            raise ApiError(403, "ACCESS_DENIED", "当前权限不允许此访问") from exc
        except psycopg.Error as exc:
            raise ApiError(503, "POLICY_UNAVAILABLE", "当前权限存储不可用", retryable=True) from exc

    @router.get("/workspaces")
    def list_workspaces(after: UUID | None = None, current=Depends(actor)):
        with database() as conn:
            return {"data": repository.workspace_page(conn, current.subject, after)}

    @router.get("/workspaces/{workspace_id}")
    def get_workspace(workspace_id: UUID, current=Depends(actor)):
        with database() as conn:
            facts, _, context = repository.checked(conn, current.subject, workspace_id)
            return {"data": repository.workspace_payload(facts, context)}

    @router.get("/workspaces/{workspace_id}/members")
    def get_members(workspace_id: UUID, after: UUID | None = None, current=Depends(actor)):
        with database() as conn:
            return {"data": repository.members(conn, current.subject, workspace_id, after)}

    @router.put("/workspaces/{workspace_id}/members/{identity_id}")
    def put_member(workspace_id: UUID, identity_id: UUID, body: MemberPolicy,
                   request: Request, current=Depends(actor)):
        with database() as conn:
            result = repository.change_member(conn, current.subject, workspace_id, identity_id,
                                              body.model_dump(exclude={"expected_epoch"}),
                                              body.expected_epoch, request.state.request_id,
                                              request.state.trace_id)
            if result is None:
                raise ApiError(409, "POLICY_EPOCH_CONFLICT", "权限已变化，请重新读取后操作")
            return {"data": result}

    @router.get("/workspaces/{workspace_id}/resources/{resource_id}")
    def get_resource(workspace_id: UUID, resource_id: UUID, request: Request, current=Depends(actor)):
        with database() as conn:
            _, resource, context = repository.checked(conn, current.subject, workspace_id,
                                                      "resource:read", resource_id)
            return {"data": {"id": str(resource["id"]), "title": resource["title"],
                             "kind": resource["kind"], "context": context.payload() |
                             {"request_id": request.state.request_id, "trace_id": request.state.trace_id}}}

    @router.post("/workspaces/{workspace_id}/delegations")
    def delegate(workspace_id: UUID, body: DelegationRequest, request: Request, current=Depends(actor)):
        with database() as conn:
            return {"data": repository.create_delegation(conn, current.subject, workspace_id,
                        body.resource_id, body.operation, body.purpose,
                        request.state.request_id, request.state.trace_id)}

    return router
