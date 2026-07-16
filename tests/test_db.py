import json
import sqlite3
from pathlib import Path

from lolz_bump.db import BumpAttemptCreate, Database
from lolz_bump.domain import Priority
from lolz_bump.settings import PostingTemplate, SchedulingSettings


def test_insert_attempt(tmp_path: Path) -> None:
    db = Database(tmp_path / "state.db")

    db.insert_attempt(
        BumpAttemptCreate(
            window_started_at="2026-03-02T06:00:00+03:00",
            thread_id=123,
            priority=Priority.IMPORTANT.value,
            success=True,
            status_code=200,
            error_message=None,
        )
    )

    attempts = db.list_attempts()
    assert len(attempts) == 1
    assert attempts[0]["thread_id"] == 123
    assert attempts[0]["success"] is True


def test_scheduling_settings_persist_without_yaml(tmp_path: Path) -> None:
    db = Database(tmp_path / "state.db")
    settings = SchedulingSettings(
        schedule_times=["18:00", "06:00"],
        important_threads=[1],
        regular_threads=[10, 11],
        thread_schedule_overrides={11: ["12:00"]},
    )

    db.save_settings(settings)

    assert Database(tmp_path / "state.db").get_settings() == settings


def test_posting_templates_persist_and_legacy_settings_get_empty_templates(tmp_path: Path) -> None:
    path = tmp_path / "state.db"
    db = Database(path)
    settings = SchedulingSettings(
        posting_templates=[PostingTemplate(id=1, name="Утро", schedule_times=["06:00"])]
    )

    db.save_settings(settings)

    assert Database(path).get_settings().posting_templates == settings.posting_templates

    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE scheduling_settings SET payload = ? WHERE id = 1",
            (json.dumps(SchedulingSettings().model_dump(exclude={"posting_templates"})),),
        )

    assert Database(path).get_settings().posting_templates == []


def test_get_settings_migrates_missing_thread_domains(tmp_path: Path) -> None:
    path = tmp_path / "state.db"
    Database(path)
    legacy_payload = {"window_limit": 1, "schedule_times": [], "important_threads": [], "regular_threads": [42], "thread_schedule_overrides": {}}
    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE scheduling_settings SET payload = ? WHERE id = 1", (json.dumps(legacy_payload),))

    settings = Database(path).get_settings()

    with sqlite3.connect(path) as connection:
        payload = json.loads(connection.execute("SELECT payload FROM scheduling_settings WHERE id = 1").fetchone()[0])
    assert settings.thread_domains == {42: "lolz.live"}
    assert payload["thread_domains"] == {"42": "lolz.live"}
    assert "window_limit" not in payload


def test_token_and_dashboard_are_persisted(tmp_path: Path) -> None:
    db = Database(tmp_path / "state.db")

    db.set_encrypted_lolz_token("encrypted-token")
    db.set_dashboard_message(user_id=123, chat_id=123, message_id=456)

    assert db.get_encrypted_lolz_token() == "encrypted-token"
    assert db.list_dashboard_chats([123, 999]) == [(123, 456)]


def test_attempt_history_is_paginated_with_human_log_fields(tmp_path: Path) -> None:
    db = Database(tmp_path / "state.db")
    for thread_id in [1, 2]:
        db.insert_attempt(
            BumpAttemptCreate("2026-07-13T06:00:00+03:00", thread_id, "regular", False, 403, "forbidden")
        )

    items, total = db.list_attempts_page(page=0, page_size=1)

    assert total == 2
    assert items[0]["thread_id"] == 2
    assert db.get_attempt(items[0]["id"])["error_message"] == "forbidden"
