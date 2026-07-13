from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

DEFAULT_THREAD_DOMAIN = "lolz.live"
SUPPORTED_THREAD_DOMAINS = frozenset({DEFAULT_THREAD_DOMAIN, "zelenka.guru"})


def validate_schedule_times(value: list[str], field_name: str) -> list[str]:
    for item in value:
        parts = item.split(":")
        if len(parts) != 2:
            raise ValueError(f"{field_name} time must be HH:MM")
        hour, minute = parts
        if not (hour.isdigit() and minute.isdigit()):
            raise ValueError(f"{field_name} time must be HH:MM")
        if not (0 <= int(hour) <= 23 and 0 <= int(minute) <= 59):
            raise ValueError(f"{field_name} time must be HH:MM")
    return sorted(set(value))


class SchedulingSettings(BaseModel):
    window_limit: int = Field(default=1, gt=0)
    schedule_times: list[str] = Field(default_factory=list)
    important_threads: list[int] = Field(default_factory=list)
    regular_threads: list[int] = Field(default_factory=list)
    thread_domains: dict[int, str] = Field(default_factory=dict)
    thread_schedule_overrides: dict[int, list[str]] = Field(default_factory=dict)

    @field_validator("important_threads", "regular_threads", mode="before")
    @classmethod
    def normalize_thread_lists(cls, value: Any) -> Any:
        return [] if value is None else value

    @field_validator("important_threads", "regular_threads")
    @classmethod
    def validate_thread_ids(cls, value: list[int]) -> list[int]:
        if any(thread_id <= 0 for thread_id in value):
            raise ValueError("thread ids must be positive")
        if len(value) > 500:
            raise ValueError("too many threads")
        return list(dict.fromkeys(value))

    @field_validator("schedule_times")
    @classmethod
    def validate_root_schedule_times(cls, value: list[str]) -> list[str]:
        return validate_schedule_times(value, "schedule_times")

    @field_validator("thread_domains", mode="before")
    @classmethod
    def normalize_thread_domains(cls, value: Any) -> Any:
        return {} if value is None else value

    @field_validator("thread_domains")
    @classmethod
    def validate_thread_domains(cls, value: dict[int, str]) -> dict[int, str]:
        if any(thread_id <= 0 for thread_id in value):
            raise ValueError("thread domain ids must be positive")
        if any(domain and domain not in SUPPORTED_THREAD_DOMAINS for domain in value.values()):
            raise ValueError("unsupported thread domain")
        return value

    @field_validator("thread_schedule_overrides", mode="before")
    @classmethod
    def normalize_schedule_overrides(cls, value: Any) -> Any:
        return {} if value is None else value

    @field_validator("thread_schedule_overrides")
    @classmethod
    def validate_thread_schedule_overrides(
        cls,
        value: dict[int, list[str]],
    ) -> dict[int, list[str]]:
        return {
            thread_id: validate_schedule_times(schedule_times, f"thread_schedule_overrides[{thread_id}]")
            for thread_id, schedule_times in value.items()
        }

    @model_validator(mode="after")
    def validate_limits(self) -> "SchedulingSettings":
        if set(self.important_threads) & set(self.regular_threads):
            raise ValueError("thread cannot be both important and regular")
        configured_threads = set(self.important_threads + self.regular_threads)
        unknown_domain_threads = set(self.thread_domains) - configured_threads
        if unknown_domain_threads:
            raise ValueError("thread_domains contains unknown thread ids")
        unknown_override_threads = set(self.thread_schedule_overrides) - configured_threads
        if unknown_override_threads:
            raise ValueError("thread_schedule_overrides contains unknown thread ids")
        self.thread_domains = {
            thread_id: self.thread_domains.get(thread_id) or DEFAULT_THREAD_DOMAIN
            for thread_id in configured_threads
        }
        for schedule_time in self.all_schedule_times():
            important_count = sum(
                1
                for thread_id in self.important_threads
                if self.is_thread_scheduled(thread_id, schedule_time)
            )
            if important_count > self.window_limit:
                raise ValueError("important_threads count exceeds window_limit for at least one schedule")
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
