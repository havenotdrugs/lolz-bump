from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Callable

import aiohttp

API_BASE = "https://api.lolz.live"
DEFAULT_API_TIMEOUT_SECONDS = 30.0


@dataclass(frozen=True)
class BumpResult:
    success: bool
    thread_id: int
    status_code: int | None
    attempts: int
    payload: dict[str, Any] | None
    error_message: str | None


async def bump_thread(
    session: aiohttp.ClientSession,
    token: str,
    thread_id: int,
    timeout_seconds: float = DEFAULT_API_TIMEOUT_SECONDS,
    max_attempts: int = 5,
    sleep_func: Callable[[float], Any] = asyncio.sleep,
) -> BumpResult:
    url = f"{API_BASE}/threads/{thread_id}/bump"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }

    for attempt in range(1, max_attempts + 1):
        try:
            async with session.post(url, headers=headers, timeout=timeout_seconds) as response:
                status = response.status
                if status == 429:
                    retry_after_header = response.headers.get("Retry-After", "")
                    retry_after = float(retry_after_header) if retry_after_header.isdigit() else min(60, 2**attempt)
                    await sleep_func(retry_after)
                    continue

                if 500 <= status < 600:
                    await sleep_func(min(30, 2**attempt))
                    continue

                if status >= 400:
                    return BumpResult(
                        success=False,
                        thread_id=thread_id,
                        status_code=status,
                        attempts=attempt,
                        payload=None,
                        error_message=f"request failed with status {status}",
                    )

                payload = await response.json()
                return BumpResult(
                    success=True,
                    thread_id=thread_id,
                    status_code=status,
                    attempts=attempt,
                    payload=payload,
                    error_message=None,
                )
        except (aiohttp.ClientError, asyncio.TimeoutError):
            if attempt == max_attempts:
                return BumpResult(
                    success=False,
                    thread_id=thread_id,
                    status_code=None,
                    attempts=attempt,
                    payload=None,
                    error_message="request failed after retries",
                )
            await sleep_func(min(30, 2**attempt))

    return BumpResult(
        success=False,
        thread_id=thread_id,
        status_code=None,
        attempts=max_attempts,
        payload=None,
        error_message="request failed after retries",
    )
