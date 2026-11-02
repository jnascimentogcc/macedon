"""Initial schema: documents, versions, chunks, audit log, and Row-Level Security.

Revision ID: 0001
Revises:
Create Date: 2026-11-02
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "macedon_app"

# Request-scoped identity, set by the API with set_config(..., true) inside each transaction:
#   app.user_id   the OIDC subject
#   app.groups    comma-separated group names from the token
#   app.is_admin  'true' for admins and for the trusted ingestion worker
IDENTITY_FUNCTIONS = [
    """
    CREATE FUNCTION app_is_admin() RETURNS boolean
    LANGUAGE sql STABLE AS $$
        SELECT coalesce(current_setting('app.is_admin', true), '') = 'true'
    $$
    """,
    """
    CREATE FUNCTION app_user_id() RETURNS text
    LANGUAGE sql STABLE AS $$
        SELECT coalesce(current_setting('app.user_id', true), '')
    $$
    """,
    """
    CREATE FUNCTION app_can_read(acl_users text[], acl_groups text[]) RETURNS boolean
    LANGUAGE sql STABLE AS $$
        SELECT app_is_admin()
            OR (app_user_id() <> '' AND app_user_id() = ANY (acl_users))
            OR string_to_array(coalesce(current_setting('app.groups', true), ''), ',')
               && acl_groups
    $$
    """,
]


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    for statement in IDENTITY_FUNCTIONS:
        op.execute(statement)

    op.execute(
        """
        CREATE TABLE documents (
            id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            name        varchar(255) NOT NULL,
            doc_type    varchar(16)  NOT NULL CHECK (doc_type IN ('pdf', 'docx', 'txt')),
            owner_id    varchar(255) NOT NULL,
            tags        text[]       NOT NULL DEFAULT '{}',
            acl_users   text[]       NOT NULL DEFAULT '{}',
            acl_groups  text[]       NOT NULL DEFAULT '{}',
            created_at  timestamptz  NOT NULL DEFAULT now(),
            archived_at timestamptz
        )
        """
    )

    op.execute(
        """
        CREATE TABLE document_versions (
            id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            document_id uuid         NOT NULL REFERENCES documents (id) ON DELETE CASCADE,
            number      integer      NOT NULL CHECK (number >= 1),
            file_hash   varchar(64)  NOT NULL,
            storage_key text         NOT NULL,
            status      varchar(16)  NOT NULL
                        CHECK (status IN ('processing', 'active', 'archived', 'failed')),
            error       text,
            author_id   varchar(255) NOT NULL,
            created_at  timestamptz  NOT NULL DEFAULT now(),
            UNIQUE (document_id, number)
        )
        """
    )
    # At most one active version per document.
    op.execute(
        "CREATE UNIQUE INDEX uq_document_versions_active "
        "ON document_versions (document_id) WHERE status = 'active'"
    )
    op.execute("CREATE INDEX ix_document_versions_file_hash ON document_versions (file_hash)")

    op.execute(
        """
        CREATE TABLE chunks (
            id              bigserial PRIMARY KEY,
            version_id      uuid NOT NULL REFERENCES document_versions (id) ON DELETE CASCADE,
            document_id     uuid         NOT NULL REFERENCES documents (id) ON DELETE CASCADE,
            section_id      varchar(64)  NOT NULL,
            position        integer      NOT NULL,
            page            integer,
            path            text         NOT NULL,
            content         text         NOT NULL,
            content_hash    varchar(64)  NOT NULL,
            embedding       halfvec(3072) NOT NULL,
            embedding_model varchar(64)  NOT NULL,
            acl_users       text[]       NOT NULL DEFAULT '{}',
            acl_groups      text[]       NOT NULL DEFAULT '{}',
            tsv             tsvector GENERATED ALWAYS AS
                            (to_tsvector('simple', path || ' ' || content)) STORED,
            UNIQUE (version_id, position)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_chunks_embedding ON chunks USING hnsw (embedding halfvec_cosine_ops)"
    )
    op.execute("CREATE INDEX ix_chunks_tsv ON chunks USING gin (tsv)")
    op.execute("CREATE INDEX ix_chunks_document_id ON chunks (document_id)")
    op.execute("CREATE INDEX ix_chunks_content_hash ON chunks (content_hash, embedding_model)")

    op.execute(
        """
        CREATE TABLE audit_log (
            id          bigserial PRIMARY KEY,
            at          timestamptz  NOT NULL DEFAULT now(),
            actor_id    varchar(255) NOT NULL,
            action      varchar(32)  NOT NULL,
            document_id uuid,
            version_id  uuid,
            chunk_ids   bigint[],
            details     jsonb
        )
        """
    )

    # ---- Row-Level Security: the second barrier behind the filter in the query itself. ----
    for table in ("documents", "document_versions", "chunks", "audit_log"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")

    # documents: readable through the ACL; changed only by the owner or an admin.
    op.execute(
        "CREATE POLICY documents_select ON documents FOR SELECT "
        "USING (app_can_read(acl_users, acl_groups))"
    )
    op.execute(
        "CREATE POLICY documents_insert ON documents FOR INSERT "
        "WITH CHECK (app_is_admin() OR owner_id = app_user_id())"
    )
    op.execute(
        "CREATE POLICY documents_update ON documents FOR UPDATE "
        "USING (app_is_admin() OR owner_id = app_user_id()) "
        "WITH CHECK (app_is_admin() OR owner_id = app_user_id())"
    )

    # document_versions: visible when the parent document is visible (documents RLS applies in
    # the subquery); changed only through the owner or an admin.
    op.execute(
        "CREATE POLICY versions_select ON document_versions FOR SELECT "
        "USING (EXISTS (SELECT 1 FROM documents d WHERE d.id = document_id))"
    )
    op.execute(
        "CREATE POLICY versions_insert ON document_versions FOR INSERT "
        "WITH CHECK (app_is_admin() OR EXISTS ("
        "SELECT 1 FROM documents d WHERE d.id = document_id AND d.owner_id = app_user_id()))"
    )
    op.execute(
        "CREATE POLICY versions_update ON document_versions FOR UPDATE "
        "USING (app_is_admin() OR EXISTS ("
        "SELECT 1 FROM documents d WHERE d.id = document_id AND d.owner_id = app_user_id()))"
    )

    # chunks: readable through the ACL copied onto each chunk; written only by the trusted
    # ingestion worker, which runs with app.is_admin = 'true'.
    op.execute(
        "CREATE POLICY chunks_select ON chunks FOR SELECT "
        "USING (app_can_read(acl_users, acl_groups))"
    )
    op.execute(
        "CREATE POLICY chunks_write ON chunks FOR ALL USING (app_is_admin()) "
        "WITH CHECK (app_is_admin())"
    )

    # audit_log: anyone can append an entry about themselves; only admins can read it.
    op.execute(
        "CREATE POLICY audit_insert ON audit_log FOR INSERT "
        "WITH CHECK (app_is_admin() OR actor_id = app_user_id())"
    )
    op.execute("CREATE POLICY audit_select ON audit_log FOR SELECT USING (app_is_admin())")

    # ---- Privileges for the application role. No DELETE on documents (soft delete) and
    # ---- no UPDATE/DELETE on the audit log (append-only).
    op.execute(f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON documents, document_versions TO {APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON chunks TO {APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT ON audit_log TO {APP_ROLE}")
    op.execute(f"GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE}")
    op.execute(
        f"GRANT EXECUTE ON FUNCTION app_is_admin(), app_user_id(), "
        f"app_can_read(text[], text[]) TO {APP_ROLE}"
    )


def downgrade() -> None:
    for table in ("audit_log", "chunks", "document_versions", "documents"):
        op.execute(f"DROP TABLE IF EXISTS {table}")
    op.execute("DROP FUNCTION IF EXISTS app_can_read(text[], text[])")
    op.execute("DROP FUNCTION IF EXISTS app_user_id()")
    op.execute("DROP FUNCTION IF EXISTS app_is_admin()")
