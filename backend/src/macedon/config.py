from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, read from environment variables prefixed with MACEDON_."""

    model_config = SettingsConfigDict(env_prefix="MACEDON_", env_file=".env", extra="ignore")

    # The API connects as macedon_app (no superuser, no BYPASSRLS) so Row-Level Security applies.
    database_url: str = "postgresql+asyncpg://macedon_app:macedon_app@127.0.0.1:5432/macedon"
    # Migrations run as the schema owner.
    migration_database_url: str = "postgresql+asyncpg://macedon:macedon@127.0.0.1:5432/macedon"
    redis_url: str = "redis://localhost:6379"

    s3_endpoint_url: str | None = "http://localhost:9000"
    s3_bucket: str = "macedon-documents"
    s3_access_key: str = "macedon"
    s3_secret_key: str = Field(default="macedon-dev-secret", repr=False)

    oidc_issuer: str = "http://localhost:8080/realms/macedon"
    oidc_audience: str = "macedon-api"
    oidc_jwks_url: str = "http://127.0.0.1:8080/realms/macedon/protocol/openid-connect/certs"
    admin_role: str = "admin"

    max_upload_bytes: int = 50 * 1024 * 1024

    query_rate_limit_per_minute: int = 30

    openai_api_key: SecretStr | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-6.1-terra"  # mid tier; see the OpenAI models page
    embedding_model: str = "text-embedding-3-large"
    embedding_dimensions: int = 3072  # must match the halfvec(3072) column


@lru_cache
def get_settings() -> Settings:
    return Settings()
