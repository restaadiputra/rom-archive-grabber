import asyncio
from collections.abc import AsyncIterator, Mapping
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Any

import httpx

from rom_archive_grabber.domain.ports import HttpError, HttpStream

_RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
_BACKOFF_BASE_SECONDS = 0.5
_TIMEOUT = httpx.Timeout(30.0, connect=15.0)


def user_agent(version: str) -> str:
    return f"rom-archive-grabber/{version} (+https://github.com/restaadiputra/rom-archive-grabber)"


async def _sleep(seconds: float) -> None:
    # Module-level so tests can replace it and skip real waiting.
    await asyncio.sleep(seconds)


class _Stream:
    def __init__(self, response: httpx.Response, url: str) -> None:
        self._response = response
        self._url = url
        self.status: int = response.status_code
        self.headers: Mapping[str, str] = response.headers

    async def chunks(self) -> AsyncIterator[bytes]:
        try:
            async for chunk in self._response.aiter_bytes():
                yield chunk
        except httpx.HTTPError as error:
            raise HttpError(self._url, None) from error


class HttpxClient:
    def __init__(self, user_agent: str, retries: int = 3) -> None:
        self._retries = retries
        self._client = httpx.AsyncClient(
            headers={"User-Agent": user_agent}, follow_redirects=True, timeout=_TIMEOUT
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def get_text(self, url: str) -> tuple[str, str]:
        response = await self._get(url, None)
        return response.text, response.headers.get("content-type", "")

    async def get_json(self, url: str, params: Mapping[str, str] | None = None) -> Any:  # noqa: ANN401  JSON bodies have no fixed shape
        return (await self._get(url, params)).json()

    def stream(self, url: str, start: int = 0) -> AbstractAsyncContextManager[HttpStream]:
        return self._open_stream(url, start)

    @asynccontextmanager
    async def _open_stream(self, url: str, start: int) -> AsyncIterator[HttpStream]:
        headers = {"Range": f"bytes={start}-"} if start > 0 else {}
        try:
            async with self._client.stream("GET", url, headers=headers) as response:
                yield _Stream(response, url)
        except httpx.TransportError as error:
            raise HttpError(url, None) from error

    async def _get(self, url: str, params: Mapping[str, str] | None) -> httpx.Response:
        status: int | None = None
        for attempt in range(self._retries + 1):
            if attempt:
                await _sleep(_BACKOFF_BASE_SECONDS * 2 ** (attempt - 1))
            status = None
            try:
                response = await self._client.get(url, params=params)
            except httpx.TransportError:
                continue
            if response.is_success:
                return response
            status = response.status_code
            if status not in _RETRY_STATUSES:
                break
        raise HttpError(url, status)
