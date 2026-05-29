from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ApprovalHistory(Base):
    """과거 영수증 승인/반려 내역. (Few-shot 및 History Lookup 용)

    규칙 매칭이 실패했을 때 동일 테넌트의 유사 승인 사례를 검색하여
    용도를 추론하는 데 사용한다. 벡터 DB 임베딩 시에도 원천 데이터로
    참조된다.
    """

    __tablename__ = "approval_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # --- 테넌트 식별 ---
    company_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    workplace_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)

    # --- 요청자 ---
    user_id: Mapped[str] = mapped_column(String(64), nullable=False)

    # --- 영수증 내역 ---
    receipt_amount: Mapped[int] = mapped_column(Integer, nullable=False)
    receipt_merchant: Mapped[str] = mapped_column(String(255), nullable=False)
    receipt_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    # --- 처리 결과 ---
    approved_category: Mapped[str] = mapped_column(String(255), nullable=False)
    rejection_reason: Mapped[str | None] = mapped_column(String(512), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<ApprovalHistory id={self.id} company_id={self.company_id!r} "
            f"user_id={self.user_id!r} status={self.status!r} "
            f"amount={self.receipt_amount}>"
        )
