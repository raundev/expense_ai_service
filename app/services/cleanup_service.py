"""Soft Delete 물리 정리 워커 (설계 §4.3, Critical Design Rule #4).

`status`/`embedding_status == "DELETING"` 인 봇·문서를 안전하게(멱등) 물리 삭제한다.

처리 순서
  - 문서: Qdrant 벡터(metadata.doc_id 필터) → 디스크 파일(file_path) → RDB Document 행
  - 봇  : 소속 문서(owner_id=bot.id)가 모두 사라진 뒤 RDB Bot 행
          (ORM cascade 로 sessions/messages/recommended 동반 삭제)

엣지 케이스 방어 (Qdrant 네트워크 실패 등):
  각 문서/봇은 **독립 트랜잭션**으로 처리한다. 벡터 또는 파일 삭제 단계에서 예외가 나면
  `db.rollback()` 으로 RDB 행 삭제를 되돌리고 DELETING 상태로 남겨 **다음 주기에 재시도**한다.
  → 부분 삭제(행은 지웠는데 벡터가 남는 '좀비 벡터')를 원천 차단한다. 벡터/파일 삭제는 멱등
  이라(없으면 no-op) 재시도해도 안전하며, 한 항목 실패가 다른 항목 처리를 막지 않는다.
"""
from __future__ import annotations

import logging
import os

from qdrant_client import models as qmodels
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.vector_store import get_policy_vector_store
from app.models.bots import Bot
from app.models.documents import Document

logger = logging.getLogger(__name__)

_DELETING = "DELETING"


def _delete_vectors(vector_store, doc_id: str) -> None:
    """Qdrant 에서 metadata.doc_id == doc_id 인 포인트를 영구 삭제(멱등 — 없으면 no-op)."""
    vector_store.client.delete(
        collection_name=vector_store.collection_name,
        points_selector=qmodels.FilterSelector(
            filter=qmodels.Filter(
                must=[
                    qmodels.FieldCondition(
                        key="metadata.doc_id", match=qmodels.MatchValue(value=doc_id)
                    )
                ]
            )
        ),
        wait=True,
    )


def _delete_file(file_path: str | None) -> None:
    """원본 파일 삭제(멱등 — 없으면 skip)."""
    if file_path and os.path.isfile(file_path):
        os.remove(file_path)


def run_cleanup(db: Session, vector_store=None) -> dict:
    """DELETING 봇·문서를 물리 삭제한다. 멱등 — 배치/수동 반복 호출 안전.

    반환: {documents_deleted, documents_failed, bots_deleted, bots_pending}.
    """
    vs = vector_store if vector_store is not None else get_policy_vector_store()
    docs_deleted = docs_failed = 0
    bots_deleted = bots_pending = 0

    # 1) 문서 물리 삭제: 벡터 → 파일 → 행 (문서별 독립 트랜잭션)
    deleting_docs = (
        db.execute(select(Document).where(Document.embedding_status == _DELETING))
        .scalars()
        .all()
    )
    for doc in deleting_docs:
        doc_id, file_path = doc.id, doc.file_path
        try:
            _delete_vectors(vs, doc_id)   # ① Qdrant (실패 시 except 로)
            _delete_file(file_path)       # ② 디스크 파일
            db.delete(doc)                # ③ RDB 행
            db.commit()
            docs_deleted += 1
        except Exception:  # noqa: BLE001 -- 부분삭제 방지: 롤백 후 DELETING 유지(다음 주기 재시도)
            db.rollback()
            docs_failed += 1
            logger.exception("문서 물리삭제 실패 — DELETING 유지(다음 주기 재시도): doc_id=%s", doc_id)

    # 2) 봇 물리 삭제: 소속 문서(owner_id=bot.id)가 모두 사라진 경우에만 (ORM cascade)
    deleting_bots = (
        db.execute(select(Bot).where(Bot.status == _DELETING)).scalars().all()
    )
    for bot in deleting_bots:
        remaining = db.execute(
            select(func.count()).select_from(Document).where(Document.owner_id == bot.id)
        ).scalar_one()
        if remaining > 0:
            bots_pending += 1
            logger.info(
                "봇 물리삭제 보류 — 잔여 문서 %d건(다음 주기): bot_id=%s", remaining, bot.id
            )
            continue
        try:
            db.delete(bot)  # cascade=all,delete-orphan -> sessions/messages/recommended 동반 삭제
            db.commit()
            bots_deleted += 1
        except Exception:  # noqa: BLE001
            db.rollback()
            logger.exception("봇 물리삭제 실패 — DELETING 유지(다음 주기 재시도): bot_id=%s", bot.id)

    result = {
        "documents_deleted": docs_deleted,
        "documents_failed": docs_failed,
        "bots_deleted": bots_deleted,
        "bots_pending": bots_pending,
    }
    logger.info("cleanup 완료: %s", result)
    return result
