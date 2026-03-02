from __future__ import annotations

from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator


class ConfigError(ValueError):
    """Configuration validation error."""


class AppConfig(BaseModel):
    window_limit: int = Field(gt=0)
    api_timeout_seconds: float = Field(default=30.0, gt=0)
    timezone: str
    schedule_times: list[str]
    important_threads: list[int]
    regular_threads: list[int]

    @field_validator("important_threads", "regular_threads", mode="before")
    @classmethod
    def normalize_nullable_thread_lists(cls, value: Any) -> Any:
        if value is None:
            return []
        return value

    @field_validator("schedule_times")
    @classmethod
    def validate_schedule_times(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("schedule_times must not be empty")
        for item in value:
            parts = item.split(":")
            if len(parts) != 2:
                raise ValueError("time must be HH:MM")
            hour, minute = parts
            if not (hour.isdigit() and minute.isdigit()):
                raise ValueError("time must be HH:MM")
            hh = int(hour)
            mm = int(minute)
            if hh < 0 or hh > 23 or mm < 0 or mm > 59:
                raise ValueError("time must be HH:MM")
        return value

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except Exception as exc:  # pragma: no cover
            raise ValueError("invalid timezone") from exc
        return value

    @model_validator(mode="after")
    def validate_limits(self) -> "AppConfig":
        if len(self.important_threads) > self.window_limit:
            raise ValueError("important_threads count exceeds window_limit")
        return self


def load_config(path: str | Path) -> AppConfig:
    config_path = Path(path)
    try:
        data = yaml.safe_load(config_path.read_text())
        if not isinstance(data, dict):
            raise ConfigError("config root must be object")
        return AppConfig.model_validate(data)
    except (OSError, ValidationError, ConfigError) as exc:
        raise ConfigError(str(exc)) from exc
