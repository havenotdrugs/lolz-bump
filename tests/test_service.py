from pathlib import Path

import pytest

from lolz_bump.config import AppConfig
from lolz_bump.db import Database
from lolz_bump.lolz_api import BumpResult
from lolz_bump.service import execute_window, mark_window_as_started


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

    summary1 = await execute_window(
        config=config,
        db=db,
        bump_func=fake_bump,
        window_started_at="2026-03-02T06:00:00+03:00",
        schedule_time="06:00",
    )
    summary2 = await execute_window(
        config=config,
        db=db,
        bump_func=fake_bump,
        window_started_at="2026-03-02T18:00:00+03:00",
        schedule_time="18:00",
    )

    assert summary1.total_planned == 5
    assert summary2.total_planned == 5
    assert list(summary1.selected_thread_ids) == [1, 2, 3, 10, 11]
    assert list(summary2.selected_thread_ids) == [1, 2, 3, 12, 10]
    assert called == [1, 2, 3, 10, 11, 1, 2, 3, 12, 10]
    assert db.get_regular_index() == 1


def test_build_cron_specs() -> None:
    from lolz_bump.service import parse_schedule_specs

    specs = parse_schedule_specs(["06:00", "18:15"])
    assert specs == [(6, 0), (18, 15)]


@pytest.mark.asyncio
async def test_execute_window_respects_thread_schedule_overrides(tmp_path: Path) -> None:
    db = Database(tmp_path / "state.db")
    config = AppConfig(
        window_limit=3,
        timezone="Europe/Moscow",
        schedule_times=["06:00"],
        important_threads=[1, 2],
        regular_threads=[10, 11, 12],
        thread_schedule_overrides={
            2: ["18:00"],
            10: ["18:00"],
            11: ["06:00"],
            12: ["06:00", "18:00"],
        },
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

    summary = await execute_window(
        config=config,
        db=db,
        bump_func=fake_bump,
        window_started_at="2026-03-02T06:00:00+03:00",
        schedule_time="06:00",
    )

    assert called == [1, 11, 12]
    assert list(summary.selected_thread_ids) == [1, 11, 12]
    assert list(summary.skipped_thread_ids) == [2, 10]
    assert list(summary.deferred_thread_ids) == []


def test_mark_window_as_started_rejects_duplicate_key() -> None:
    executed_window_keys: set[str] = set()

    assert mark_window_as_started(executed_window_keys, "2026-03-20T06:00") is True
    assert mark_window_as_started(executed_window_keys, "2026-03-20T06:00") is False
