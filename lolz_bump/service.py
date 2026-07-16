from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Awaitable, Callable

from .db import BumpAttemptCreate, Database
from .domain import Priority, select_threads_for_window
from .lolz_api import BumpResult
from .settings import SchedulingSettings

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class WindowSummary:
    schedule_time: str
    total_planned: int
    success_count: int
    failed_count: int
    selected_thread_ids: tuple[int, ...]
    skipped_thread_ids: tuple[int, ...]


def parse_schedule_specs(schedule_times: list[str]) -> list[tuple[int, int]]:
    result: list[tuple[int, int]] = []
    for item in schedule_times:
        hour_raw, minute_raw = item.split(":")
        result.append((int(hour_raw), int(minute_raw)))
    return result


async def execute_window(
    config: SchedulingSettings,
    db: Database,
    bump_func: Callable[[int], Awaitable[BumpResult]],
    window_started_at: str,
    schedule_time: str,
) -> WindowSummary:
    active_thread_ids = {
        thread_id
        for thread_id in config.important_threads + config.regular_threads
        if config.is_thread_scheduled(thread_id, schedule_time)
    }
    selected = select_threads_for_window(
        important_threads=config.important_threads,
        regular_threads=config.regular_threads,
        active_thread_ids=active_thread_ids,
    )
    selected_thread_ids = [planned.thread_id for planned in selected]
    skipped_thread_ids = [
        thread_id
        for thread_id in config.important_threads + config.regular_threads
        if thread_id not in active_thread_ids
    ]
    LOGGER.info(
        "window_started schedule_time=%s window_started_at=%s selected=%s skipped_by_schedule=%s",
        schedule_time,
        window_started_at,
        selected_thread_ids,
        skipped_thread_ids,
    )

    success_count = 0
    failed_count = 0
    for planned in selected:
        result = await bump_func(planned.thread_id)
        db.insert_attempt(
            BumpAttemptCreate(
                window_started_at=window_started_at,
                thread_id=planned.thread_id,
                priority=planned.priority.value,
                success=result.success,
                status_code=result.status_code,
                error_message=result.error_message,
            )
        )

        log_method = LOGGER.info if result.success else LOGGER.warning
        log_method(
            "bump_attempt schedule_time=%s thread_id=%s priority=%s success=%s status_code=%s attempts=%s error=%s",
            schedule_time,
            planned.thread_id,
            planned.priority.value,
            result.success,
            result.status_code,
            result.attempts,
            result.error_message,
        )

        if result.success:
            success_count += 1
        else:
            failed_count += 1

    return WindowSummary(
        schedule_time=schedule_time,
        total_planned=len(selected),
        success_count=success_count,
        failed_count=failed_count,
        selected_thread_ids=tuple(selected_thread_ids),
        skipped_thread_ids=tuple(skipped_thread_ids),
    )
