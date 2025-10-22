import uvicorn
from fastapi import FastAPI
from app.routers.dm import router as dm_router
from app.core.config import settings

app = FastAPI(title="RAG DM Bot")

@app.get("/health")
def health():
    return {"status": "ok", "env": settings.app_env}

app.include_router(dm_router)

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=settings.app_port, reload=True)

@app.get("/")
def index():
    return {"ok": True, "service": "RAG DM Bot", "hint": "POST /simulate_dm"}
