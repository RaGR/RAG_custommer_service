from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_env: str = "dev"
    app_port: int = 8000
    rate_limit_per_min: int = 60
    log_level: str = "INFO"

    llm_provider: str = "none"      # none|openrouter|huggingface
    llm_api_base: str = ""
    llm_api_key: str = ""
    llm_model: str = ""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="", extra="ignore")

settings = Settings()
