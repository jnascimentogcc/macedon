import hashlib
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import ColumnElement, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from macedon.audit import record_audit
from macedon.auth import get_identity
from macedon.config import Settings, get_settings
from macedon.db.identity import Identity
from macedon.db.models import Collection, Document, DocumentVersion
from macedon.db.session import get_session
from macedon.documents.queue import JobQueue, get_job_queue
from macedon.documents.schemas import (
    DocumentOut,
    DocumentPage,
    DocumentUpdate,
    UploadOut,
    VersionOut,
)
from macedon.documents.storage import ObjectStore, get_object_store
from macedon.documents.tags import InvalidTagError, normalize_tags
from macedon.documents.validation import UnsupportedFileError, detect_document_type
from macedon.groups import available_groups

router = APIRouter(prefix="/documents", tags=["documents"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
IdentityDep = Annotated[Identity, Depends(get_identity)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
StoreDep = Annotated[ObjectStore, Depends(get_object_store)]
QueueDep = Annotated[JobQueue, Depends(get_job_queue)]


def _version_out(version: DocumentVersion | None) -> VersionOut | None:
    return None if version is None else VersionOut.model_validate(version, from_attributes=True)


async def _read_limited(file: UploadFile, limit: int) -> bytes:
    data = bytearray()
    while chunk := await file.read(1024 * 1024):
        data += chunk
        if len(data) > limit:
            raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, f"file exceeds {limit} bytes")
    return bytes(data)


async def _load_document(session: AsyncSession, document_id: uuid.UUID) -> Document:
    """A document the caller cannot read looks exactly like one that does not exist."""
    document = await session.get(Document, document_id)
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "document not found")
    return document


def _require_manager(document: Document, identity: Identity) -> None:
    if not (identity.is_admin or document.owner_id == identity.user_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "only the owner can change this document")
    if document.archived_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "document is archived")


def _clean_tags(tags: list[str] | None) -> list[str]:
    try:
        return normalize_tags(tags)
    except InvalidTagError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc


async def _require_collection(session: AsyncSession, collection_id: uuid.UUID | None) -> None:
    if collection_id is not None and await session.get(Collection, collection_id) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "collection not found")


async def _versions(session: AsyncSession, document_id: uuid.UUID) -> list[DocumentVersion]:
    result = await session.execute(
        select(DocumentVersion)
        .where(DocumentVersion.document_id == document_id)
        .order_by(DocumentVersion.number.desc())
    )
    return list(result.scalars())


def _document_with(document: Document, versions: list[DocumentVersion]) -> DocumentOut:
    """`versions` newest first."""
    active = next((v for v in versions if v.status == "active"), None)
    out = DocumentOut.model_validate(document, from_attributes=True)
    out.latest_version = _version_out(versions[0] if versions else None)
    out.active_version = _version_out(active)
    return out


async def _document_out(session: AsyncSession, document: Document) -> DocumentOut:
    return _document_with(document, await _versions(session, document.id))


async def _store_version(
    session: AsyncSession,
    store: ObjectStore,
    document: Document,
    identity: Identity,
    data: bytes,
    file_hash: str,
) -> DocumentVersion:
    number = (
        await session.execute(
            select(func.coalesce(func.max(DocumentVersion.number), 0)).where(
                DocumentVersion.document_id == document.id
            )
        )
    ).scalar_one() + 1
    version = DocumentVersion(
        id=uuid.uuid4(),
        document_id=document.id,
        number=number,
        file_hash=file_hash,
        storage_key=f"documents/{document.id}/versions/{number}",
        status="processing",
        author_id=identity.user_id,
    )
    await store.put(version.storage_key, data)
    session.add(version)
    await session.flush()
    return version


