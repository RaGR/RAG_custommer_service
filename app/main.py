"""FastAPI application entrypoint with security middleware and observability."""

from __future__ import annotations

import logging
import os
import time
import uuid
from typing import Any, Dict

import uvicorn
from fastapi import FastAPI, HTTPException, Request, Response

from app.core.config import settings
from app.logging.setup import hash_identity, setup_logging
from app.observability.metrics import inc_errors, inc_requests, render_metrics
from app.routers.admin_keys import router as admin_router
from app.routers.dm import router as dm_router
from app.security.audit import init_security_tables, security_db
from app.security.auth import Role, require_roles
from app.security.cors import configure_cors
from app.security.headers import BodySizeLimitMiddleware, SecurityHeadersMiddleware

setup_logging()
logger = logging.getLogger("app.main")
request_logger = logging.getLogger("app.request")

app = FastAPI(title="RAG DM Bot")
configure_cors(app)
app.add_middleware(BodySizeLimitMiddleware)
app.add_middleware(SecurityHeadersMiddleware)


@app.on_event("startup")
async def startup_event() -> None:
    init_security_tables()
    logger.info("startup_complete")


@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
    request.state.request_id = request_id  # type: ignore[attr-defined]
    inc_requests()
    start = time.time()
    status_code = 500
    response: Response | None = None
    try:
        response = await call_next(request)
        status_code = response.status_code
        response.headers.setdefault("X-Request-ID", request_id)
        return response
    except HTTPException as exc:
        status_code = exc.status_code
        inc_errors()
        raise
    except Exception:
        inc_errors()
        raise
    finally:
        latency_ms = int((time.time() - start) * 1000)
        ctx = getattr(request.state, "security_context", None)
        identity_hash = hash_identity(ctx.subject) if ctx else "anon"
        roles = ",".join(sorted(role.value for role in ctx.roles)) if ctx else ""
        rl_tokens = getattr(request.state, "rate_limit_tokens", None)
        log_payload: Dict[str, Any] = {
            "request_id": request_id,
            "path": request.url.path,
            "method": request.method,
            "status": status_code,
            "latency_ms": latency_ms,
            "identity": identity_hash,
        }
        if roles:
            log_payload["roles"] = roles
        if rl_tokens is not None:
            log_payload["rl_tokens"] = round(float(rl_tokens), 2)
        request_logger.info("http_request", extra=log_payload)


@app.get("/health")
async def health() -> Dict[str, Any]:
    ok_db = os.path.exists(settings.db_path)
    ok_idx = os.path.exists(os.path.join(settings.index_path, "index.faiss"))
    status = "ok" if (ok_db and ok_idx) else "degraded"
    return {
        "status": status,
        "env": settings.app_env,
        "llm_provider": settings.llm_provider,
        "llm_model": settings.llm_model,
        "db_exists": ok_db,
        "index_exists": ok_idx,
    }


@app.get("/metrics")
async def metrics(request: Request) -> Response:
    await require_roles(request, (Role.ADMIN, Role.ANALYST))
    text = render_metrics()
    return Response(content=text, media_type="text/plain; charset=utf-8")


@app.get("/security/selftest")
async def security_selftest(request: Request) -> Dict[str, Any]:
    await require_roles(request, (Role.ADMIN,))
    checks = _security_checks()
    overall = all(checks.values())
    return {"status": "ok" if overall else "degraded", "checks": checks}


def _security_checks() -> Dict[str, bool]:
    checks: Dict[str, bool] = {
        "security_headers_enabled": settings.security_headers_enabled,
        "body_limit_configured": settings.max_request_body_bytes > 0,
    }
    try:
        with security_db(readonly=True) as conn:
            rows = conn.execute(
                """SELECT name FROM sqlite_master WHERE type='table' AND name IN ('api_keys','audit','tenant_limits')"""
            ).fetchall()
        checks["security_tables"] = len(rows) == 3
    except Exception:
        checks["security_tables"] = False
    return checks


@app.get("/", response_class=Response)
async def index() -> Response:
    html = """
<!doctype html><html lang="fa" dir="rtl"><meta charset="utf-8"/>
<title>RAG DM Bot</title><meta name="viewport" content="width=device-width, initial-scale=1"/>
<style>body{font-family:sans-serif;max-width:820px;margin:24px auto;padding:0 12px}
.row{display:flex;gap:8px;margin:10px 0}input,button{font-size:16px}#log{border:1px solid #ddd;border-radius:8px;padding:12px;min-height:220px;background:#fafafa}
.u{color:#333}.b{color:#0a5}.err{color:#c22}</style>
<h2>RAG DM Bot</h2>
<p><small>LLM (OpenRouter) + پاسخ فارسی بر پایه دیتابیس — POST /simulate_dm</small></p>
<div class="row">
  <input id="text" placeholder="پرسش را بنویسید..." style="flex:1;padding:10px"/>
  <button id="send">ارسال</button>
</div>
<div id="log"></div>
<script>
const $=s=>document.querySelector(s);const log=(c,m)=>{const p=document.createElement('p');p.className=c;p.textContent=m;$("#log").appendChild(p);$("#log").scrollTop=$("#log").scrollHeight;}
async function send(){
  const t=$("#text").value.trim(); if(!t) return;
  log("u","شما: "+t); $("#text").value="";
  try{
    const r=await fetch("/simulate_dm",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({sender_id:"demo",message_id:String(Date.now()),text:t})});
    if(!r.ok){const e=await r.json();log("err","خطا: "+(e.detail?.detail||r.status));return;}
    const data=await r.json(); log("b","ربات: "+(data.reply||"—"));
  }catch(err){log("err","شبکه: "+err);}
}
$("#send").onclick=send; $("#text").addEventListener("keydown",(e)=>{if(e.key==="Enter") send();});
</script>
</html>"""
    return Response(content=html, media_type="text/html")


app.include_router(dm_router)
app.include_router(admin_router)


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=settings.app_port, reload=True)
