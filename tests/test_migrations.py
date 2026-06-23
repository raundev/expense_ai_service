"""마이그레이션 정합성 테스트 — alembic 이 설치된 인터프리터(.venv/CI)에서만 실행.

시스템 python 에는 alembic 이 없어(로컬 `alembic/` 디렉터리가 namespace 로 잡힘) `importorskip` 으로
모듈 전체가 자동 skip 된다. CI 또는 alembic 보유 환경에서 실행 시 다음을 검증한다:
  1) base → head → base 가 깨끗이 적용/롤백되는지(깨진 마이그레이션·백필 적발)
  2) 모델 metadata 와 head 스키마가 완전 정합인지(autogenerate diff == 0 → '리비전 누락' 적발)

⚠️ 격리: env.py 가 `settings.sqlalchemy_database_uri` 로 URL 을 덮어쓰므로, dev DB 오염을 막기 위해
`settings.DATABASE_URL` 을 임시 파일 DB 로 monkeypatch 한 뒤 alembic 을 돌린다(downgrade base 가
실제 DB 를 드롭하는 사고 방지).
"""
from __future__ import annotations

import pytest

# 주의: 시스템 python 에서는 루트의 로컬 `alembic/` 디렉터리가 namespace 패키지로 잡혀 `import alembic`
# 자체는 성공한다(그러나 alembic.config 같은 실제 하위 모듈은 없다). 따라서 가용성 판정은 반드시
# 실제 패키지에만 있는 하위 모듈로 해야 정확히 skip 된다(`alembic` 으로 판정하면 collection 에러).
pytest.importorskip("alembic.config")

from alembic import command  # noqa: E402
from alembic.autogenerate import compare_metadata  # noqa: E402
from alembic.config import Config  # noqa: E402
from alembic.migration import MigrationContext  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.models import Base  # noqa: E402


@pytest.fixture
def scratch_db(tmp_path, monkeypatch):
    """임시 파일 SQLite 로 격리. settings 를 교체해 env.py 가 이 DB 를 보게 한다(dev DB 보호)."""
    url = f"sqlite:///{(tmp_path / 'migrations.db').as_posix()}"
    monkeypatch.setattr(settings, "DATABASE_URL", url)
    return url


def test_migrations_apply_and_downgrade(scratch_db):
    """base → head → base 전체 적용/롤백이 오류 없이 수행된다(깨진 마이그레이션/백필 적발)."""
    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")


def test_no_model_migration_drift(scratch_db):
    """head 까지 적용한 DB 스키마가 모델 metadata 와 완전 정합(autogenerate 차이 0).

    실패 = 모델을 바꿨는데 대응 마이그레이션을 안 썼다는 뜻 → 머지 전에 적발.
    """
    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")

    engine = create_engine(scratch_db)
    try:
        with engine.connect() as conn:
            ctx = MigrationContext.configure(
                conn,
                opts={"target_metadata": Base.metadata, "compare_type": True},
            )
            diffs = compare_metadata(ctx, Base.metadata)
    finally:
        engine.dispose()

    assert not diffs, (
        "모델과 마이그레이션 head 가 불일치합니다 — 누락/불일치 마이그레이션이 있습니다:\n"
        + "\n".join(str(d) for d in diffs)
    )
