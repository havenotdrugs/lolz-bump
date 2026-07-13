from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from .db import Database
from .lolz_api import BumpResult
from .service import WindowSummary, execute_window, parse_schedule_specs

LOGGER = logging.getLogger(__name__)
MOSCOW_TIMEZONE = "Europe/Moscow"


class SchedulerController:
    def __init__(
        self,
        db: Database,
        bump_func: Callable[[int], Awaitable[BumpResult]],
        on_window_finished: Callable[[WindowSummary], Awaitable[None]],
    ) -> None:
        self._db = db
        self._bump_func = bump_func
        self._on_window_finished = on_window_finished
        self._timezone = ZoneInfo(MOSCOW_TIMEZONE)
        self._scheduler = AsyncIOScheduler(timezone=self._timezone)
        self._execution_lock = asyncio.Lock()
        self._executed_window_keys: set[str] = set()

    @property
    def jobs(self):
        return self._scheduler.get_jobs()

    def start(self) -> None:
        self.reload()
        self._scheduler.start()
        LOGGER.info("scheduler_started schedule_times=%s", self._db.get_settings().all_schedule_times())

    def shutdown(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)

    def reload(self) -> None:
        self._scheduler.remove_all_jobs()
        for schedule_time in self._db.get_settings().all_schedule_times():
            hour, minute = parse_schedule_specs([schedule_time])[0]
            self._scheduler.add_job(
                self.run_window,
                args=[schedule_time],
                id=f"window:{schedule_time}",
                replace_existing=True,
                trigger=CronTrigger(hour=hour, minute=minute, timezone=self._timezone),
            )

    async def run_window(self, schedule_time: str) -> None:
        window_date = datetime.now(self._timezone).date().isoformat()
        window_key = f"{window_date}T{schedule_time}"
        self._executed_window_keys = {
            key for key in self._executed_window_keys if key.startswith(window_date)
        }
        if window_key in self._executed_window_keys or self._execution_lock.locked():
            return
        async with self._execution_lock:
            if window_key in self._executed_window_keys:
                return
            self._executed_window_keys.add(window_key)
            settings = self._db.get_settings()
            try:
                summary = await execute_window(
                    config=settings,
                    db=self._db,
                    bump_func=self._bump_func,
                    window_started_at=datetime.now(self._timezone).isoformat(timespec="seconds"),
                    schedule_time=schedule_time,
                )
            except Exception:
                LOGGER.exception("window_failed schedule_time=%s window_key=%s", schedule_time, window_key)
                return
            try:
                await self._on_window_finished(summary)
            except Exception:
                LOGGER.exception("window_notification_failed schedule_time=%s", schedule_time)
