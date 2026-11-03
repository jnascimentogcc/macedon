import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class VersionOut(BaseModel):
    id: uuid.UUID
    number: int
    status: str
    file_hash: str
    author_id: str
    error: str | None
    created_at: datetime


class DocumentOut(BaseModel):
    id: uuid.UUID
    name: str
    doc_type: str
    owner_id: str
    tags: list[str]
    collection_id: uuid.UUID | None
    acl_users: list[str]
    acl_groups: list[str]
    created_at: datetime
    archived_at: datetime | None
    latest_version: VersionOut | None = None
    active_version: VersionOut | None = None


class UploadOut(BaseModel):
    document: DocumentOut
    version: VersionOut
    duplicate: bool = False


class DocumentPage(BaseModel):
    items: list[DocumentOut]
    total: int
    limit: int
    offset: int


class DocumentUpdate(BaseModel):
    """Fields left out stay as they are; `collection_id: null` takes the document out of its
    collection."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    tags: list[str] | None = None
    collection_id: uuid.UUID | None = None
    acl_groups: list[str] | None = None
