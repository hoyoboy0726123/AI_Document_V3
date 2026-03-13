from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    PROJECT_NAME: str = "AI Document V3"
    PROJECT_VERSION: str = "1.0.0"

    DATABASE_URL: str = "sqlite:///./doc_management.db"

    # Security: SECRET_KEY must be provided via environment variable
    SECRET_KEY: str = Field(
        ...,
        min_length=32,
        description="JWT secret key - MUST be set in .env file"
    )
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30  # 30 minutes (recommended: 15-60)

    # Refresh Token Configuration
    # Allows users to stay logged in for extended periods without re-authentication
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7  # 7 days (recommended: 7-30)

    DEFAULT_ADMIN_USERNAME: str = "admin"
    DEFAULT_ADMIN_PASSWORD: str = "Admin@123"
    DEFAULT_ADMIN_EMAIL: str = "admin@example.com"

    # Ollama 推理服務
    OLLAMA_BASE_URL: str = "http://127.0.0.1:11434"
    OLLAMA_LLM_MODEL: str = "llama3.2"
    OLLAMA_VISION_MODEL: str = "llava"
    OLLAMA_EMBED_MODEL: str = "all-minilm"
    OLLAMA_KEEP_ALIVE: str = "5m"
    OLLAMA_TIMEOUT: int = 120  # seconds
    # Optional generation controls (help avoid truncated answers)
    # -1 for unlimited tokens (Ollama default); increase context for long PDFs
    OLLAMA_NUM_PREDICT: int | None = -1
    OLLAMA_NUM_CTX: int | None = 8192
    # Sampling and repetition controls (optional; set in .env if needed)
    OLLAMA_TEMPERATURE: float | None = None
    OLLAMA_TOP_P: float | None = None
    OLLAMA_TOP_K: int | None = None
    OLLAMA_REPEAT_PENALTY: float | None = None
    OLLAMA_MIROSTAT: int | None = None  # 0/1/2
    OLLAMA_MIROSTAT_TAU: float | None = None
    OLLAMA_MIROSTAT_ETA: float | None = None
    # Optional comma-separated stop tokens, e.g.: "<|im_start|>,<|im_end|>,</s>"
    OLLAMA_STOP: str | None = None

    FILE_STORAGE_DIR: str = "./storage"
    PDF_STORAGE_DIR: str = "./storage/documents"
    PDF_TEMP_DIR: str = "./storage/tmp"
    FAISS_INDEX_PATH: str = "./storage/faiss_index.bin"

    # RAG 相關設定
    MIN_SIMILARITY_SCORE: float = 0.3  # 最低相似度分數閾值
    DEFAULT_TOP_K: int = 5  # 預設返回的來源數量
    SEARCH_MULTIPLIER: int = 10  # 搜尋倍數（實際搜尋 top_k * multiplier）



    class Config:
        env_file = ".env"


settings = Settings()
