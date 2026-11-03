"""Collections: a tree that organizes documents, plus an index on tags.

Collections are organization only. They never grant access: the ACL stays on each document.
Everyone who is signed in can read the whole tree; only admins change it.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-02
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "macedon_app"


def upgrade() -> None:
    # `path` is the chain of ancestor ids ("/<root>/<child>/"), so a whole subtree is one prefix
    # match and renaming never rewrites it.
    op.execute(
        """
        CREATE TABLE collections (
            id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            parent_id  uuid REFERENCES collections (id) ON DELETE RESTRICT,
            name       varchar(120) NOT NULL CHECK (btrim(name) <> ''),
            path       text         NOT NULL,
            depth      integer      NOT NULL CHECK (depth BETWEEN 1 AND 4),
            created_at timestamptz  NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_collections_sibling_name ON collections "
        "(coalesce(parent_id, '00000000-0000-0000-0000-000000000000'::uuid), lower(name))"
    )
    op.execute("CREATE INDEX ix_collections_path ON collections (path text_pattern_ops)")

    op.execute(
        "ALTER TABLE documents ADD COLUMN collection_id uuid "
        "REFERENCES collections (id) ON DELETE RESTRICT"
    )
    op.execute("CREATE INDEX ix_documents_collection_id ON documents (collection_id)")
    op.execute("CREATE INDEX ix_documents_tags ON documents USING gin (tags)")

    op.execute("ALTER TABLE collections ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE collections FORCE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY collections_select ON collections FOR SELECT USING (true)")
    op.execute(
        "CREATE POLICY collections_write ON collections FOR ALL "
        "USING (app_is_admin()) WITH CHECK (app_is_admin())"
    )
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON collections TO {APP_ROLE}")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_documents_tags")
    op.execute("DROP INDEX IF EXISTS ix_documents_collection_id")
    op.execute("ALTER TABLE documents DROP COLUMN IF EXISTS collection_id")
    op.execute("DROP TABLE IF EXISTS collections")
