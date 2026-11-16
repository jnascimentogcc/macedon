"""Keyword search with Portuguese stemming and accent folding.

The `simple` configuration matches only identical words, so "reembolsadas" never found
"reembolso" and "rescisao" never found "rescisão". The new `macedon_text` configuration folds
accents (unaccent) and then stems with the Portuguese snowball stemmer. Codes such as "NSI-317"
survive both steps. The generated `tsv` column is rebuilt with it, and the query side must use the
same configuration (see `macedon.query.retrieval.TEXT_SEARCH_CONFIG`).

Revision ID: 0004
Revises: 0003
"""

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent")
    op.execute("CREATE TEXT SEARCH CONFIGURATION macedon_text (COPY = portuguese)")
    op.execute(
        "ALTER TEXT SEARCH CONFIGURATION macedon_text "
        "ALTER MAPPING FOR hword, hword_part, word WITH unaccent, portuguese_stem"
    )
    op.execute("DROP INDEX ix_chunks_tsv")
    op.execute("ALTER TABLE chunks DROP COLUMN tsv")
    op.execute(
        "ALTER TABLE chunks ADD COLUMN tsv tsvector GENERATED ALWAYS AS "
        "(to_tsvector('macedon_text', path || ' ' || content)) STORED"
    )
    op.execute("CREATE INDEX ix_chunks_tsv ON chunks USING gin (tsv)")


def downgrade() -> None:
    op.execute("DROP INDEX ix_chunks_tsv")
    op.execute("ALTER TABLE chunks DROP COLUMN tsv")
    op.execute(
        "ALTER TABLE chunks ADD COLUMN tsv tsvector GENERATED ALWAYS AS "
        "(to_tsvector('simple', path || ' ' || content)) STORED"
    )
    op.execute("CREATE INDEX ix_chunks_tsv ON chunks USING gin (tsv)")
    op.execute("DROP TEXT SEARCH CONFIGURATION macedon_text")
