import uuid
from datetime import datetime

from pydantic import BaseModel


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
