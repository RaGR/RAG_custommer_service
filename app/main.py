import uvicorn
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from app.routers.dm import router as dm_router
from app.core.config import settings

app = FastAPI(title="RAG DM Bot")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # narrow in prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health():
    return {
        "status": "ok",
        "env": settings.app_env,
        "llm_provider": settings.llm_provider,
        "llm_model": settings.llm_model,
        "llm_api_base": settings.llm_api_base[:30] + "..." if settings.llm_api_base else "",
    }



# Simple chat page at "/"
@app.get("/", response_class=Response)
def index():
    html = """
<!doctype html>
<html lang="fa" dir="rtl">
<head>
<meta charset="utf-8"/>
<title>RAG DM Bot</title>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<style>
  body{font-family:sans-serif;max-width:720px;margin:24px auto;padding:0 12px;}
  .row{display:flex;gap:8px;margin:8px 0;}
  input,button,textarea{font-size:16px}
  #log{border:1px solid #ddd;border-radius:8px;padding:12px;min-height:200px;background:#fafafa}
  .u{color:#222;margin:6px 0;}
  .b{color:#0a5;margin:6px 0;}
  small{color:#888}
</style>
</head>
<body>
<h2>RAG DM Bot</h2>
<p><small>POST /simulate_dm → پاسخ فارسی بر پایه دیتابیس + LLM (OpenRouter)</small></p>
<div class="row">
  <input id="text" placeholder="پرسش خود را بنویسید..." style="flex:1;padding:10px"/>
  <button id="send">ارسال</button>
</div>
<div id="log"></div>
<script>
const $ = sel => document.querySelector(sel);
const log = (cls, msg) => {
  const p = document.createElement('p');
  p.className = cls;
  p.textContent = msg;
  $("#log").appendChild(p);
  $("#log").scrollTop = $("#log").scrollHeight;
};
async function send(){
  const t = $("#text").value.trim();
  if(!t) return;
  log("u","شما: " + t);
  $("#text").value = "";
  try{
    const r = await fetch("/simulate_dm", {
      method: "POST",
      headers: {"Content-Type":"application/json"},
      body: JSON.stringify({sender_id:"demo", message_id: String(Date.now()), text: t})
    });
    if(!r.ok){
      const e = await r.json();
      log("b","خطا: " + (e.detail || r.status));
      return;
    }
    const data = await r.json();
    log("b","ربات: " + (data.reply || "—"));
  }catch(err){
    log("b","خطای شبکه: " + err);
  }
}
$("#send").onclick = send;
$("#text").addEventListener("keydown", (e)=>{ if(e.key==="Enter") send(); });
</script>
</body>
</html>
"""
    return Response(content=html, media_type="text/html")

app.include_router(dm_router)

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=settings.app_port, reload=True)