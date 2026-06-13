from pathlib import Path

from pydantic import Field, field_validator
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
    OLLAMA_LLM_MODEL: str = "qwen3:8b"
    OLLAMA_VISION_MODEL: str = "qwen2.5vl:7b"
    OLLAMA_EMBED_MODEL: str = "quentinz/bge-large-zh-v1.5:latest"
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

    # PDF 多頁 VL 分析上限（受模型 context window 限制）
    MAX_PDF_ANALYSIS_PAGES: int = 10

    # LLM provider 抽象：可獨立切換 LLM 與 embedding 的後端
    LLM_PROVIDER: str = "ollama"               # ollama | gemini
    LLM_MODEL: str | None = None               # 覆寫 OLLAMA_LLM_MODEL；空則用 provider 預設
    EMBEDDING_PROVIDER: str = "ollama"
    EMBEDDING_MODEL: str | None = None
    # VL 視覺模型(目前只支援 ollama;Gemini vision 走 LLM_PROVIDER 那條)
    VISION_PROVIDER: str = "ollama"
    VISION_MODEL: str | None = None            # 覆寫 OLLAMA_VISION_MODEL;留空則沿用

    # Gemini / Google AI Studio
    GEMINI_API_KEY: str | None = None
    GEMINI_LLM_MODEL: str = "gemini-2.5-flash"
    GEMINI_EMBED_MODEL: str = "text-embedding-004"

    # KG 抽取
    KG_AUTO_EXTRACT: bool = True               # 文件 ingest 完成後自動跑 KG 抽取
    KG_MIN_CONFIDENCE: float = 0.3             # 低於此值的 LLM relation 不寫入

    # RAG「小找大」：命中小塊後，連同同文件前後 N 塊一起餵給 LLM，
    # 避免句子被切塊邊界截斷（搜尋精度用小塊、上下文完整性用擴展後的大塊）。
    RAG_NEIGHBOR_RADIUS: int = 1               # 0 = 關閉擴展；1 = 帶 k-1/k+1
    RAG_EXPAND_MAX_CHARS: int = 2000           # 單一來源擴展後的字數上限
    # 所有來源餵入 LLM 的總字數「上限」(實際還會依 num_ctx 動態夾限，見 effective_rag_budget)。
    # input+output 共用同一 context window，須留生成空間。8192 視窗下 6000 字安全。
    RAG_CONTEXT_BUDGET_CHARS: int = 6000
    RAG_OUTPUT_RESERVE_CHARS: int = 1800       # 預留給「生成」的視窗額度（夾限時扣除）



    @field_validator("OLLAMA_KEEP_ALIVE", mode="before")
    @classmethod
    def _normalize_keep_alive(cls, v):
        # Ollama daemon 接受純數字（"-1" = 永久），但 Ollama API 要求帶單位（如 "5m"）。
        # 系統環境常為 daemon 設 OLLAMA_KEEP_ALIVE=-1，會被 pydantic-settings 一起讀進來。
        # 這裡若拿到純數字 / 負數，補上秒單位避免送 API 時 400。
        if v is None:
            return v
        s = str(v).strip()
        if not s:
            return s
        # 已帶單位（s/m/h）就直接用
        if s[-1].lower() in {"s", "m", "h"}:
            return s
        # 純數字（含負號）→ 補 's'
        try:
            int(s)
            return f"{s}s"
        except ValueError:
            return s

    class Config:
        env_file = ".env"


settings = Settings()
