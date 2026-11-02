import uuid
from typing import Self

from pydantic import BaseModel, Field, model_validator


class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    document_id: uuid.UUID | None = Field(
        default=None, description="Limit the search to one document."
    )
    version: int | None = Field(
        default=None,
        ge=1,
        description="Search this historical version instead of the active one. "
        "Requires document_id.",
    )
    top_k: int = Field(default=5, ge=1, le=10, description="How many chunks to retrieve.")

    @model_validator(mode="after")
    def _version_needs_a_document(self) -> Self:
        if self.version is not None and self.document_id is None:
            raise ValueError("version requires document_id")
        return self


class SourceOut(BaseModel):
    id: int
    document_id: uuid.UUID
    document_name: str
    version: int
    page: int | None
    section: str
    text: str
    cited: bool


class QueryResponse(BaseModel):
    answer: str
    sources: list[SourceOut]
    model: str | None = None
