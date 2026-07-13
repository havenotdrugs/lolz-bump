from pathlib import Path

import pytest

from lolz_bump.db import Database
from lolz_bump.lolz_api import BumpResult
from lolz_bump.scheduler import SchedulerController
from lolz_bump.settings import SchedulingSettings


@pytest.mark.asyncio
async def test_scheduler_reloads_jobs_and_notifies_after_window(tmp_path: Path) -> None:
    db = Database(tmp_path / "state.db")
    db.save_settings(SchedulingSettings(schedule_times=["06:00"], regular_threads=[10]))
    notified = []

    async def bump(thread_id: int) -> BumpResult:
        return BumpResult(True, thread_id, 200, 1, {"ok": True}, None)

    async def notify(summary) -> None:
        notified.append(summary)

    controller = SchedulerController(db=db, bump_func=bump, on_window_finished=notify)
    controller.reload()
    await controller.run_window("06:00")

    assert [job.id for job in controller.jobs] == ["window:06:00"]
    assert notified[0].selected_thread_ids == (10,)
    controller.shutdown()


@pytest.mark.asyncio
async def test_scheduler_keeps_window_result_when_notification_fails(tmp_path: Path) -> None:
    db = Database(tmp_path / "state.db")
    db.save_settings(SchedulingSettings(schedule_times=["06:00"], regular_threads=[10]))

    async def bump(thread_id: int) -> BumpResult:
        return BumpResult(True, thread_id, 200, 1, {"ok": True}, None)

    async def notify(summary) -> None:
        raise RuntimeError("Telegram is unavailable")

    controller = SchedulerController(db=db, bump_func=bump, on_window_finished=notify)

    await controller.run_window("06:00")

    assert db.list_attempts()[0]["success"] is True
