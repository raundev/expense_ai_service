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
    # Chat LLM 호출 HTTP 타임아웃(초)의 명시적 override. 설정하면 자동 판정을 무시하고
    # 이 값을 그대로 쓴다. 미설정(None)이면 OPENAI_API_BASE 기준으로 자동 결정한다
    #   (RunPod GPU 프록시는 큐 대기로 느려서 길게, 그 외 클라우드는 짧게 — llm_http_timeout 참고).
    LLM_HTTP_TIMEOUT: float | None = None
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    # 임베딩 공급자: "openai"(OpenAI 호환 API) 또는 "fastembed"(로컬 ONNX, API/네트워크 불필요).
    # fastembed 사용 시 EMBEDDING_MODEL 은 FastEmbed 지원 모델명으로 설정한다
    #   (예: sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 — 한국어 지원, 384차원).
    EMBEDDING_PROVIDER: str = "openai"

    # --- CORS ---
    # 콤마(,)로 구분된 오리진 목록. "*"은 전체 허용.
    CORS_ORIGINS: str = "*"

    # --- Multi-tenant 등록 검증 ---
    # 미등록 (company_id, workplace_id) 의 도메인 API 접근 차단 모드(점진 롤아웃).
    #   "off"     : 검증 안 함(기존 동작). 기본값 — 백필/모니터링 전 안전 기본값.
    #   "log"     : 미등록이어도 통과하되 경고 로그만 남김(화이트리스트 모니터링 단계).
    #   "enforce" : 미등록/정지(SUSPENDED) 테넌트는 403 으로 차단.
    TENANT_ENFORCEMENT_MODE: str = "off"

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

    @property
    def is_runpod_llm(self) -> bool:
        """LLM endpoint(OPENAI_API_BASE)가 사내 RunPod GPU 프록시인지."""
        return "runpod.ai" in self.OPENAI_API_BASE.lower()

    @property
    def llm_http_timeout(self) -> float:
        """Chat LLM 호출 HTTP 타임아웃(초).

        우선순위:
          1) LLM_HTTP_TIMEOUT 이 명시되면 그 값을 그대로 사용한다(운영자 강제 지정).
          2) 아니면 endpoint 기준으로 자동 판정한다 — RunPod GPU 프록시는 콜드스타트·
             큐 대기로 응답이 최대 ~2분 30초까지 걸려 150초를, 그 외 클라우드(GPT 등)는 60초.

        이전엔 모델명 접두사(`LLM_MODEL.startswith("Qwen")`)로 판정했으나, 같은 RunPod
        endpoint 라도 모델명이 바뀌면(소문자 qwen·다른 모델 등) 타임아웃이 조용히 60초로
        떨어지는 함정이 있어 endpoint 기준으로 바꿨다. (임베딩 호출에는 적용하지 않는다.)
        """
        if self.LLM_HTTP_TIMEOUT is not None:
            return self.LLM_HTTP_TIMEOUT
        return 150.0 if self.is_runpod_llm else 60.0


@lru_cache
def get_settings() -> Settings:
    """설정 싱글톤. lru_cache 로 프로세스 당 1회만 인스턴스화."""
    return Settings()


settings = get_settings()
