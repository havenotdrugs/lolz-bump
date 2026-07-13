from __future__ import annotations

import asyncio
import os
from pathlib import Path

import aiohttp

from .bot import TelegramControl
from .db import Database
from .lolz_api import BumpResult, bump_thread, get_thread
from .scheduler import SchedulerController
from .secrets import SecretStore


def parse_admin_ids(value: str | None) -> set[int]:
    if not value:
        raise RuntimeError("TELEGRAM_ADMIN_IDS is required")
    try:
        admin_ids = {int(item.strip()) for item in value.split(",") if item.strip()}
    except ValueError as exc:
        raise RuntimeError("TELEGRAM_ADMIN_IDS must contain numeric IDs") from exc
    if not admin_ids or any(item <= 0 for item in admin_ids):
        raise RuntimeError("TELEGRAM_ADMIN_IDS must contain positive IDs")
    return admin_ids


async def run_application() -> None:
    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not telegram_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required")
    db = Database(os.getenv("STATE_DB_PATH", "state.db"))
    key_path = Path("/secrets/app.key") if Path("/secrets").exists() else Path(".secrets/app.key")
    secrets = SecretStore(key_path)
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
        async def perform_bump(thread_id: int) -> BumpResult:
            encrypted_token = db.get_encrypted_lolz_token()
            if encrypted_token is None:
                return BumpResult(False, thread_id, None, 0, None, "LOLZ token is not configured")
            return await bump_thread(
                session=session,
                token=secrets.decrypt(encrypted_token),
                thread_id=thread_id,
            )

        async def check_thread(thread_id: int) -> BumpResult:
            encrypted_token = db.get_encrypted_lolz_token()
            if encrypted_token is None:
                return BumpResult(False, thread_id, None, 0, None, "LOLZ token is not configured")
            return await get_thread(session=session, token=secrets.decrypt(encrypted_token), thread_id=thread_id)

        controller: SchedulerController | None = None

        def reload_scheduler() -> None:
            if controller is not None:
                controller.reload()

        bot = TelegramControl(
            token=telegram_token,
            admin_ids=parse_admin_ids(os.getenv("TELEGRAM_ADMIN_IDS")),
            db=db,
            secrets=secrets,
            reload_scheduler=reload_scheduler,
            check_thread=check_thread,
        )
        controller = SchedulerController(
            db=db,
            bump_func=perform_bump,
            on_window_finished=bot.notify_window_finished,
        )
        controller.start()
        try:
            await bot.run()
        finally:
            controller.shutdown()
            await bot.close()


def main() -> None:
    asyncio.run(run_application())
