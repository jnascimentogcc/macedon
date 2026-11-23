import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Scope = Literal["read", "write"]


def _read_only() -> list[Scope]:
    return ["read"]


class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    groups: list[str] = Field(default_factory=list, max_length=50)
    scopes: list[Scope] = Field(default_factory=_read_only, min_length=1)
    # Days until the key stops working. None uses the configured default; a key always expires.
    expires_in_days: int | None = Field(default=None, ge=1)


class ApiKeyOut(BaseModel):
    id: uuid.UUID
    name: str
    prefix: str
    groups: list[str]
    scopes: list[str]
    created_by: str
    created_at: datetime
    expires_at: datetime
    revoked_at: datetime | None
    last_used_at: datetime | None


class ApiKeyCreated(ApiKeyOut):
    # The only time the secret is ever shown.
    token: str
