from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

# --- Engine ---
# pool_pre_ping: 끊긴 커넥션을 사용 전에 감지하여 재연결.
engine = create_engine(
    settings.DB_URL,
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
