import uuid

from pydantic import BaseModel, Field


class CollectionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    parent_id: uuid.UUID | None = None


class CollectionRename(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class CollectionOut(BaseModel):
    id: uuid.UUID
    parent_id: uuid.UUID | None
    name: str
    depth: int
    document_count: int = Field(description="Documents directly in this collection you can read.")
