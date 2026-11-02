"""The collection tree. Everyone signed in can read it; only admins change it.

Collections organize documents and scope queries. They never grant access to anything: the ACL
stays on each document.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from macedon.audit import record_audit
from macedon.auth import get_identity
from macedon.collections.schemas import CollectionCreate, CollectionOut, CollectionRename
from macedon.db.identity import Identity
from macedon.db.models import Collection, Document
from macedon.db.session import get_session

router = APIRouter(prefix="/collections", tags=["collections"])

MAX_DEPTH = 4

SessionDep = Annotated[AsyncSession, Depends(get_session)]
IdentityDep = Annotated[Identity, Depends(get_identity)]


def _require_admin(identity: Identity) -> None:
    if not identity.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "only administrators change collections")


async def _load(session: AsyncSession, collection_id: uuid.UUID) -> Collection:
    collection = await session.get(Collection, collection_id)
    if collection is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "collection not found")
    return collection


@router.get("", response_model=list[CollectionOut])
async def list_collections(session: SessionDep) -> list[CollectionOut]:
    """The whole tree, flat and ordered so parents come before their children.

    `document_count` counts only the documents the caller can read (Row-Level Security).
    """
    count_rows = await session.execute(
        select(Document.collection_id, func.count())
        .where(Document.archived_at.is_(None), Document.collection_id.is_not(None))
        .group_by(Document.collection_id)
    )
    counts = {row[0]: row[1] for row in count_rows}
    rows = (await session.execute(select(Collection))).scalars()
    return [
        CollectionOut(
            id=c.id,
            parent_id=c.parent_id,
            name=c.name,
            depth=c.depth,
            document_count=counts.get(c.id, 0),
        )
        for c in sorted(rows, key=lambda c: (c.path.count("/"), c.name.lower()))
    ]


@router.post("", status_code=status.HTTP_201_CREATED, response_model=CollectionOut)
async def create_collection(
    body: CollectionCreate, session: SessionDep, identity: IdentityDep
) -> CollectionOut:
    _require_admin(identity)
    parent = await _load(session, body.parent_id) if body.parent_id else None
    depth = 1 if parent is None else parent.depth + 1
    if depth > MAX_DEPTH:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"collections can be nested {MAX_DEPTH} deep"
        )
    collection_id = uuid.uuid4()
    collection = Collection(
        id=collection_id,
        parent_id=parent.id if parent else None,
        name=body.name.strip(),
        path=f"{parent.path if parent else '/'}{collection_id}/",
        depth=depth,
    )
    session.add(collection)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "a collection with this name already exists here"
        ) from exc
    await record_audit(
        session, identity, "collection_create", details={"collection_id": str(collection_id)}
    )
    return CollectionOut(
        id=collection.id,
        parent_id=collection.parent_id,
        name=collection.name,
        depth=collection.depth,
        document_count=0,
    )


@router.patch("/{collection_id}", response_model=CollectionOut)
async def rename_collection(
    collection_id: uuid.UUID, body: CollectionRename, session: SessionDep, identity: IdentityDep
) -> CollectionOut:
    _require_admin(identity)
    collection = await _load(session, collection_id)
    collection.name = body.name.strip()
    try:
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "a collection with this name already exists here"
        ) from exc
    await record_audit(
        session, identity, "collection_rename", details={"collection_id": str(collection_id)}
    )
    count = (
        await session.execute(
            select(func.count()).where(
                Document.collection_id == collection.id, Document.archived_at.is_(None)
            )
        )
    ).scalar_one()
    return CollectionOut(
        id=collection.id,
        parent_id=collection.parent_id,
        name=collection.name,
        depth=collection.depth,
        document_count=count,
    )


@router.delete("/{collection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_collection(
    collection_id: uuid.UUID, session: SessionDep, identity: IdentityDep
) -> None:
    """Only an empty collection can be deleted: no children and no documents (archived or not)."""
    _require_admin(identity)
    collection = await _load(session, collection_id)
    children = (
        await session.execute(
            select(func.count())
            .select_from(Collection)
            .where(Collection.parent_id == collection.id)
        )
    ).scalar_one()
    documents = (
        await session.execute(
            select(func.count())
            .select_from(Document)
            .where(Document.collection_id == collection.id)
        )
    ).scalar_one()
    if children or documents:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "move or remove its subcollections and documents before deleting it",
        )
    await session.delete(collection)
    await record_audit(
        session, identity, "collection_delete", details={"collection_id": str(collection_id)}
    )
