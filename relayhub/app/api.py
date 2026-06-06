"""FastAPI 路由 (技术文档 B5)。承载原型 UI, 仅监听 127.0.0.1 (SEC-3)。

启动: uvicorn app.api:app --host 127.0.0.1 --port 8080
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pydantic import ValidationError

from .config import load_settings
from .marzban import MarzbanClient, MarzbanError
from .models import LineSpec
from .provisioning import ProvisioningService

app = FastAPI(title="RelayHub", version="0.1.0")

_settings = load_settings()
_service = ProvisioningService(MarzbanClient(_settings), _settings)

WEB_DIR = Path(__file__).resolve().parent.parent / "web"


def _err(code: int, message: str):
    return JSONResponse(status_code=code, content={"error": {"code": code, "message": message}})


@app.exception_handler(MarzbanError)
async def _marzban_err(_, exc: MarzbanError):
    return _err(502, str(exc))


@app.exception_handler(ValueError)
async def _value_err(_, exc: ValueError):
    return _err(400, str(exc))


@app.get("/")
def index():
    idx = WEB_DIR / "index.html"
    if not idx.exists():
        raise HTTPException(404, "index.html not found")
    return FileResponse(idx)


@app.post("/api/lines")
def create_line(spec: LineSpec):
    return _service.provision(spec)


@app.get("/api/lines")
def list_lines():
    return _service.list_customers()


@app.get("/api/stats")
def stats():
    customers = _service.list_customers()
    online = sum(1 for c in customers if c.status == "ok")
    used = round(sum(c.used_gb for c in customers), 1)
    expiring = sum(1 for c in customers if c.expire.endswith("天") and _days(c.expire) <= 7)
    return {
        "customers": len(customers),
        "online": online,
        "used_gb": used,
        "expiring": expiring,
    }


@app.post("/api/lines/{name}/rotate-sub")
def rotate_sub(name: str):
    return {"sub_url": _service.rotate_sub(name)}


@app.delete("/api/lines/{name}", status_code=204)
def delete_line(name: str):
    _service.remove(name)


def _days(expire: str) -> int:
    try:
        return int(expire.replace("天", "").strip())
    except ValueError:
        return 999
