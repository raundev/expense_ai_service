from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String
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

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<ReceiptTransaction id={self.id} file_id={self.file_id} "
            f"merchant={self.merchant_name!r} match_type={self.match_type!r}>"
        )
