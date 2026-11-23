"""API keys: long-lived credentials for other applications.

A key acts as its own identity (`key:<id>`) with the groups chosen when it was created, so the
document ACL and Row-Level Security apply to it exactly as to a user. Only a SHA-256 hash of the
secret is stored; the secret has 256 bits of entropy, so a plain hash is enough.

The table is for administrators only (RLS). The API has to find a key *before* it knows who is
calling, so authentication goes through `api_key_authenticate`, a SECURITY DEFINER function that
returns just what the identity needs, only for a key that is neither revoked nor expired, and
records the last use (at most once a minute, to avoid writing on every request). The table has
RLS enabled but not forced, so its owner, and so that function, can read it.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-23
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "macedon_app"


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE api_keys (
            id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            name         varchar(120) NOT NULL,
            prefix       varchar(16)  NOT NULL,
            token_hash   varchar(64)  NOT NULL UNIQUE,
            groups       text[]       NOT NULL DEFAULT '{}',
            scopes       text[]       NOT NULL
                         CHECK (cardinality(scopes) > 0 AND scopes <@ ARRAY['read', 'write']),
            created_by   varchar(255) NOT NULL,
            created_at   timestamptz  NOT NULL DEFAULT now(),
            expires_at   timestamptz  NOT NULL,
            revoked_at   timestamptz,
            last_used_at timestamptz
        )
        """
    )
    op.execute("ALTER TABLE api_keys ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY api_keys_admin ON api_keys FOR ALL "
        "USING (app_is_admin()) WITH CHECK (app_is_admin())"
    )
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON api_keys TO {APP_ROLE}")

    op.execute(
        """
        CREATE FUNCTION api_key_authenticate(p_hash text)
        RETURNS TABLE (key_id uuid, key_groups text[], key_scopes text[])
        LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = public, pg_temp AS $$
        BEGIN
            RETURN QUERY
                SELECT k.id, k.groups, k.scopes FROM api_keys k
                WHERE k.token_hash = p_hash AND k.revoked_at IS NULL AND k.expires_at > now();
            UPDATE api_keys k SET last_used_at = now()
            WHERE k.token_hash = p_hash AND k.revoked_at IS NULL AND k.expires_at > now()
              AND (k.last_used_at IS NULL OR k.last_used_at < now() - interval '1 minute');
        END
        $$
        """
    )
    op.execute("REVOKE ALL ON FUNCTION api_key_authenticate(text) FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION api_key_authenticate(text) TO {APP_ROLE}")


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS api_key_authenticate(text)")
    op.execute("DROP TABLE IF EXISTS api_keys")
