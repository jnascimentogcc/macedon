from typing import Annotated

from fastapi import APIRouter, Depends

from macedon.auth import get_identity
from macedon.config import Settings, get_settings
from macedon.db.identity import Identity

router = APIRouter(prefix="/groups", tags=["groups"])


def available_groups(settings: Settings, identity: Identity) -> list[str]:
    """Groups a document can be shared with: the configured ones plus the caller's own.

    The identity provider is never queried, so the platform only knows the groups an operator
    listed in `known_groups` and the ones carried by the caller's token.
    """
    return sorted({*settings.known_groups, *identity.groups})


@router.get("", response_model=list[str])
async def list_groups(
    identity: Annotated[Identity, Depends(get_identity)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> list[str]:
    return available_groups(settings, identity)
