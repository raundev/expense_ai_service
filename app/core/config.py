from functools import lru_cache

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

# .env 의 모든 키를 os.environ 으로 전파한다.
# 목적: 외부 라이브러리(httpx/openai/urllib3 등)가 우리 Settings 객체를 거치지 않고
# os.environ 에서 직접 읽는 환경변수 -- 특히 SSL_CERT_FILE, REQUESTS_CA_BUNDLE --
# 를 .env 한 곳에서 관리할 수 있게 한다.
# override=True: .env 를 단일 진실 공급원(source of truth)으로 강제한다. 잘못 설정된
# 시스템 환경변수(예: 존재하지 않는 CA 경로를 가리키는 SSL_CERT_FILE)가 .env 의 올바른
# 값을 가리는 드리프트를 방지한다. (11→12단계에서 실제로 LLM 호출이 깨졌던 원인)
load_dotenv(override=True)


class Settings(BaseSettings):
    """애플리케이션 전역 설정.

    `.env` 파일 또는 환경 변수에서 값을 읽어온다.
    """

    # --- Application ---
    APP_NAME: str = "Bizplay Expense AI Service"
    ENVIRONMENT: str = "local"
    DEBUG: bool = True
    API_PREFIX: str = "/api"

    # --- Relational Database ---
    # 로컬 개발 기본값(SQLite). 운영(PostgreSQL)에서는 DATABASE_URL 을 사용한다.
    DB_URL: str = "sqlite:///./expense_ai.db"
    # 운영용 표준 변수. 설정되면 DB_URL 보다 우선한다(SQLAlchemy 가 스킴으로 드라이버 자동 선택).
    #   예) postgresql+psycopg2://user:pass@host:5432/expense_ai
    DATABASE_URL: str | None = None

    # --- Vector Database (Qdrant) ---
    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_API_KEY: str | None = None

    # --- LLM / Embeddings ---
    OPENAI_API_KEY: str | None = None
    # 사내 GPU(RunPod) 프록시. OpenAI 호환 endpoint 를 그대로 사용한다.
    OPENAI_API_BASE: str = "https://api.runpod.ai/v2/v7fykeg2rhwgse/openai/v1"
    LLM_MODEL: str = "gpt-4o-mini"
    EMBEDDING_MODEL: str = "text-embedding-3-small"

    # --- CORS ---
    # 콤마(,)로 구분된 오리진 목록. "*"은 전체 허용.
    CORS_ORIGINS: str = "*"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def sqlalchemy_database_uri(self) -> str:
        """실제 사용할 DB 연결 URI. DATABASE_URL(운영) 우선, 없으면 DB_URL(로컬).

        SQLAlchemy 는 URI 스킴(`postgresql+psycopg2://` / `sqlite://`)으로 드라이버를
        자동 선택하므로, 운영 PostgreSQL 전환은 DATABASE_URL 지정만으로 충분하다.
        """
        return self.DATABASE_URL or self.DB_URL

    @property
    def is_sqlite(self) -> bool:
        return self.sqlalchemy_database_uri.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    """설정 싱글톤. lru_cache 로 프로세스 당 1회만 인스턴스화."""
    return Settings()


settings = get_settings()
