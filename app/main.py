import uvicorn, time, sqlite3, os
from fastapi import FastAPI, Response, Request
from fastapi.middleware.cors import CORSMiddleware
from app.routers.dm import router as dm_router
from app.core.config import settings

app = FastAPI(title="RAG DM Bot")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # narrow in prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health():
    # light checks
    ok_db = os.path.exists(settings.db_path)
    ok_idx = os.path.exists(os.path.join(settings.index_path, "index.faiss"))
    return {
        "status": "ok" if (ok_db and ok_idx) else "degraded",
        "env": settings.app_env,
        "llm_provider": settings.llm_provider,
        "llm_model": settings.llm_model,
        "db_exists": ok_db,
        "index_exists": ok_idx
    }

# very simple in-process counters (demo)
_METRICS = {
    "requests_total": 0,
    "fallback_total": 0,
    "errors_total": 0,
}

@app.middleware("http")
async def metrics_mw(request: Request, call_next):
    _METRICS["requests_total"] += 1
    t0 = time.time()
    try:
        resp = await call_next(request)
        return resp
    except Exception:
        _METRICS["errors_total"] += 1
        raise
    finally:
        _ = int((time.time() - t0) * 1000)

@app.get("/metrics")
def metrics():
    text = "\n".join([f"{k} {v}" for k, v in _METRICS.items()]) + "\n"
    return Response(content=text, media_type="text/plain")

@app.get("/", response_class=Response)
def index():
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
    if(!r.ok){const e=await r.json();log("err","خطا: "+(e.detail||r.status));return;}
    const data=await r.json(); log("b","ربات: "+(data.reply||"—"));
  }catch(err){log("err","شبکه: "+err);}
}
$("#send").onclick=send; $("#text").addEventListener("keydown",(e)=>{if(e.key==="Enter") send();});
</script>
</html>"""
    return Response(content=html, media_type="text/html")

app.include_router(dm_router)

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=settings.app_port, reload=True)