@router.post("", status_code=status.HTTP_202_ACCEPTED, response_model=UploadOut)
async def upload_document(
    session: SessionDep,
    identity: IdentityDep,
    settings: SettingsDep,
    store: StoreDep,
    queue: QueueDep,
    file: Annotated[UploadFile, File()],
    name: Annotated[str | None, Form()] = None,
    tags: Annotated[list[str] | None, Form()] = None,
    collection_id: Annotated[uuid.UUID | None, Form()] = None,
    acl_users: Annotated[list[str] | None, Form()] = None,
    acl_groups: Annotated[list[str] | None, Form()] = None,
) -> UploadOut:
    """Create a document with version 1; processing continues in the background."""
    data = await _read_limited(file, settings.max_upload_bytes)
    try:
        doc_type = detect_document_type(data)
    except UnsupportedFileError as exc:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, str(exc)) from exc

    clean_tags = _clean_tags(tags)
    await _require_collection(session, collection_id)
    unknown = set(acl_groups or []) - set(available_groups(settings, identity))
    if unknown:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"unknown groups: {', '.join(sorted(unknown))}"
        )
    document = Document(
        id=uuid.uuid4(),
        name=name or file.filename or "untitled",
        doc_type=doc_type,
        owner_id=identity.user_id,
        tags=clean_tags,
        collection_id=collection_id,
        # The owner can always read their own document.
        acl_users=sorted({identity.user_id, *(acl_users or [])}),
        acl_groups=sorted(set(acl_groups or [])),
    )
    session.add(document)
    await session.flush()
    version = await _store_version(
        session, store, document, identity, data, hashlib.sha256(data).hexdigest()
    )
    await record_audit(session, identity, "upload", document_id=document.id, version_id=version.id)
    out = UploadOut(
        document=await _document_out(session, document),
        version=_version_out(version),
    )
    await session.commit()
    await queue.enqueue_ingestion(version.id)
    return out


@router.get("", response_model=DocumentPage)
async def list_documents(
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    include_archived: bool = False,
    collection_id: Annotated[
        uuid.UUID | None, Query(description="Only documents in this collection or below.")
    ] = None,
    tag: Annotated[
        list[str] | None, Query(description="Only documents with all these tags.")
    ] = None,
) -> DocumentPage:
    """The documents the caller can read, newest first. Row-Level Security does the filtering."""
    conditions: list[ColumnElement[bool]] = (
        [] if include_archived else [Document.archived_at.is_(None)]
    )
    if collection_id is not None:
        root = aliased(Collection)
        conditions.append(
            Document.collection_id.in_(
                select(Collection.id)
                .join(root, root.id == collection_id)
                .where(func.starts_with(Collection.path, root.path))
            )
        )
    wanted_tags = _clean_tags(tag)
    if wanted_tags:
        conditions.append(Document.tags.contains(wanted_tags))
    total = (
        await session.execute(select(func.count()).select_from(Document).where(*conditions))
    ).scalar_one()
    documents = list(
        (
            await session.execute(
                select(Document)
                .where(*conditions)
                .order_by(Document.created_at.desc(), Document.id)
                .limit(limit)
                .offset(offset)
            )
        ).scalars()
    )
    versions: dict[uuid.UUID, list[DocumentVersion]] = {d.id: [] for d in documents}
    if documents:
        rows = await session.execute(
            select(DocumentVersion)
            .where(DocumentVersion.document_id.in_(versions))
            .order_by(DocumentVersion.number.desc())
        )
        for version in rows.scalars():
            versions[version.document_id].append(version)
    return DocumentPage(
        items=[_document_with(document, versions[document.id]) for document in documents],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{document_id}", response_model=DocumentOut)
async def get_document(document_id: uuid.UUID, session: SessionDep) -> DocumentOut:
    return await _document_out(session, await _load_document(session, document_id))


@router.patch("/{document_id}", response_model=DocumentOut)
async def update_document(
    document_id: uuid.UUID, body: DocumentUpdate, session: SessionDep, identity: IdentityDep
) -> DocumentOut:
    """Rename, retag or move a document. Only its owner or an administrator can."""
    document = await _load_document(session, document_id)
    _require_manager(document, identity)
    fields = body.model_fields_set
    if "name" in fields and body.name is not None:
        document.name = body.name.strip()
    if "tags" in fields:
        document.tags = _clean_tags(body.tags)
    if "collection_id" in fields:
        await _require_collection(session, body.collection_id)
        document.collection_id = body.collection_id
    await session.flush()
    await record_audit(session, identity, "update", document_id=document.id)
    return await _document_out(session, document)


@router.post(
    "/{document_id}/versions", status_code=status.HTTP_202_ACCEPTED, response_model=UploadOut
)
async def upload_version(
    document_id: uuid.UUID,
    session: SessionDep,
    identity: IdentityDep,
    settings: SettingsDep,
    store: StoreDep,
    queue: QueueDep,
    file: Annotated[UploadFile, File()],
) -> UploadOut:
    document = await _load_document(session, document_id)
    _require_manager(document, identity)

    data = await _read_limited(file, settings.max_upload_bytes)
    try:
        doc_type = detect_document_type(data)
    except UnsupportedFileError as exc:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, str(exc)) from exc
    if doc_type != document.doc_type:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"a new version must keep the document type ({document.doc_type})",
        )

    file_hash = hashlib.sha256(data).hexdigest()
    versions = await _versions(session, document.id)
    if versions and versions[0].file_hash == file_hash and versions[0].status != "failed":
        # The same file again is not reprocessed.
        return UploadOut(
            document=await _document_out(session, document),
            version=_version_out(versions[0]),
            duplicate=True,
        )

    try:
        version = await _store_version(session, store, document, identity, data, file_hash)
    except IntegrityError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "another version was uploaded at the same time"
        ) from exc
    await record_audit(
        session, identity, "upload_version", document_id=document.id, version_id=version.id
    )
    out = UploadOut(
        document=await _document_out(session, document),
        version=_version_out(version),
    )
    await session.commit()
    await queue.enqueue_ingestion(version.id)
    return out


