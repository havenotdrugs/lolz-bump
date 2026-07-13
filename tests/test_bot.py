from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import datetime
from typing import Any

import pytest
from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.methods import TelegramMethod
from aiogram.methods.base import TelegramType
from aiogram.types import Chat, Message, Update, User

from lolz_bump.bot import TelegramControl, parse_thread_reference
from lolz_bump.lolz_api import BumpResult
from lolz_bump.settings import SchedulingSettings


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
