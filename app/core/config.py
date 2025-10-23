from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # App
    app_env: str = "dev"
    app_port: int = 8000
    log_level: str = "INFO"

    # DB & Retrieval
    db_path: str = "/home/ragr/Desktop/rag-instabot/db/app_data.sqlite"
    index_path: str = "/home/ragr/Desktop/rag-instabot/data/faiss_index"
    embed_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

    # Retrieval thresholds
    min_vector_score: float = 0.30      # cosine/IP score threshold
    max_ctx_items: int = 4              # top-k to send to LLM
    max_desc_chars: int = 220           # truncate description per item

    # LLM Provider chain (failover)
    llm_provider: str = "openrouter"    # openrouter|huggingface|none
    llm_api_base: str = ""              # set by env
    llm_api_key: str = ""               # secret
    llm_model: str = ""
    hf_api_base: str = ""               # optional second provider (HF)
    hf_api_key: str = ""                # optional
    hf_model: str = ""                  # optional

    # Security
    require_api_key: bool = False
    api_key: str = ""                   # if require_api_key=True, must be set

    # Rate-limiting (token bucket)
    rl_bucket_size: int = 60            # tokens per window
    rl_refill_per_sec: float = 1.0      # refill rate
    rl_identity_header: str = "X-API-Key"  # or "ip"

    # HTTP timeouts/retries
    llm_timeout_s: int = 60
    llm_retries: int = 2                # per provider

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
