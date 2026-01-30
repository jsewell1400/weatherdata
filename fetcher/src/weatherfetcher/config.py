"""
Configuration module - loads settings from environment variables.
"""

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Configuration loaded from environment variables."""

    # MongoDB connection settings
    mongo_host: str = Field(default="mongodb", description="MongoDB hostname")
    mongo_port: int = Field(default=27017, description="MongoDB port")
    mongo_database: str = Field(default="weatherdata", description="Database name")
    mongo_username: str = Field(..., description="MongoDB username")
    mongo_password: str = Field(..., description="MongoDB password")

    # Polling intervals
    observation_interval_seconds: int = Field(
        default=600,  # 10 minutes = 6 times per hour
        description="How often to fetch observations (seconds)"
    )
    station_refresh_interval_seconds: int = Field(
        default=86400,  # 24 hours
        description="How often to refresh the station list (seconds)"
    )

    # Environment Canada URLs (updated June 2025)
    ec_base_url: str = Field(
        default="https://dd.weather.gc.ca/today/citypage_weather",
        description="Environment Canada XML data base URL"
    )
    ec_site_list_url: str = Field(
        default="https://collaboration.cmc.ec.gc.ca/cmc/cmos/public_doc/msc-data/citypage-weather/site_list_en.geojson",
        description="URL for the station list (GeoJSON format)"
    )

    # Request settings
    request_timeout_seconds: int = Field(
        default=30,
        description="HTTP request timeout in seconds"
    )
    max_concurrent_requests: int = Field(
        default=20,
        description="Maximum concurrent HTTP requests"
    )
    request_delay_seconds: float = Field(
        default=0.1,
        description="Delay between requests to avoid overwhelming the server"
    )

    # Retry settings
    max_retries: int = Field(
        default=3,
        description="Maximum retries for failed requests"
    )
    retry_delay_seconds: float = Field(
        default=1.0,
        description="Delay between retries"
    )

    # Logging
    log_level: str = Field(
        default="INFO",
        description="Logging level"
    )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False

    @property
    def mongo_uri(self) -> str:
        """Build MongoDB connection URI."""
        return (
            f"mongodb://{self.mongo_username}:{self.mongo_password}"
            f"@{self.mongo_host}:{self.mongo_port}/{self.mongo_database}"
            f"?authSource={self.mongo_database}"
        )


# Global settings instance
settings = Settings()
