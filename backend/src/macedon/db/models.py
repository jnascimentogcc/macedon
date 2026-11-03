"""ORM models. The schema itself, including indexes and RLS policies, lives in the migrations."""

import uuid
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import HALFVEC
from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

EMBEDDING_DIMENSIONS = 3072  # text-embedding-3-large, stored as halfvec


class Base(DeclarativeBase):
    pass


class Collection(Base):
    """A node of the tree that organizes documents. Organization only, never access."""

    __tablename__ = "collections"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("collections.id"))
    name: Mapped[str] = mapped_column(String(120))
    path: Mapped[str] = mapped_column(Text)  # "/<ancestor id>/.../<own id>/"
    depth: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255))
    doc_type: Mapped[str] = mapped_column(String(16))
    owner_id: Mapped[str] = mapped_column(String(255))
    tags: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    collection_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("collections.id"))
    acl_users: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    acl_groups: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DocumentVersion(Base):
    __tablename__ = "document_versions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    number: Mapped[int] = mapped_column(Integer)
    file_hash: Mapped[str] = mapped_column(String(64))
    storage_key: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16))  # processing | active | archived | failed
    error: Mapped[str | None] = mapped_column(Text)
    author_id: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_versions.id", ondelete="CASCADE")
    )
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    section_id: Mapped[str] = mapped_column(String(64))
    position: Mapped[int] = mapped_column(Integer)
    page: Mapped[int | None] = mapped_column(Integer)
    path: Mapped[str] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64))
    embedding = mapped_column(HALFVEC(EMBEDDING_DIMENSIONS))
    embedding_model: Mapped[str] = mapped_column(String(64))
    acl_users: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    acl_groups: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    actor_id: Mapped[str] = mapped_column(String(255))
    action: Mapped[str] = mapped_column(String(32))
    document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    chunk_ids: Mapped[list[int] | None] = mapped_column(ARRAY(BigInteger))
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))
