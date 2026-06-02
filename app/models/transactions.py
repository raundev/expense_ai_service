from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ReceiptFile(Base):
    """일괄 업로드된 영수증 파일 메타데이터.

    한 번의 batch 호출이 곧 한 개의 `ReceiptFile` 레코드이며,
    그 안에 속한 모든 행이 `ReceiptTransaction` 로 1:N 으로 연결된다.
    """

    __tablename__ = "receipt_files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # --- 테넌트 식별 ---
    company_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    workplace_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)

    # --- 파일 메타 ---
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    upload_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
    total_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<ReceiptFile id={self.id} file_name={self.file_name!r} "
            f"company_id={self.company_id!r} total_count={self.total_count}>"
        )


class ReceiptTransaction(Base):
    """업로드된 파일에 속한 개별 영수증 + 추천 엔진 결과 스냅샷.

    추천 결과(`recommended_*`, `match_type`, `applied_rule_id`)는 업로드 시점의
    의사결정을 보존하기 위해 그대로 적재한다. 사용자가 나중에 카테고리를
    수동 변경하면 `is_manually_modified=True` 로 표시한다.
    """

    __tablename__ = "receipt_transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("receipt_files.id"), index=True, nullable=False
    )

    # --- 테넌트 식별 (조회/격리 최적화용으로 직접 보유) ---
    company_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    workplace_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)

    # --- 사용자 조직 정보 (14단계, PRD 5/7: 부서별 집계·필터·엑셀 컬럼용) ---
    department: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)

    # --- 영수증 원본 ---
    receipt_date: Mapped[date] = mapped_column(Date, nullable=False)
    receipt_time: Mapped[str] = mapped_column(String(8), nullable=False)
    merchant_name: Mapped[str] = mapped_column(String(255), nullable=False)
    merchant_sector_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)

    # --- 추천 엔진 결과 스냅샷 ---
    recommended_category_code: Mapped[str] = mapped_column(String(64), nullable=False)
    recommended_result_category: Mapped[str] = mapped_column(String(255), nullable=False)
    applied_rule_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    match_type: Mapped[str] = mapped_column(String(16), nullable=False)

    # --- 사용자 보정 여부 ---
    is_manually_modified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    # --- 컴플라이언스(규정 준수) 감사 결과 (12단계, PRD 6.1) ---
    # is_compliant: 사칙 위배 여부. RAG 컴플라이언스 노드가 판정. 기본 True(준수).
    # server_default 는 SQLite/PostgreSQL 양쪽에서 동작하도록 text("true") 사용
    # (text("1") 은 PostgreSQL 의 boolean 컬럼 DEFAULT 로 거부됨).
    is_compliant: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    # violation_reason: 위반 사유 (프롬프트 초안의 compliance_reason). 준수 시 NULL.
    violation_reason: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    # --- 소명(해명) 워크플로우 추적 필드 (PRD '컴플라이언스 감사 소명 워크플로우') ---
    # explanation_status: '미요청' / '요청완료' / '정상처리' / '위반확정' (Enum 성격).
    #   위반 판정 시 compliance 노드가 '미요청' 으로 자동 초기화한다.
    explanation_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    explanation_request_dt: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )  # 소명 요청 일시
    explanation_requester: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )  # 소명 요청자
    explanation_process_dt: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )  # 소명 처리(승인/반려) 일시
    explanation_processor: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )  # 소명 처리자
    explanation_request_msg: Mapped[str | None] = mapped_column(
        String(2048), nullable=True
    )  # 소명 요청 메시지(사용자 제출 해명)
    explanation_process_comment: Mapped[str | None] = mapped_column(
        String(2048), nullable=True
    )  # 소명 처리 코멘트(감사자 의견)

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<ReceiptTransaction id={self.id} file_id={self.file_id} "
            f"merchant={self.merchant_name!r} match_type={self.match_type!r} "
            f"is_compliant={self.is_compliant}>"
        )
