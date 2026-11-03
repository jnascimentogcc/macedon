"""Let a document's owner update the ACL copied onto its chunks.

Each chunk carries a copy of its document's ACL, so changing who a document is shared with must
rewrite the chunks too. Until now only the ingestion worker (an admin) could write chunks. This
adds an UPDATE policy for the owner of the document, so the API can do it as the caller and the
second barrier stays on. Policies are permissive and combine with `chunks_write`.

Row-Level Security cannot limit columns, so the application role also loses its table-wide UPDATE
on chunks and keeps it only on the two ACL columns: an owner can re-share a document but never
rewrite the indexed content or embeddings.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-03
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "macedon_app"


def upgrade() -> None:
    owner_of_document = (
        "EXISTS (SELECT 1 FROM documents d "
        "WHERE d.id = chunks.document_id AND d.owner_id = app_user_id())"
    )
    op.execute(
        f"CREATE POLICY chunks_owner_update ON chunks FOR UPDATE "
        f"USING ({owner_of_document}) WITH CHECK ({owner_of_document})"
    )
    op.execute(f"REVOKE UPDATE ON chunks FROM {APP_ROLE}")
    op.execute(f"GRANT UPDATE (acl_users, acl_groups) ON chunks TO {APP_ROLE}")


def downgrade() -> None:
    op.execute(f"REVOKE UPDATE (acl_users, acl_groups) ON chunks FROM {APP_ROLE}")
    op.execute(f"GRANT UPDATE ON chunks TO {APP_ROLE}")
    op.execute("DROP POLICY IF EXISTS chunks_owner_update ON chunks")
