# RAG DM Bot — FastAPI + SQLite + FAISS + OpenRouter (DeepSeek)

A **Retrieval-Augmented Generation (RAG)** service that answers **cosmetics & beauty** questions in Persian.  
It combines **semantic search** (FAISS) + **keyword search** (SQLite FTS5) with **DeepSeek LLM via OpenRouter** to produce grounded, concise answers.

<p align="center">
  <img src="./images/chat-tested.png" width="720" alt="Web chat test screenshot"/>
</p>

---

## 1) Project Overview

- **Goal:** a conversational AI that answers beauty/product questions using your curated SQLite data and an LLM, with **RAG** ensuring answers are grounded in real entries.
- **Stack:** **FastAPI** (API), **SQLite + FTS5** (data + keyword search), **FAISS** (vector search), **OpenRouter LLM (DeepSeek)**, hybrid retrieval, redaction, rate-limit, basic auth.
- **How it works:** user query → normalize → hybrid retrieval (FAISS ∪ FTS5) → prompt (context-aware, Farsi policy) → **DeepSeek** via OpenRouter → reply.

<p align="center">
  <img src="./images/proj-structure.png" width="720" alt="Project structure overview"/>
</p>

---

## 2) Features

- **Hybrid Retrieval**
  - **FAISS** for semantic retrieval over product `name + description`.
  - **FTS5** for fast keyword matching (BM25).
- **LLM Integration**
  - **DeepSeek** (OpenRouter) with ASCII-safe headers and controlled prompts.
- **API Endpoints**
  - `POST /simulate_dm` — main chat endpoint (returns `{"reply": "..."}`).
  - `GET /health` — readiness (env, DB/index presence).
  - `GET /metrics` — minimal counters (requests, errors, fallback).
  - `POST /feedback` — collect ratings/notes per message.
- **Security**
  - API Key auth (optional), rate-limit (token bucket), safe logging, redaction/allow-list to LLM.
- **Ops / Debug**
  - Optional debug routes (`/debug/retrieve`, `/debug/prompt`) to inspect retrieval/prompt.

---

## 3) System Architecture

- **FastAPI Backend**: validates input, orchestrates retrieval, builds prompt, calls LLM.
- **SQLite DB + FTS5**: products storage and lexical search.
- **FAISS Index**: normalized embeddings for semantic search.
- **LLM (OpenRouter DeepSeek)**: generates grounded Farsi responses.

<p align="center">
  <img src="./images/RAG Bot System_ Use Case Diagram.png" width="900" alt="Use Case Diagram"/>
</p>

<p align="center">
  <img src="./images/Simulazione RAG DM_ Diagramma Sequenziale.png" width="900" alt="Sequence Diagram"/>
</p>

---

## 4) Installation & Setup

### 4.1. Clone & Python venv
```bash
git clone <REPO_URL>
cd <project_directory>
python3 -m venv .venvs
source .venvs/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
````

### 4.2. Environment variables

Create `.env` (see example below).
You can also verify visually:

<p align="center">
  <img src="./images/updated-envirment-var.png" width="720" alt="Updated environment variables"/>
</p>

**Example `.env`**

```env
APP_ENV=prod
APP_PORT=8000
LOG_LEVEL=INFO

# Database / Index
DB_PATH=rag-instabot/db/app_data.sqlite
INDEX_PATH=rag-instabot/data/faiss_index
EMBED_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2

# Retrieval thresholds
MIN_VECTOR_SCORE=0.30
MAX_CTX_ITEMS=4
MAX_DESC_CHARS=220

# Security
REQUIRE_API_KEY=true
API_KEY=change-me

# Rate limit
RL_BUCKET_SIZE=60
RL_REFILL_PER_SEC=1.0
RL_IDENTITY_HEADER=X-API-Key

# LLM (OpenRouter - DeepSeek)
LLM_PROVIDER=openrouter
LLM_API_BASE=https://openrouter.ai/api/v1
LLM_MODEL=deepseek/deepseek-chat-v3.1:free
LLM_API_KEY=sk-xxxxxxxx

