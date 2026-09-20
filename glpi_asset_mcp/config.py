from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    glpi_base_url: str
    glpi_app_token: str | None
    glpi_user_token: str | None
    glpi_username: str | None
    glpi_password: str | None
    reports_dir: Path
    request_timeout_seconds: int

    @classmethod
    def from_env(cls) -> "Settings":
        base_url = os.environ.get("GLPI_BASE_URL", "").strip().rstrip("/")
        reports_dir = Path(os.environ.get("GLPI_REPORTS_DIR", "reports")).resolve()
        timeout = int(os.environ.get("GLPI_REQUEST_TIMEOUT_SECONDS", "30"))
        return cls(
            glpi_base_url=base_url,
            glpi_app_token=os.environ.get("GLPI_APP_TOKEN"),
            glpi_user_token=os.environ.get("GLPI_USER_TOKEN"),
            glpi_username=os.environ.get("GLPI_USERNAME"),
            glpi_password=os.environ.get("GLPI_PASSWORD"),
            reports_dir=reports_dir,
            request_timeout_seconds=timeout,
        )

    def validate(self) -> None:
        if not self.glpi_base_url:
            raise ValueError("GLPI_BASE_URL is required")
        if not self.glpi_user_token and not (self.glpi_username and self.glpi_password):
            raise ValueError("Set GLPI_USER_TOKEN, or set GLPI_USERNAME and GLPI_PASSWORD")

