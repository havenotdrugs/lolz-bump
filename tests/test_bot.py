from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import datetime
from typing import Any

import pytest
from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.methods import TelegramMethod
from aiogram.methods.base import TelegramType
from aiogram.types import CallbackQuery, Chat, Message, Update, User

from lolz_bump.bot import TelegramControl, parse_thread_reference
from lolz_bump.lolz_api import BumpResult
from lolz_bump.settings import PostingTemplate, SchedulingSettings


class FakeDatabase:
    def __init__(self, settings: SchedulingSettings | None = None) -> None:
        self.settings = settings or SchedulingSettings()

    def get_settings(self) -> SchedulingSettings:
        return self.settings

    def save_settings(self, settings: SchedulingSettings) -> None:
        self.settings = settings


class LocalBotSession(BaseSession):
    async def close(self) -> None:
        pass

    async def make_request(
        self,
        bot: Bot,
        method: TelegramMethod[TelegramType],
        timeout: int | None = None,
    ) -> TelegramType:
        return True

    async def stream_content(
        self,
        url: str,
        headers: dict[str, Any] | None = None,
        timeout: int = 30,
        chunk_size: int = 65536,
        raise_for_status: bool = True,
    ) -> AsyncGenerator[bytes, None]:
        if False:
            yield b""


class RecordingBotSession(BaseSession):
    def __init__(self) -> None:
        super().__init__()
        self.methods: list[str] = []
        self.next_message_id = 100

    async def close(self) -> None:
        pass

    async def make_request(
        self,
        bot: Bot,
        method: TelegramMethod[TelegramType],
        timeout: int | None = None,
    ) -> TelegramType:
        self.methods.append(method.__api_method__)
        if method.__api_method__ == "sendMessage":
            self.next_message_id += 1
            return Message(
                message_id=self.next_message_id,
                date=datetime.now(),
                chat=Chat(id=1, type="private"),
            )
        return True

    async def stream_content(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        timeout: int = 30,
        chunk_size: int = 65536,
        raise_for_status: bool = True,
    ) -> AsyncGenerator[bytes, None]:
        if False:
            yield b""


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("9734917", (9734917, "lolz.live")),
        ("https://lolz.live/threads/9734917/", (9734917, "lolz.live")),
        ("https://lolz.live/threads/9734917/unread", (9734917, "lolz.live")),
        ("https://zelenka.guru/threads/9734917", (9734917, "zelenka.guru")),
        ("https://zelenka.guru/threads/9734917/unread?foo=bar", (9734917, "zelenka.guru")),
    ],
)
def test_parse_thread_reference_accepts_id_and_lolz_urls(value: str, expected: tuple[int, str]) -> None:
    assert parse_thread_reference(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "0",
        "https://lolz.live/threads/0",
        "http://lolz.live/threads/9734917",
        "https://lolz.live.example/threads/9734917",
        "https://example.com/threads/9734917",
        "https://lolz.live/threads/not-an-id",
    ],
)
def test_parse_thread_reference_rejects_invalid_values(value: str) -> None:
    with pytest.raises(ValueError):
        parse_thread_reference(value)


async def test_adding_thread_url_preserves_domain_and_card_shows_it() -> None:
    control = object.__new__(TelegramControl)
    control._db = FakeDatabase()
    control._pending = {}
    control._reload_scheduler = lambda: None
    control._check_thread = lambda thread_id: _successful_check(thread_id)
    shown: list[str] = []

    async def show(user_id: int, chat_id: int, text: str, keyboard: object) -> None:
        shown.append(text)

    control._show = show

    await control._input(
        user_id=1,
        chat_id=1,
        pending=("thread_id", ("regular", "0")),
        value="https://zelenka.guru/threads/9734917/unread",
    )
    await control._input(user_id=1, chat_id=1, pending=control._pending[1], value="05:00\n17:00")
    await control._thread(user_id=1, chat_id=1, priority="regular", thread_id=9734917, page=0)

    assert control._db.settings.regular_threads == [9734917]
    assert control._db.settings.thread_domains == {9734917: "zelenka.guru"}
    assert shown[-1] == "Тема https://zelenka.guru/threads/9734917/\nГрафик:\n05:00\n17:00"


