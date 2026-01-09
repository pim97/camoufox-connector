"""
Configuration handling for Camoufox Connector.

Supports configuration via:
- Command line arguments
- Environment variables
- JSON configuration files
"""

from __future__ import annotations

import json
from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ServerMode(str, Enum):
    """Operating mode for the connector server."""

    SINGLE = "single"
    POOL = "pool"


class Settings(BaseSettings):
    """
    Configuration settings for Camoufox Connector.

    Settings can be configured via environment variables (prefixed with CAMOUFOX_)
    or directly passed as arguments.
    """

    model_config = SettingsConfigDict(
        env_prefix="CAMOUFOX_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Server mode
    mode: ServerMode = Field(
        default=ServerMode.SINGLE,
        description="Operating mode: 'single' for one browser, 'pool' for multiple",
    )

    # Pool configuration
    pool_size: int = Field(
        default=3,
        ge=1,
        le=20,
        description="Number of browser instances in pool mode",
    )

    # Network configuration
    api_port: int = Field(
        default=8080,
        ge=1024,
        le=65535,
        description="HTTP API port for health checks and management",
    )

    ws_port_start: int = Field(
        default=9222,
        ge=1024,
        le=65500,
        description="Starting port for browser WebSocket endpoints",
    )

    api_host: str = Field(
        default="0.0.0.0",
        description="Host to bind the HTTP API to",
    )

    # Browser configuration
    headless: bool = Field(
        default=True,
        description="Run browsers in headless mode",
    )

    geoip: bool = Field(
        default=True,
        description="Enable GeoIP-based locale/timezone spoofing",
    )

    humanize: bool = Field(
        default=True,
        description="Enable humanization features",
    )

    block_images: bool = Field(
        default=False,
        description="Block image loading for faster page loads",
    )

    # Proxy configuration
    proxy: Optional[str] = Field(
        default=None,
        description="Proxy URL (http://user:pass@host:port)",
    )

    # Debug settings
    debug: bool = Field(
        default=False,
        description="Enable debug logging",
    )

    @field_validator("proxy")
    @classmethod
    def validate_proxy(cls, v: Optional[str]) -> Optional[str]:
        """Validate proxy URL format."""
        if v is None or v == "":
            return None
        # Basic validation - should start with http:// or https://
        if not v.startswith(("http://", "https://", "socks5://")):
            raise ValueError("Proxy must start with http://, https://, or socks5://")
        return v

    @classmethod
    def from_json(cls, path: str | Path) -> Settings:
        """Load settings from a JSON configuration file."""
        with open(path) as f:
            data = json.load(f)
        return cls(**data)

    @classmethod
    def from_cli_args(cls, args) -> Settings:
        """Create settings from parsed CLI arguments."""
        # Convert argparse namespace to dict, filtering None values
        data = {k: v for k, v in vars(args).items() if v is not None}

        # Handle config file if specified
        if "config" in data and data["config"]:
            config_path = data.pop("config")
            base_settings = cls.from_json(config_path)
            # Merge CLI args on top of config file
            return base_settings.model_copy(update=data)

        return cls(**data)

    def get_ws_port(self, index: int = 0) -> int:
        """Get WebSocket port for a given browser instance index."""
        return self.ws_port_start + index

    def to_camoufox_kwargs(self) -> dict:
        """Convert settings to kwargs for camoufox launch_server."""
        kwargs = {
            "headless": self.headless,
            "geoip": self.geoip,
            "humanize": self.humanize,
            "block_images": self.block_images,
        }

        if self.proxy:
            kwargs["proxy"] = self.proxy

        return kwargs
