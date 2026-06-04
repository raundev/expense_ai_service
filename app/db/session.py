from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

# --- Engine ---
# DB URI 는 settings.sqlalchemy_database_uri 가 DATABASE_URL(운영 PostgreSQL) 우선,
# 없으면 DB_URL(로컬 SQLite) 로 해석한다. 드라이버는 URI 스킴으로 자동 선택된다.
_db_uri = settings.sqlalchemy_database_uri

# SQLite 는 멀티스레드(FastAPI 스레드풀)에서 동일 커넥션 공유 시 막히므로
# check_same_thread=False 가 필요하다. PostgreSQL 등에는 적용하지 않는다.
_connect_args: dict = {"check_same_thread": False} if settings.is_sqlite else {}

# pool_pre_ping: 끊긴 커넥션을 사용 전에 감지하여 재연결(특히 PostgreSQL 운영 환경에 유용).
engine = create_engine(
    _db_uri,
    connect_args=_connect_args,
    pool_pre_ping=True,
    echo=settings.DEBUG,
    future=True,
)

# --- Session Factory ---
SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
    class_=Session,
)


def get_db() -> Generator[Session, None, None]:
    """FastAPI 의존성 주입용 DB 세션 제너레이터.

    요청 단위로 세션을 열고, 응답 후 반드시 닫는다.

    사용 예:
        @router.get("/items")
        def list_items(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