async def test_creating_posting_template_from_bot_input_persists_it() -> None:
    control = object.__new__(TelegramControl)
    control._db = FakeDatabase()
    control._pending = {}
    control._reload_scheduler = lambda: None
    shown: list[str] = []

    async def show(user_id: int, chat_id: int, text: str, keyboard: object) -> None:
        shown.append(text)

    control._show = show

    await control._input(1, 1, ("template_name", ()), "Рабочий день")
    await control._input(1, 1, control._pending[1], "17:00\n06:00")

    assert control._db.settings.posting_templates == [
        PostingTemplate(id=1, name="Рабочий день", schedule_times=["06:00", "17:00"])
    ]


async def test_posting_template_can_be_renamed_edited_and_deleted() -> None:
    control = object.__new__(TelegramControl)
    control._db = FakeDatabase(
        SchedulingSettings(
            posting_templates=[PostingTemplate(id=4, name="Старое", schedule_times=["06:00"])]
        )
    )
    control._pending = {}
    control._reload_scheduler = lambda: None

    async def show(user_id: int, chat_id: int, text: str, keyboard: object) -> None:
        pass

    control._show = show

    await control._input(1, 1, ("template_rename", ("4",)), "Новое")
    await control._input(1, 1, ("template_schedule", ("4",)), "07:00\n19:00")

    assert control._db.settings.posting_templates == [
        PostingTemplate(id=4, name="Новое", schedule_times=["07:00", "19:00"])
    ]

    await control._delete_template(1, 1, 4)
    assert control._db.settings.posting_templates == []


async def test_applying_posting_template_copies_schedule_to_new_thread() -> None:
    control = object.__new__(TelegramControl)
    control._db = FakeDatabase(
        SchedulingSettings(
            posting_templates=[PostingTemplate(id=7, name="Утро", schedule_times=["06:00", "09:00"])]
        )
    )
    control._pending = {
        1: ("new_schedule", ("regular", "0", "9734917", "lolz.live")),
    }
    control._reload_scheduler = lambda: None
    shown: list[str] = []

    async def show(user_id: int, chat_id: int, text: str, keyboard: object) -> None:
        shown.append(text)

    control._show = show

    await control._apply_template(1, 1, 7)

    assert control._db.settings.regular_threads == [9734917]
    assert control._db.settings.thread_domains == {9734917: "lolz.live"}
    assert control._db.settings.thread_schedule_overrides == {9734917: ["06:00", "09:00"]}

    control._db.settings.posting_templates[0].schedule_times = ["18:00"]
    assert control._db.settings.thread_schedule_overrides[9734917] == ["06:00", "09:00"]


async def test_callback_flow_applies_template_to_existing_thread() -> None:
    control = TelegramControl(
        token="123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi",
        admin_ids={1},
        db=FakeDatabase(
            SchedulingSettings(
                regular_threads=[42],
                thread_domains={42: "lolz.live"},
                posting_templates=[PostingTemplate(id=7, name="Утро", schedule_times=["06:00"])],
            )
        ),
        secrets=object(),
        reload_scheduler=lambda: None,
        check_thread=_successful_check,
    )
    await control._bot.session.close()
    control._bot.session = LocalBotSession()
    shown: list[str] = []

    async def show(user_id: int, chat_id: int, text: str, keyboard: object) -> None:
        shown.append(text)

    control._show = show
    dispatcher = Dispatcher()
    dispatcher.include_router(control._router)
    user = User(id=1, is_bot=False, first_name="Admin")
    message = Message(
        message_id=1,
        date=datetime.now(),
        chat=Chat(id=1, type="private"),
        from_user=user,
    )

    async def feed(update_id: int, data: str) -> None:
        await dispatcher.feed_update(
            control._bot,
            Update(
                update_id=update_id,
                callback_query=CallbackQuery(
                    id=str(update_id),
                    from_user=user,
                    chat_instance="test",
                    message=message,
                    data=data,
                ),
            ),
        )

    try:
        await feed(1, "schedule:regular:42:0")
        await feed(2, "schedule_templates:0")
        await feed(3, "use_template:7")
    finally:
        await control.close()

    assert "Выберите способ задания графика." in shown[0]
    assert "Выберите шаблон постинга." in shown[1]
    assert control._db.settings.thread_schedule_overrides == {42: ["06:00"]}


