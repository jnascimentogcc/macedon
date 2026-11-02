-- Runs once, when the dev database is first created.
-- The API connects as macedon_app, a role that is neither superuser nor table owner,
-- so Row-Level Security applies to it (superusers always bypass RLS).
CREATE EXTENSION IF NOT EXISTS vector;
CREATE ROLE macedon_app LOGIN PASSWORD 'macedon_app' NOSUPERUSER NOBYPASSRLS;
