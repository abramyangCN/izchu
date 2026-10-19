from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="IZCHU_",
        extra="ignore",
    )

    strava_client_id: int | None = None
    strava_client_secret: str | None = None
    strava_redirect_uri: str = "http://localhost:8080/api/strava/callback"
    garmin_email: str | None = None
    garmin_password: str | None = None
    data_dir: Path = Field(default=Path("./data"))
    log_level: str = "INFO"

    @property
    def strava_token_path(self) -> Path:
        return self.data_dir / "strava-token.json"

    @property
    def strava_state_path(self) -> Path:
        return self.data_dir / "strava-oauth-state.json"

    @property
    def garmin_token_dir(self) -> Path:
        return self.data_dir / "garmin-tokens"

    @property
    def activity_dir(self) -> Path:
        return self.data_dir / "activities"

    def ensure_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.activity_dir.mkdir(parents=True, exist_ok=True, mode=0o700)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_directories()
    return settings

