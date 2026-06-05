"""공통 Document 모델 — 도메인 비종속 (설계 §2.2, Critical Design Rule #2).

이 테이블은 챗봇 전용이 아니다. 소유 주체를 범용 `owner_id` + `domain` 으로만 표현하고,
`bot_id` 같은 도메인 종속어를 컬럼·API 표면에 두지 않는다. 덕분에 컴플라이언스 엔진 등
다른 주체도 동일 모델로 문서를 적재·관리할 수 있다(`owner_id` 는 하드 FK 가 아닌 soft ref).

컴플라이언스 격리(Critical Design Rule #1 — 이중 게이트): 영수증 컴플라이언스 RAG 는
`domain="expense_rule" AND is_compliance_source=true` 로만 검색한다. 일반 규정
(`domain="policy"`)이 컴플라이언스 컨텍스트에 섞이지 않도록, 이 두 필드는 **벡터 청크
payload 에도 동일 저장**되어 메타데이터 필터로 활용된다(§8, §3).

삭제(Critical Design Rule #4 — Hard Delete 금지): `embedding_status="DELETING"` 으로
전이(검색/목록에서 즉시 제외)한 뒤, 정리 함수가 벡터(doc_id 필터) → 파일 → DB행 순으로
멱등 제거한다. '좀비 벡터'(행은 지워졌는데 벡터가 남아 재노출되는 사고)를 차단한다(§4.3).
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class Document(Base):
    """범용 문서 메타데이터 + 임베딩 라이프사이클 상태."""

    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)

    # --- 테넌트 식별 (조회/격리 키) ---
    company_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    workplace_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)

    # --- 도메인/소유 (범용 — Critical Design Rule #2) ---
    # domain 예: "policy"(챗봇 일반규정), "expense_rule"(경비/컴플라이언스).
    domain: Mapped[str] = mapped_column(
        String(32),
        index=True,
        nullable=False,
        default="policy",
        server_default=text("'policy'"),
    )
    # owner_id: policy 도메인에서는 bot_id(soft ref), expense_rule 은 컴플라이언스 엔진 식별자 등.
    owner_id: Mapped[str | None] = mapped_column(String(36), index=True, nullable=True)
    # is_compliance_source: 영수증 자동검증 RAG 근거 문서 표식. 벡터 payload 에도 동일 저장.
    is_compliance_source: Mapped[bool] = mapped_column(
        Boolean, index=True, nullable=False, default=False, server_default=text("false")
    )

    # --- 문서 메타 ---
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    byte_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_name: Mapped[str] = mapped_column(String(255), nullable=False)

    # --- 임베딩 라이프사이클: "PROCESSING" | "COMPLETED" | "FAILED" | "DELETING" ---
    embedding_status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="PROCESSING",
        server_default=text("'PROCESSING'"),
    )
    error_message: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<Document id={self.id!r} domain={self.domain!r} owner_id={self.owner_id!r} "
            f"status={self.embedding_status!r} compliance={self.is_compliance_source}>"
        )