# (Optional) OpenRouter analytics headers - ASCII only
OR_HTTP_REFERER=http://localhost:8000/
OR_X_TITLE=RAG-Instabot
```

**OpenRouter key creation**

<p align="center">
  <img src="./images/openrouter-api-key.png" width="720" alt="OpenRouter API Key setup"/>
</p>

### How to setup open router api key
- Proceed to Official OpenRouter web site: [openrouter.ai](https://openrouter.ai/)
- Make an account and login
- Navigate to key / APIkey section and generate a key (note: you will have one key and can access all models via that same key)
- Activate the key in your open router panel before run(note: some times will get disabled by default)




### 4.3. Prepare DB & Index

1. **FTS5** (if not already):

```bash
bash scripts/setup_fts.sh
```

2. **FAISS vectors** (CPU-only safe):

```bash
python scripts/build_vectors.py
```

<p align="center">
  <img src="./images/db-snapshot.png" width="720" alt="DB snapshot"/>
</p>

<p align="center">
  <img src="./images/cpu_vectors_building.png" width="720" alt="CPU vector building"/>
</p>

### 4.4. Run API

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Open **[http://127.0.0.1:8000/](http://127.0.0.1:8000/)** (built-in web chat).

---

## 5) Environment Configuration (What each key does)

* `APP_ENV`, `APP_PORT`, `LOG_LEVEL` — app mode/port/logging.
* `DB_PATH`, `INDEX_PATH`, `EMBED_MODEL` — data sources & embeddings.
* `MIN_VECTOR_SCORE`, `MAX_CTX_ITEMS`, `MAX_DESC_CHARS` — quality/safety knobs for retrieval & prompt size.
* `REQUIRE_API_KEY`, `API_KEY` — access control gates.
* `RL_*` — token bucket rate limit parameters.
* `LLM_*` — provider base URL, model name, API key.
* `OR_*` — optional OpenRouter analytics headers (ASCII-only).

---

## 6) API Endpoints

### 6.1. `POST /simulate_dm`

**Request**

```json
{
  "sender_id": "u1",
  "message_id": "m1",
  "text": "سرم ویتامین C برای پوست حساس"
}
```

**Response**

```json
{
  "reply": "..."
}
```

### 6.2. `GET /health`

Checks env + DB/index presence.

```json
{
  "status": "ok",
  "env": "prod",
  "llm_provider": "openrouter",
  "llm_model": "deepseek/deepseek-chat-v3.1:free",
  "db_exists": true,
  "index_exists": true
}
```

### 6.3. `GET /metrics`

Text counters:

```
requests_total 10
fallback_total 0
errors_total 0
```

### 6.4. `POST /feedback`

```json
{
  "message_id": "m1",
  "rating": "good",
  "note": "Helpful"
}
```

```json
{"ok": true}
```

---

## 7) Data Flow

1. **Input** → normalize (Persian variants, digits).
2. **Retrieval** → FAISS (semantic) + FTS5 (keyword) → merge + threshold → top-K context.
3. **Prompt** → build Farsi, anti-hallucination policy, redaction/allow-list (name/description/price only).
4. **LLM** → OpenRouter DeepSeek with ASCII-safe headers.
5. **Response** → concise Farsi answer; if no evidence → “اطلاعات کافی در دیتابیس موجود نیست.”

<p align="center">
  <img src="./images/curl-test.png" width="720" alt="curl test for API"/>
</p>


---

## 8) Testing

* **Manual**

  * Web UI: `http://127.0.0.1:8000/`
  * curl:

    ```bash
    curl -X POST http://127.0.0.1:8000/simulate_dm \
      -H "Content-Type: application/json" -H "X-API-Key: change-me" \
      -d '{"sender_id":"u1","message_id":"m1","text":"کرم ضدآفتاب مناسب پوست چرب"}'
    ```


* **Edge cases** (visual reference)

  <p align="center">
    <img src="./images/3-examples-edge-case.png" width="720" alt="Edge case examples"/>
  </p>
* **Debug (optional)**

  * `/debug/retrieve?q=...` — inspect FAISS/FTS hits.
  * `/debug/prompt?q=...` — preview final prompt (trimmed).

---

## 9) Security & Privacy

* **Auth**: optional API key (`REQUIRE_API_KEY=true`).
* **Rate-limit**: in-process token bucket (per IP or `X-API-Key`).
* **Redaction/Allow-list**: only `name/description/price` go to LLM; strip URLs/markup; truncate lengths.
* **Headers**: enforce **ASCII-only** for OpenRouter; avoid Unicode header issues.
* **Logging**: **no secrets or full prompts** in logs; only minimal structured fields (latency, hits, provider).
* **Failover**: retries + provider chain (OpenRouter → HF) → safe fallback string.


---


## 10) License

This project is licensed under the **Apache License 2.0**.

You may not use the files in this repository except in compliance with the License.
You may obtain a copy of the License at:

- `LICENSE` (included in this repository)
- https://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on an **"AS IS" BASIS**, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the specific language governing permissions and limitations under the License.

---

## Further Reading

Please read the full **technical documentation** for architecture details, security policies, and operational guidance:

- `./Technical-Documentation.pdf`
