"""Application configuration loaded from environment variables.

Centralizing settings here means the rest of the codebase never reads
os.environ directly, which keeps configuration testable and mockable.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "wrightwarp-api"
    environment: str = "development"
    api_v1_prefix: str = "/api/v1"

    mongo_host: str = "localhost"
    mongo_port: int = 27017
    mongo_user: str | None = None
    mongo_password: str | None = None
    mongo_db_name: str = "wrightwarp"

    # Overrides everything above when set (e.g. for MongoDB Atlas or any
    # connection string that doesn't fit the host/port/user/password shape).
    mongo_uri: str | None = None

    @property
    def mongo_connection_uri(self) -> str:
        if self.mongo_uri:
            return self.mongo_uri
        if self.mongo_user and self.mongo_password:
            # docker-compose creates this user via MONGO_INITDB_ROOT_USERNAME, which
            # always lives in the admin database regardless of mongo_db_name.
            return f"mongodb://{self.mongo_user}:{self.mongo_password}@{self.mongo_host}:{self.mongo_port}/?authSource=admin"
        return f"mongodb://{self.mongo_host}:{self.mongo_port}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
