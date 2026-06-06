import pytest

from app.parsing import parse_socks


def test_no_auth():
    e = parse_socks("1.2.3.4:8080")
    assert e.address == "1.2.3.4" and e.port == 8080
    assert e.user is None and e.password is None


def test_with_auth():
    e = parse_socks("5.6.7.8:1080:bob:secret")
    assert e.address == "5.6.7.8" and e.port == 1080
    assert e.user == "bob" and e.password == "secret"


def test_strips_whitespace():
    assert parse_socks("  1.2.3.4:8080  ").port == 8080


@pytest.mark.parametrize("bad", [
    "1.2.3.4",                 # 缺端口
    "1.2.3.4:8080:user",       # 3 段
    "1.2.3.4:notaport",        # 端口非数字
    "1.2.3.4:70000",           # 端口越界
    "",                        # 空
])
def test_invalid_raises(bad):
    with pytest.raises(ValueError):
        parse_socks(bad)
