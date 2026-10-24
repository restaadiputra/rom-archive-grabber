from collections.abc import AsyncIterator

import httpx
import pytest
import respx

from rom_archive_grabber.adapters import http_client
from rom_archive_grabber.adapters.http_client import HttpxClient, user_agent
from rom_archive_grabber.domain.ports import HttpError

UA = "rom-archive-grabber/0.1.0 (+https://github.com/restaadiputra/rom-archive-grabber)"


@pytest.fixture
def sleeps(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    delays: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        delays.append(seconds)

    monkeypatch.setattr(http_client, "_sleep", fake_sleep)
    return delays


@pytest.fixture
async def client() -> AsyncIterator[HttpxClient]:
    instance = HttpxClient(UA)
    yield instance
    await instance.aclose()


def test_user_agent_string() -> None:
    assert user_agent("0.1.0") == UA


@respx.mock
async def test_retries_then_succeeds_on_503(client: HttpxClient, sleeps: list[float]) -> None:
    route = respx.get("https://example.com/a.txt").mock(
        side_effect=[
            httpx.Response(503),
            httpx.Response(503),
            httpx.Response(200, text="hi", headers={"content-type": "text/plain"}),
        ]
    )
    text, content_type = await client.get_text("https://example.com/a.txt")
    assert (text, content_type) == ("hi", "text/plain")
    assert route.call_count == 3
    assert sleeps == [0.5, 1.0]
    assert route.calls.last.request.headers["user-agent"] == UA


@respx.mock
async def test_raises_http_error_after_404(client: HttpxClient, sleeps: list[float]) -> None:
    respx.get("https://example.com/missing").mock(return_value=httpx.Response(404))
    with pytest.raises(HttpError) as info:
        await client.get_text("https://example.com/missing")
    assert info.value.status == 404
    assert "https://example.com/missing" in str(info.value)
    assert sleeps == []


@respx.mock
async def test_connection_errors_exhaust_retries(client: HttpxClient, sleeps: list[float]) -> None:
    respx.get("https://example.com/down").mock(side_effect=httpx.ConnectError("boom"))
    with pytest.raises(HttpError) as info:
        await client.get_json("https://example.com/down")
    assert info.value.status is None
    assert sleeps == [0.5, 1.0, 2.0]


@respx.mock
async def test_get_json_passes_params(client: HttpxClient) -> None:
    route = respx.get("https://example.org/api").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    assert await client.get_json("https://example.org/api", {"q": "x"}) == {"ok": True}
    assert route.calls.last.request.url.params["q"] == "x"


@respx.mock
async def test_stream_sends_range_header(client: HttpxClient) -> None:
    route = respx.get("https://example.com/big.zip").mock(
        return_value=httpx.Response(206, content=b"abcdef")
    )
    async with client.stream("https://example.com/big.zip", 100) as response:
        body = b"".join([chunk async for chunk in response.chunks()])
        assert response.status == 206
    assert body == b"abcdef"
    request = route.calls.last.request
    assert request.headers["range"] == "bytes=100-"
    assert request.headers["user-agent"] == UA


@respx.mock
async def test_stream_without_start_omits_range(client: HttpxClient) -> None:
    route = respx.get("https://example.com/big.zip").mock(
        return_value=httpx.Response(200, content=b"x")
    )
    async with client.stream("https://example.com/big.zip") as response:
        assert response.status == 200
    assert "range" not in route.calls.last.request.headers


async def _broken_body() -> AsyncIterator[bytes]:
    yield b"abc"
    raise httpx.ReadError("connection reset")


@respx.mock
async def test_stream_read_error_becomes_http_error(client: HttpxClient) -> None:
    respx.get("https://example.com/big.zip").mock(
        return_value=httpx.Response(200, content=_broken_body())
    )
    async with client.stream("https://example.com/big.zip") as response:
        received: list[bytes] = []
        with pytest.raises(HttpError) as raised:
            async for chunk in response.chunks():
                received.append(chunk)
    assert received == [b"abc"]
    assert raised.value.status is None
