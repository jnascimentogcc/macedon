from typing import Annotated

from fastapi import Depends, FastAPI

from macedon.auth import get_identity
from macedon.db.identity import Identity


def create_app() -> FastAPI:
    app = FastAPI(title="Macedon", version="0.1.0")

    @app.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/me", tags=["system"])
    async def me(identity: Annotated[Identity, Depends(get_identity)]) -> dict[str, object]:
        return {
            "user_id": identity.user_id,
            "groups": list(identity.groups),
            "is_admin": identity.is_admin,
        }

    return app


app = create_app()
