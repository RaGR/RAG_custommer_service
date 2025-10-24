# 💬 RAG DM Bot — FastAPI + SQLite + FAISS + OpenRouter LLM

A retrieval-augmented generation (RAG) micro-service that answers Persian (فارسی) user queries about beauty & cosmetics products.  
It combines a **local SQLite + FAISS** knowledge base with a **free OpenRouter LLM** (DeepSeek Chat v3.1) for fluent contextual replies.

---

## 🧠 Architecture Overview

> Hybrid RAG Stack  
> **FastAPI (backend)** → **SQLite + FTS5 + FAISS retrieval** → **Prompt builder (Farsi)** → **LLM API (OpenRouter)**  

Key components:

- **FastAPI** service with `/simulate_dm` and `/` (web chat UI)
- **SQLite** product database (`products` table) + FTS5 index  
- **FAISS** semantic vector index (`paraphrase-multilingual-MiniLM-L12-v2`)
- **Hybrid retrieval:** vector ∪ keyword merge
- **Prompt policy:** concise, Farsi-only, citation-based
- **LLM Client:** DeepSeek Chat v3.1 via OpenRouter API
- **Debug routes:** `/health`, `/debug/retrieve`, `/debug/prompt`

---

## 🗂️ Project Structure

```

rag-instabot/
├── app/
│   ├── core/config.py
│   ├── logging/setup.py
│   ├── observability/metrics.py
│   ├── providers/circuit.py
│   ├── retrieval/{fts.py,vector.py,normalize.py}
│   ├── prompting/builder.py
│   ├── llm/client.py
│   ├── routers/{dm.py,admin_keys.py}
│   ├── security/{auth.py,audit.py,cors.py,headers.py,hmac_sig.py,rate_limit.py}
│   └── main.py
├── db/app_data.sqlite
├── data/faiss_index/{index.faiss,meta.npy}
├── scripts/{setup_fts.sh,build_vectors.py,rebuild_db.sh}
├── .env.example
├── README.md
├── SECURITY_NOTES.md
└── images/
├── proj-structure.png
├── env-structure.png
├── db-snapshot.png
├── cpu_vectors_building.png
└── chat-tested.png

````

---

## ⚙️ Environment & Config

Create and activate a virtual env, then install all dependencies:

```bash
python3 -m venv .venvs
source .venvs/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
````

### `.env` configuration

Copy `.env.example` to `.env` and update credentials. Leave secrets (e.g. `LLM_API_KEY`, JWT keys, HMAC shared secret) blank in source control, then populate them locally or in production.

Key variables:

- `AUTH_MODE` — `api_key` (default) or `jwt`.
- `REQUIRE_API_KEY` / `API_KEY` — static fallback when persistent keys are unavailable.
- `JWT_*` — signing key material when JWT auth is enabled (set `JWT_SIGNING_KEY` for HS256 or `JWT_PUBLIC_KEY` for RS256).
- `HMAC_REQUIRED` / `HMAC_WINDOW_SEC` — enable signed requests with nonce replay defense.
- `CORS_ORIGINS`, `SECURITY_HEADERS_ENABLED`, `MAX_REQUEST_BODY_BYTES`, `DEBUG_ROUTES` — tighten surface area per environment (set `CORS_ORIGINS` as a JSON list, e.g. `["http://localhost:8000"]`).
- `RL_BUCKET_SIZE`, `RL_REFILL_PER_SEC`, `RL_IDENTITY_HEADER` — tune per-identity rate limiting.

LLM configuration (`LLM_API_BASE`, `LLM_API_KEY`, `LLM_MODEL`) remains required for inference.

---

## 🧩 Build & Index the Data

1. **FTS5 setup**

```bash
bash scripts/setup_fts.sh
```

2. **CPU-only vector embedding**

```bash
python scripts/build_vectors.py
```

(Uses Sentence-Transformers MiniLM model; runs entirely on CPU.)

3. Check outputs:

```
data/faiss_index/index.faiss
data/faiss_index/meta.npy
```

---

## 🚀 Run the Service

```bash
uvicorn app.main:app --reload --port 8000
```

