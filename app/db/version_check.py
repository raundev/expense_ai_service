"""DB 스키마 버전 점검 — **alembic 의존 없이** 동작(앱 런타임 인터프리터에 alembic 이 없어도 됨).

`alembic/versions/*.py` 를 파싱해 head 리비전(어떤 down_revision 으로도 참조되지 않는 revision)을
구하고, DB 의 `alembic_version` 과 비교한다. 불일치 시 enforce 면 부팅 실패(RuntimeError),
아니면 경고만 남긴다.

목적: '마이그레이션 미적용' 상태를 요청 시점의 모호한 500 대신 **기동 시점의 명확한 메시지**로 노출.
(운영 컨테이너는 기동 전 `alembic upgrade head` 를 수행하므로 항상 통과한다 — Dockerfile 참고.)

왜 alembic 을 import 하지 않나: 앱은 시스템 python(=alembic 미설치)으로도 구동되며, 로컬 루트의
`alembic/` 디렉터리가 namespace 로 잡혀 `import alembic.*` 가 깨질 수 있다. 순수 파일 파싱이 안전하다.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

# app/db/version_check.py → 프로젝트 루트 = parents[2]
_VERSIONS_DIR = Path(__file__).resolve().parents[2] / "alembic" / "versions"

# `revision: str = '...'` / `revision = "..."` 모두 매칭. 타입 어노테이션(: ...)은 '=' 를 포함하지 않으므로 안전.
_REVISION_RE = re.compile(r"^revision(?:\s*:[^=]+)?\s*=\s*['\"]([^'\"]+)['\"]", re.MULTILINE)
_DOWN_STR_RE = re.compile(r"^down_revision(?:\s*:[^=]+)?\s*=\s*['\"]([^'\"]+)['\"]", re.MULTILINE)
# merge 리비전의 튜플형: down_revision = ('a', 'b')
_DOWN_TUPLE_RE = re.compile(r"^down_revision(?:\s*:[^=]+)?\s*=\s*\(([^)]*)\)", re.MULTILINE)
_QUOTED_RE = re.compile(r"['\"]([^'\"]+)['\"]")


def find_code_head() -> str | None:
    """마이그레이션 파일들에서 단일 head 리비전을 찾는다.

    head 가 0개이거나 2개 이상(멀티헤드)이면 None 을 반환한다(거짓 경보 방지를 위해 점검을 건너뛰게 함).
    """
    if not _VERSIONS_DIR.is_dir():
        return None
    revisions: set[str] = set()
    down_refs: set[str] = set()
    for path in _VERSIONS_DIR.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        rev_match = _REVISION_RE.search(source)
        if not rev_match:
            continue
        revisions.add(rev_match.group(1))
        down_refs.update(_DOWN_STR_RE.findall(source))
        for tuple_body in _DOWN_TUPLE_RE.findall(source):
            down_refs.update(_QUOTED_RE.findall(tuple_body))
    heads = revisions - down_refs
    return next(iter(heads)) if len(heads) == 1 else None


def read_db_revision(engine: Engine) -> str | None:
    """DB 의 `alembic_version.version_num`. 테이블 부재(미마이그레이션)/조회 실패 시 None."""
    try:
        with engine.connect() as conn:
            return conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    except Exception:  # noqa: BLE001 — alembic_version 부재 등은 '미적용'으로 간주
        return None


def check_db_at_head(engine: Engine, *, enforce: bool) -> None:
    """DB 리비전이 코드 head 와 일치하는지 점검.

    - 일치: info 로그 후 통과.
    - 불일치: enforce 면 RuntimeError(부팅 중단), 아니면 warning(로컬 개발 편의).
    - head 를 단일 확정할 수 없으면(멀티헤드/파싱 실패) 조용히 건너뛴다.
    """
    code_head = find_code_head()
    if code_head is None:
        logger.debug("DB 버전 점검 건너뜀: 코드 head 를 단일하게 확정할 수 없음")
        return
    db_rev = read_db_revision(engine)
    if db_rev == code_head:
        logger.info("DB 스키마 최신 확인: revision=%s", db_rev)
        return
    message = (
        f"DB 스키마가 최신이 아닙니다 (DB={db_rev}, code head={code_head}). "
        f"`alembic upgrade head` 를 실행하세요(로컬: .venv\\Scripts\\alembic.exe)."
    )
    if enforce:
        raise RuntimeError(message)
    logger.warning(message)
