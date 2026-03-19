from __future__ import annotations

from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator


class ConfigError(ValueError):
    """Configuration validation error."""


def validate_schedule_times(value: list[str], field_name: str) -> list[str]:
    if not value:
        raise ValueError(f"{field_name} must not be empty")
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


class AppConfig(BaseModel):
    window_limit: int = Field(gt=0)
    api_timeout_seconds: float = Field(default=30.0, gt=0)
    timezone: str
    schedule_times: list[str]
    important_threads: list[int]
    regular_threads: list[int]
    thread_schedule_overrides: dict[int, list[str]] = Field(default_factory=dict)

    @field_validator("important_threads", "regular_threads", mode="before")
    @classmethod
    def normalize_nullable_thread_lists(cls, value: Any) -> Any:
        if value is None:
            return []
        return value

    @field_validator("thread_schedule_overrides", mode="before")
    @classmethod
    def normalize_nullable_thread_schedule_overrides(cls, value: Any) -> Any:
        if value is None:
            return {}
        return value

    @field_validator("schedule_times")
    @classmethod
    def validate_root_schedule_times(cls, value: list[str]) -> list[str]:
        return validate_schedule_times(value, field_name="schedule_times")

    @field_validator("thread_schedule_overrides")
    @classmethod
    def validate_thread_schedule_overrides(
        cls,
        value: dict[int, list[str]],
    ) -> dict[int, list[str]]:
        return {
            thread_id: validate_schedule_times(
                schedule_times,
                field_name=f"thread_schedule_overrides[{thread_id}]",
            )
            for thread_id, schedule_times in value.items()
        }

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
        configured_threads = set(self.important_threads + self.regular_threads)
        unknown_override_threads = set(self.thread_schedule_overrides) - configured_threads
        if unknown_override_threads:
            raise ValueError("thread_schedule_overrides contains unknown thread ids")
        for schedule_time in self.all_schedule_times():
            important_count = sum(
                1
                for thread_id in self.important_threads
                if self.is_thread_scheduled(thread_id, schedule_time)
            )
            if important_count > self.window_limit:
                raise ValueError(
                    "important_threads count exceeds window_limit for at least one schedule"
                )
        return self

    def all_schedule_times(self) -> list[str]:
        schedule_times = set(self.schedule_times)
        for override_schedule_times in self.thread_schedule_overrides.values():
            schedule_times.update(override_schedule_times)
        return sorted(schedule_times)

    def schedule_times_for_thread(self, thread_id: int) -> list[str]:
        return self.thread_schedule_overrides.get(thread_id, self.schedule_times)

    def is_thread_scheduled(self, thread_id: int, schedule_time: str) -> bool:
        return schedule_time in self.schedule_times_for_thread(thread_id)


def load_config(path: str | Path) -> AppConfig:
    config_path = Path(path)
    try:
        data = yaml.safe_load(config_path.read_text())
        if not isinstance(data, dict):
            raise ConfigError("config root must be object")
        return AppConfig.model_validate(data)
    except (OSError, ValidationError, ConfigError) as exc:
        raise ConfigError(str(exc)) from exc