@router.get("/{document_id}/versions", response_model=list[VersionOut])
async def list_versions(document_id: uuid.UUID, session: SessionDep) -> list[VersionOut]:
    await _load_document(session, document_id)
    return [
        VersionOut.model_validate(v, from_attributes=True)
        for v in await _versions(session, document_id)
    ]


@router.post("/{document_id}/versions/{number}/activate", response_model=VersionOut)
async def activate_version(
    document_id: uuid.UUID, number: int, session: SessionDep, identity: IdentityDep
) -> VersionOut:
    """Make a previously indexed version the active one (this is also how rollback works)."""
    document = await _load_document(session, document_id)
    _require_manager(document, identity)

    versions = {v.number: v for v in await _versions(session, document_id)}
    target = versions.get(number)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "version not found")
    if target.status == "active":
        return VersionOut.model_validate(target, from_attributes=True)
    if target.status != "archived":
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"a {target.status} version cannot be activated"
        )

    # Demote first: at most one version per document may be active at any moment.
    await session.execute(
        update(DocumentVersion)
        .where(DocumentVersion.document_id == document_id, DocumentVersion.status == "active")
        .values(status="archived")
    )
    target.status = "active"
    await session.flush()
    await record_audit(session, identity, "activate", document_id=document_id, version_id=target.id)
    return VersionOut.model_validate(target, from_attributes=True)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_document(
    document_id: uuid.UUID, session: SessionDep, identity: IdentityDep
) -> None:
    """Soft delete: nothing is erased, but the document stops answering queries."""
    document = await _load_document(session, document_id)
    _require_manager(document, identity)

    document.archived_at = func.now()
    await session.execute(
        update(DocumentVersion)
        .where(DocumentVersion.document_id == document_id, DocumentVersion.status == "active")
        .values(status="archived")
    )
    await record_audit(session, identity, "archive", document_id=document_id)
