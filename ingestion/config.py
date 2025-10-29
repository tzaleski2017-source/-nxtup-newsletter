"""
Configuration Management

Loads and validates environment variables using Pydantic.
"""

from typing import List
from pydantic_settings import BaseSettings
from pydantic import Field, field_validator


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    # Twitch API Credentials
    twitch_client_id: str = Field(
        ...,
        description="Twitch application Client ID"
    )
    twitch_client_secret: str = Field(
        ...,
        description="Twitch application Client Secret"
    )
    twitch_access_token: str = Field(
        ...,
        description="Twitch user access token for EventSub and IRC"
    )

    # Database Configuration
    database_url: str = Field(
        ...,
        description="PostgreSQL connection string (Neon database)"
    )

    # Application Settings
    snapshot_interval_minutes: int = Field(
        default=15,
        description="Interval between snapshot collections (minutes)"
    )

    log_level: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR)"
    )

    # Tracked Streamers
    # Note: In production, this would come from database
    # For MVP, we use environment variable for simplicity
    tracked_streamers: str = Field(
        default="",
        description="Comma-separated list of Twitch usernames to track"
    )

    @field_validator("tracked_streamers")
    @classmethod
    def parse_streamers(cls, v: str) -> str:
        """Validate tracked streamers format."""
        if not v:
            raise ValueError("TRACKED_STREAMERS must not be empty")

        # Validate format (comma-separated, no spaces)
        streamers = [s.strip() for s in v.split(",") if s.strip()]
        if not streamers:
            raise ValueError("TRACKED_STREAMERS must contain at least one username")

        return v

    @property
    def tracked_streamer_list(self) -> List[str]:
        """Return tracked streamers as a list."""
        return [s.strip() for s in self.tracked_streamers.split(",") if s.strip()]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


# Global settings instance (loaded once)
settings: Settings = None


def get_settings() -> Settings:
    """Get or create settings instance."""
    global settings
    if settings is None:
        settings = Settings()
    return settings
