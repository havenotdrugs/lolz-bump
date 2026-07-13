from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import Boolean, Integer, String, Text, create_engine, func, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from .settings import SchedulingSettings


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


class SchedulingSettingsRecord(Base):
    __tablename__ = "scheduling_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    payload: Mapped[str] = mapped_column(Text, nullable=False)


class SecretRecord(Base):
    __tablename__ = "secrets"

    name: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)


class DashboardRecord(Base):
    __tablename__ = "dashboards"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chat_id: Mapped[int] = mapped_column(Integer, nullable=False)
    message_id: Mapped[int] = mapped_column(Integer, nullable=False)


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
        self._ensure_settings_row()

    def _ensure_runtime_state_row(self) -> None:
        with Session(self._engine) as session:
            state = session.get(RuntimeState, 1)
            if state is None:
                session.add(RuntimeState(id=1, regular_index=0))
                session.commit()

    def _ensure_settings_row(self) -> None:
        with Session(self._engine) as session:
            settings = session.get(SchedulingSettingsRecord, 1)
            if settings is None:
                session.add(
                    SchedulingSettingsRecord(
                        id=1,
                        payload=SchedulingSettings().model_dump_json(),
                    )
                )
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

    def list_attempts_page(self, page: int, page_size: int) -> tuple[list[dict[str, object]], int]:
        offset = max(0, page) * page_size
        with Session(self._engine) as session:
            items = session.scalars(
                select(BumpAttempt).order_by(BumpAttempt.id.desc()).offset(offset).limit(page_size)
            ).all()
            total = session.scalar(select(func.count()).select_from(BumpAttempt)) or 0
            return [
                {
                    "id": item.id,
                    "window_started_at": item.window_started_at,
                    "thread_id": item.thread_id,
                    "priority": item.priority,
                    "success": item.success,
                    "status_code": item.status_code,
                    "error_message": item.error_message,
                }
                for item in items
            ], total

    def get_attempt(self, attempt_id: int) -> dict[str, object] | None:
        with Session(self._engine) as session:
            item = session.get(BumpAttempt, attempt_id)
            if item is None:
                return None
            return {
                "id": item.id,
                "window_started_at": item.window_started_at,
                "thread_id": item.thread_id,
                "priority": item.priority,
                "success": item.success,
                "status_code": item.status_code,
                "error_message": item.error_message,
            }

    def get_settings(self) -> SchedulingSettings:
        with Session(self._engine) as session:
            record = session.get(SchedulingSettingsRecord, 1)
            if record is None:  # pragma: no cover
                return SchedulingSettings()
            settings = SchedulingSettings.model_validate_json(record.payload)
            migrated_payload = settings.model_dump_json()
            if record.payload != migrated_payload:
                record.payload = migrated_payload
                session.commit()
            return settings

    def save_settings(self, settings: SchedulingSettings) -> None:
        with Session(self._engine) as session:
            record = session.get(SchedulingSettingsRecord, 1)
            if record is None:  # pragma: no cover
                session.add(SchedulingSettingsRecord(id=1, payload=settings.model_dump_json()))
            else:
                record.payload = settings.model_dump_json()
            session.commit()

    def set_encrypted_lolz_token(self, value: str) -> None:
        with Session(self._engine) as session:
            record = session.get(SecretRecord, "lolz_api_token")
            if record is None:
                session.add(SecretRecord(name="lolz_api_token", value=value))
            else:
                record.value = value
            session.commit()

    def get_encrypted_lolz_token(self) -> str | None:
        with Session(self._engine) as session:
            record = session.get(SecretRecord, "lolz_api_token")
            return None if record is None else record.value

    def set_dashboard_message(self, user_id: int, chat_id: int, message_id: int) -> None:
        with Session(self._engine) as session:
            record = session.get(DashboardRecord, user_id)
            if record is None:
                session.add(DashboardRecord(user_id=user_id, chat_id=chat_id, message_id=message_id))
            else:
                record.chat_id = chat_id
                record.message_id = message_id
            session.commit()

    def get_dashboard_message(self, user_id: int) -> tuple[int, int] | None:
        with Session(self._engine) as session:
            record = session.get(DashboardRecord, user_id)
            if record is None:
                return None
            return (record.chat_id, record.message_id)

    def list_dashboard_chats(self, user_ids: list[int]) -> list[tuple[int, int]]:
        if not user_ids:
            return []
        with Session(self._engine) as session:
            records = session.scalars(
                select(DashboardRecord).where(DashboardRecord.user_id.in_(user_ids))
            ).all()
            return [(record.chat_id, record.message_id) for record in records]
