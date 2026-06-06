import httpx
import respx

from app.notify import TelegramNotifier


def test_disabled_when_unconfigured():
    assert TelegramNotifier("", "").enabled is False
    assert TelegramNotifier("tok", "").enabled is False
    assert TelegramNotifier("tok", "123").enabled is True


def test_disabled_send_is_noop():
    assert TelegramNotifier("", "").send("hi") is False


@respx.mock
def test_send_posts_to_telegram():
    route = respx.post("https://api.telegram.org/bot TOK/sendMessage".replace(" ", "")).mock(
        return_value=httpx.Response(200, json={"ok": True}))
    n = TelegramNotifier("TOK", "999", client=httpx.Client())
    assert n.send("hello") is True
    body = route.calls.last.request.content
    assert b"999" in body and b"hello" in body