@pytest.mark.parametrize("token_configured", [True, False])
async def test_start_sends_new_dashboard_and_following_callback_edits_it(token_configured: bool) -> None:
    class DashboardDatabase(FakeDatabase):
        def __init__(self) -> None:
            super().__init__()
            self.dashboard = (1, 99)
            self.token = "configured" if token_configured else None

        def get_encrypted_lolz_token(self) -> str | None:
            return self.token

        def get_dashboard_message(self, user_id: int) -> tuple[int, int]:
            return self.dashboard

        def set_dashboard_message(self, user_id: int, chat_id: int, message_id: int) -> None:
            self.dashboard = (chat_id, message_id)

    control = TelegramControl(
        token="123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi",
        admin_ids={1},
        db=DashboardDatabase(),
        secrets=object(),
        reload_scheduler=lambda: None,
        check_thread=_successful_check,
    )
    await control._bot.session.close()
    session = RecordingBotSession()
    control._bot.session = session
    dispatcher = Dispatcher()
    dispatcher.include_router(control._router)
    user = User(id=1, is_bot=False, first_name="Admin")

    try:
        await dispatcher.feed_update(
            control._bot,
            Update(
                update_id=1,
                message=Message(
                    message_id=10,
                    date=datetime.now(),
                    chat=Chat(id=1, type="private"),
                    from_user=user,
                    text="/start",
                ),
            ),
        )
        await dispatcher.feed_update(
            control._bot,
            Update(
                update_id=2,
                message=Message(
                    message_id=11,
                    date=datetime.now(),
                    chat=Chat(id=1, type="private"),
                    from_user=user,
                    text="/start",
                ),
            ),
        )
        await dispatcher.feed_update(
            control._bot,
            Update(
                update_id=3,
                callback_query=CallbackQuery(
                    id="3",
                    from_user=user,
                    chat_instance="test",
                    message=Message(
                        message_id=101,
                        date=datetime.now(),
                        chat=Chat(id=1, type="private"),
                        from_user=User(id=999, is_bot=True, first_name="Bot"),
                    ),
                    data="system",
                ),
            ),
        )
    finally:
        await control.close()

    assert session.methods == ["sendMessage", "sendMessage", "answerCallbackQuery", "editMessageText"]
    assert control._db.dashboard == (1, 102)


async def test_message_handler_passes_url_to_thread_input() -> None:
    control = TelegramControl(
        token="123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi",
        admin_ids={1},
        db=FakeDatabase(),
        secrets=object(),
        reload_scheduler=lambda: None,
        check_thread=_successful_check,
    )
    await control._bot.session.close()
    control._bot.session = LocalBotSession()
    received: list[tuple[tuple[str, tuple[str, ...]], str]] = []

    async def receive(user_id: int, chat_id: int, pending: tuple[str, tuple[str, ...]], value: str) -> None:
        received.append((pending, value))

    control._input = receive
    control._pending[1] = ("thread_id", ("regular", "0"))
    dispatcher = Dispatcher()
    dispatcher.include_router(control._router)
    update = Update(
        update_id=1,
        message=Message(
            message_id=1,
            date=datetime.now(),
            chat=Chat(id=1, type="private"),
            from_user=User(id=1, is_bot=False, first_name="Admin"),
            text="https://zelenka.guru/threads/9734917/unread",
        ),
    )

    try:
        await dispatcher.feed_update(control._bot, update)
    finally:
        await control.close()

    assert received == [(("thread_id", ("regular", "0")), "https://zelenka.guru/threads/9734917/unread")]


async def _successful_check(thread_id: int) -> BumpResult:
    return BumpResult(True, thread_id, 200, 1, {}, None)
