from pathlib import Path

from lolz_bump.db import BumpAttemptCreate, Database
from lolz_bump.domain import Priority


def test_regular_index_persists(tmp_path: Path) -> None:
    db_path = tmp_path / "state.db"
    db = Database(db_path)

    assert db.get_regular_index() == 0

    db.set_regular_index(3)
    assert db.get_regular_index() == 3

    db2 = Database(db_path)
    assert db2.get_regular_index() == 3


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
