from pathlib import Path

import pytest

from lolz_bump.config import AppConfig
from lolz_bump.db import Database
from lolz_bump.lolz_api import BumpResult
from lolz_bump.service import execute_window


@pytest.mark.asyncio
async def test_execute_window_priorities_and_rotation(tmp_path: Path) -> None:
    db = Database(tmp_path / "state.db")
    config = AppConfig(
        window_limit=5,
        timezone="Europe/Moscow",
        schedule_times=["06:00", "18:00"],
        important_threads=[1, 2, 3],
        regular_threads=[10, 11, 12],
    )

    called: list[int] = []

    async def fake_bump(thread_id: int) -> BumpResult:
        called.append(thread_id)
        return BumpResult(
            success=True,
            thread_id=thread_id,
            status_code=200,
            attempts=1,
            payload={"ok": True},
            error_message=None,
        )

    summary1 = await execute_window(config=config, db=db, bump_func=fake_bump, window_started_at="2026-03-02T06:00:00+03:00")
    summary2 = await execute_window(config=config, db=db, bump_func=fake_bump, window_started_at="2026-03-02T18:00:00+03:00")

    assert summary1.total_planned == 5
    assert summary2.total_planned == 5
    assert called == [1, 2, 3, 10, 11, 1, 2, 3, 12, 10]
    assert db.get_regular_index() == 1


def test_build_cron_specs() -> None:
    from lolz_bump.service import parse_schedule_specs

    specs = parse_schedule_specs(["06:00", "18:15"])
    assert specs == [(6, 0), (18, 15)]
