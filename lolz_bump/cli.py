from __future__ import annotations

import argparse
import asyncio
import logging
import os
from pathlib import Path

import aiohttp

from .config import load_config
from .db import Database
from .lolz_api import bump_thread
from .service import execute_window, run_scheduler


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="LOLZ bump scheduler")
    parser.add_argument("--config", default="config.yml", help="Path to YAML config")
    parser.add_argument("--db", default="state.db", help="Path to SQLite file")
    parser.add_argument("--dry-run", action="store_true", help="Execute one window and exit")
    return parser


async def run_async(config_path: str, db_path: str, dry_run: bool) -> None:
    config = load_config(config_path)
    token = os.getenv("LOLZ_API_TOKEN")
    if not token:
        raise RuntimeError("LOLZ_API_TOKEN is required")

    db = Database(db_path)

    timeout = aiohttp.ClientTimeout(total=config.api_timeout_seconds)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async def perform_bump(thread_id: int):
            return await bump_thread(
                session=session,
                token=token,
                thread_id=thread_id,
                timeout_seconds=config.api_timeout_seconds,
            )

        if dry_run:
            summary = await execute_window(
                config=config,
                db=db,
                bump_func=perform_bump,
                window_started_at="dry-run",
            )
            logging.info(
                "dry_run_finished",
                extra={
                    "total_planned": summary.total_planned,
                    "success_count": summary.success_count,
                    "failed_count": summary.failed_count,
                },
            )
            return

        await run_scheduler(
            config=config,
            db=db,
            bump_func=perform_bump,
            timezone_name=config.timezone,
        )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    parser = build_arg_parser()
    args = parser.parse_args()
    asyncio.run(run_async(config_path=args.config, db_path=args.db, dry_run=args.dry_run))
