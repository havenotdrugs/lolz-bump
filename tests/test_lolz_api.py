import asyncio

import pytest

from lolz_bump.lolz_api import BumpResult, bump_thread


class FakeResponse:
    def __init__(self, status: int, headers: dict[str, str] | None = None, body: dict | None = None):
        self.status = status
        self.headers = headers or {}
        self._body = body or {"ok": True}

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def json(self):
        return self._body


class FakeSession:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls: list[tuple[tuple, dict]] = []

    def post(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self._responses.pop(0)


@pytest.mark.asyncio
async def test_bump_thread_retries_429_then_success() -> None:
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    session = FakeSession(
        [
            FakeResponse(429, headers={"Retry-After": "abc"}),
            FakeResponse(200, body={"status": "ok"}),
        ]
    )

    result = await bump_thread(
        session=session,
        token="token",
        thread_id=42,
        sleep_func=fake_sleep,
    )

    assert isinstance(result, BumpResult)
    assert result.success is True
    assert result.status_code == 200
    assert sleeps == [1]


@pytest.mark.asyncio
async def test_bump_thread_stops_on_400() -> None:
    session = FakeSession([FakeResponse(400)])

    result = await bump_thread(session=session, token="token", thread_id=42)

    assert result.success is False
    assert result.status_code == 400
    assert result.attempts == 1


@pytest.mark.asyncio
async def test_bump_thread_retries_403_then_success() -> None:
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    session = FakeSession(
        [
            FakeResponse(403),
            FakeResponse(200, body={"status": "ok"}),
        ]
    )

    result = await bump_thread(
        session=session,
        token="token",
        thread_id=42,
        sleep_func=fake_sleep,
    )

    assert result.success is True
    assert result.status_code == 200
    assert result.attempts == 2
    assert sleeps == [1]