Visit → [http://127.0.0.1:8000/](http://127.0.0.1:8000/)

---

## 🔐 Security & Privacy

- **Authentication:** Argon2-hashed API keys stored in SQLite (`api_keys` table) with role-based access control (CLIENT, ANALYST, ADMIN). When Argon2 is unavailable, the service falls back to PBKDF2 (warning emitted). Optional JWT bearer mode supports HS256/RS256 keys with issuer/audience validation.
- **Key management API:** ADMIN-only routes under `/admin/api-keys` let you create, enable, or disable credentials. New keys are returned once; store them securely.
- **Request integrity:** Enable `HMAC_REQUIRED=true` to force `X-API-Key` clients to sign requests with `X-Signature`, `X-Timestamp`, and `X-Nonce`. Nonces are tracked per key to prevent replay.
- **Rate limiting:** Token bucket per identity (`X-API-Key`, JWT `sub`, or IP) with configurable defaults and tenant overrides (`tenant_limits` table). Exceeds return `429` with `Retry-After`.
- **Security headers:** Middleware enforces CSP, `X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy`, and limits request bodies via `MAX_REQUEST_BODY_BYTES`.
- **Audit & observability:** Structured JSON logs hash identities, omit secrets, and include latency/role data. `/metrics` (ADMIN/ANALYST) exports Prometheus-style counters including `llm_calls_total` and `ratelimit_block_total`. `/security/selftest` verifies critical configuration without revealing secrets.

Security checklist:

1. **Environment** — Fill in `.env` with your real API credentials, JWT signing material, and desired `AUTH_MODE`/`HMAC_REQUIRED`/`REQUIRE_API_KEY` settings. Keep committed files blank.
2. **Database migrations** — Run `sqlite3 db/app_data.sqlite < migrations/security.sql` once to create the `api_keys`, `audit`, and `tenant_limits` tables.
3. **API keys** — Use `/admin/api-keys` (ADMIN credential required) to mint production keys. Disable or rotate keys via the same endpoint; every change is logged in the `audit` table.
4. **Signed requests** — When `HMAC_REQUIRED=true`, clients must send `X-Signature`, `X-Timestamp`, and `X-Nonce`. Nonces expire after `HMAC_WINDOW_SEC`.
5. **JWT mode** — Configure `AUTH_MODE=jwt`, populate `JWT_SIGNING_KEY` (HS256) or `JWT_PUBLIC_KEY` (RS256), and ensure tokens embed roles (`CLIENT`, `ANALYST`, `ADMIN`) plus `iss`/`aud`.
6. **Validation** — Run `python -m pytest -q` before deployment and call `/security/selftest` (ADMIN) at runtime to confirm the stack is secure.

> Tip: run `pytest -q` to execute the security regression suite covering auth, JWT, HMAC, rate limiting, headers, and privacy logging.

---

## 💻 Web Chat UI

Lightweight built-in HTML interface for testing:

- Type a Farsi query (e.g. `شامپو برای مو آسیب‌دیده`)
- The system performs hybrid retrieval + LLM response.

<p align="center">
  <img src="images/chat-tested.png" width="600"/>
</p>

---

## 🧱 Development Snapshots

| Stage                         | Preview                                                  |
| :---------------------------- | :------------------------------------------------------- |
| Project structure             | <img src="images/proj-structure.png" width="450"/>       |
| Environment variables         | <img src="images/env-structure.png" width="450"/>        |
| Database (120 rows)           | <img src="images/db-snapshot.png" width="450"/>          |
| CPU vector building           | <img src="images/cpu_vectors_building.png" width="450"/> |
| Chat test (working RAG + LLM) | <img src="images/chat-tested.png" width="450"/>          |

---

## ✅ Features Completed (Commit Stage)

- ✅ SQLite DB (120 Persian product rows)
- ✅ FTS5 search + auto triggers
- ✅ Vector index (FAISS + MiniLM CPU)
- ✅ Hybrid retrieval merge
- ✅ Prompt policy in Farsi
- ✅ OpenRouter LLM integration (DeepSeek v3.1)
- ✅ Browser chat UI + API debug routes
- ✅ Unicode-safe HTTP headers patch

---

## 🧭 Next Roadmap

- 🔹 Add semantic re-ranking (better result ordering)
- 🔹 Integrate session memory for multi-turn chat
- 🔹 Dockerize deployment
- 🔹 Metrics & tracing for API latency
- 🔹 Add unit tests and load testing suite

---

## 🪄 Quick Demo CLI

```bash
curl -X POST http://127.0.0.1:8000/simulate_dm \
  -H "Content-Type: application/json" \
  -d '{"sender_id":"u1","message_id":"m1","text":"کرم ضدآفتاب مناسب پوست چرب"}'
```

Response:

```json
{
  "reply": "کرم ضدآفتاب مناسب پوست چرب از برند اوردینری یا لورآل در دیتابیس موجود است. SPF50 و بافت سبک دارد."
}
```
