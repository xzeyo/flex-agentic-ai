from functools import cached_property
from pathlib import Path
from uuid import uuid4

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TEAM_", env_file=".env", extra="ignore")
    model: str = "openai/gpt-4.1"
    api_key: SecretStr = SecretStr("")
    base_url: str | None = None
    data_dir: Path = Path("data")
    runner_image: str = "four-agent-python:1"
    run_timeout: float = Field(900, ge=1, le=3600)
    agent_timeout: float = Field(120, ge=1, le=300)
    check_timeout: float = Field(60, ge=1, le=120)
    max_fixes: int = Field(2, ge=0, le=5)
    max_review_fixes: int = Field(1, ge=0, le=2)
    max_active: int = Field(2, ge=1, le=8)
    max_queued: int = Field(20, ge=1, le=100)
    max_model_calls: int = Field(16, ge=4, le=32)

    @property
    def root(self) -> Path:
        return self.data_dir.resolve()

    @cached_property
    def instance_id(self) -> str:
        # Persisted per data volume, so separate Compose projects using /data do not collide.
        self.root.mkdir(parents=True, exist_ok=True)
        identity = self.root / "instance-id"
        if not identity.exists():
            identity.write_text(uuid4().hex, encoding="ascii")
        value = identity.read_text(encoding="ascii").strip()
        if len(value) != 32 or any(c not in "0123456789abcdef" for c in value):
            raise ValueError("Invalid application instance identity")
        return value
