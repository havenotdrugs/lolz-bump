from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import Boolean, Integer, String, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column


class Base(DeclarativeBase):
    pass


class RuntimeState(Base):
    __tablename__ = "runtime_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    regular_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class BumpAttempt(Base):
    __tablename__ = "bump_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    window_started_at: Mapped[str] = mapped_column(String, nullable=False)
    thread_id: Mapped[int] = mapped_column(Integer, nullable=False)
    priority: Mapped[str] = mapped_column(String, nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)


@dataclass(frozen=True)
class BumpAttemptCreate:
    window_started_at: str
    thread_id: int
    priority: str
    success: bool
    status_code: int | None
    error_message: str | None


class Database:
    def __init__(self, sqlite_path: str | Path) -> None:
        self._engine = create_engine(f"sqlite:///{Path(sqlite_path)}")
        Base.metadata.create_all(self._engine)
        self._ensure_runtime_state_row()

    def _ensure_runtime_state_row(self) -> None:
        with Session(self._engine) as session:
            state = session.get(RuntimeState, 1)
            if state is None:
                session.add(RuntimeState(id=1, regular_index=0))
                session.commit()

    def get_regular_index(self) -> int:
        with Session(self._engine) as session:
            state = session.get(RuntimeState, 1)
            if state is None:  # pragma: no cover
                return 0
            return state.regular_index

    def set_regular_index(self, value: int) -> None:
        with Session(self._engine) as session:
            state = session.get(RuntimeState, 1)
            if state is None:  # pragma: no cover
                state = RuntimeState(id=1, regular_index=value)
                session.add(state)
            else:
                state.regular_index = value
            session.commit()

    def insert_attempt(self, attempt: BumpAttemptCreate) -> None:
        with Session(self._engine) as session:
            session.add(
                BumpAttempt(
                    window_started_at=attempt.window_started_at,
                    thread_id=attempt.thread_id,
                    priority=attempt.priority,
                    success=attempt.success,
                    status_code=attempt.status_code,
                    error_message=attempt.error_message,
                )
            )
            session.commit()

    def list_attempts(self) -> list[dict[str, object]]:
        with Session(self._engine) as session:
            items = session.scalars(select(BumpAttempt).order_by(BumpAttempt.id.asc())).all()
            return [
                {
                    "id": item.id,
                    "thread_id": item.thread_id,
                    "success": item.success,
                    "status_code": item.status_code,
                }
                for item in items
            ]
