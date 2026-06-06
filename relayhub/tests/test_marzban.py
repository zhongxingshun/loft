import httpx
import respx

from app.config import Settings
from app.marzban import MarzbanClient

BASE = "https://panel:8000"


def _client():
    s = Settings(_env_file=None, marzban_url=BASE, admin_user="a", admin_pass="b",
                 verify_tls=False)
    return MarzbanClient(s)


@respx.mock
def test_token_then_get_core_config():
    respx.post(f"{BASE}/api/admin/token").mock(
        return_value=httpx.Response(200, json={"access_token": "T"}))
    route = respx.get(f"{BASE}/api/core/config").mock(
        return_value=httpx.Response(200, json={"outbounds": [], "routing": {"rules": []}}))
    cfg = _client().get_core_config()
    assert cfg == {"outbounds": [], "routing": {"rules": []}}
    # 请求带上了 bearer token
    assert route.calls.last.request.headers["authorization"] == "Bearer T"


@respx.mock
def test_upsert_user_conflict_falls_back_to_put():
    respx.post(f"{BASE}/api/admin/token").mock(
        return_value=httpx.Response(200, json={"access_token": "T"}))
    respx.post(f"{BASE}/api/user").mock(return_value=httpx.Response(409, json={"detail": "exists"}))
    put = respx.put(f"{BASE}/api/user/zhang").mock(
        return_value=httpx.Response(200, json={"username": "zhang", "subscription_url": "/sub/x"}))

    u = _client().upsert_user({"username": "zhang"})
    assert u["username"] == "zhang"
    assert put.called


@respx.mock
def test_http_error_wrapped():
    import pytest
    from app.marzban import MarzbanError
    respx.post(f"{BASE}/api/admin/token").mock(
        return_value=httpx.Response(200, json={"access_token": "T"}))
    respx.get(f"{BASE}/api/core/config").mock(return_value=httpx.Response(500, text="boom"))
    with pytest.raises(MarzbanError):
        _client().get_core_config()
