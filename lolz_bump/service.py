from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Awaitable, Callable
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from .config import AppConfig
from .db import BumpAttemptCreate, Database
from .domain import select_threads_for_window
from .lolz_api import BumpResult

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class WindowSummary:
    total_planned: int
    success_count: int
    failed_count: int


def parse_schedule_specs(schedule_times: list[str]) -> list[tuple[int, int]]:
    result: list[tuple[int, int]] = []
    for item in schedule_times:
        hour_raw, minute_raw = item.split(":")
        result.append((int(hour_raw), int(minute_raw)))
    return result


async def execute_window(
    config: AppConfig,
    db: Database,
    bump_func: Callable[[int], Awaitable[BumpResult]],
    window_started_at: str,
) -> WindowSummary:
    regular_index = db.get_regular_index()
    selected, next_regular_index = select_threads_for_window(
        important_threads=config.important_threads,
        regular_threads=config.regular_threads,
        window_limit=config.window_limit,
        regular_index=regular_index,
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

        if result.success:
            success_count += 1
        else:
            failed_count += 1
            LOGGER.warning(
                "bump_failed",
                extra={
                    "thread_id": planned.thread_id,
                    "status_code": result.status_code,
                    "error": result.error_message,
                },
            )

    db.set_regular_index(next_regular_index)

    return WindowSummary(
        total_planned=len(selected),
        success_count=success_count,
        failed_count=failed_count,
    )


async def run_scheduler(
    config: AppConfig,
    db: Database,
    bump_func: Callable[[int], Awaitable[BumpResult]],
    timezone_name: str,
) -> None:
    timezone = ZoneInfo(timezone_name)
    scheduler = AsyncIOScheduler(timezone=timezone)
    execution_lock = asyncio.Lock()

    async def scheduled_job() -> None:
        if execution_lock.locked():
            LOGGER.warning("previous_window_still_running")
            return

        async with execution_lock:
            now = datetime.now(timezone).isoformat(timespec="seconds")
            summary = await execute_window(
                config=config,
                db=db,
                bump_func=bump_func,
                window_started_at=now,
            )
            LOGGER.info(
                "window_finished",
                extra={
                    "total_planned": summary.total_planned,
                    "success_count": summary.success_count,
                    "failed_count": summary.failed_count,
                },
            )

    for hour, minute in parse_schedule_specs(config.schedule_times):
        scheduler.add_job(
            scheduled_job,
            trigger=CronTrigger(hour=hour, minute=minute, timezone=timezone),
        )

    scheduler.start()
    LOGGER.info("scheduler_started", extra={"schedule_times": config.schedule_times})

    await asyncio.Event().wait()
