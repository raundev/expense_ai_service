from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ReceiptRule(Base):
    """테넌트(회사/사업장)별 영수증 처리 규칙. (Rule Engine 용)

    실무 정산 규칙을 반영하기 위해 키워드/금액 범위뿐 아니라
    주말·휴일 여부, 사용 시간대, 카드사/업종 코드 등의 조건을 포함한다.
    `priority` 가 낮을수록(또는 운영 정책에 따라) 우선 적용되며,
    사업장(workplace) 규칙이 회사 공통 규칙보다 우선한다는 정책을
    서비스 레이어에서 해석한다.
    """

    __tablename__ = "company_receipt_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # --- 테넌트 식별 ---
    company_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    workplace_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)

    # --- 규칙 메타 ---
    rule_name: Mapped[str] = mapped_column(String(255), nullable=False)

    # --- 적용 조건 ---
    condition_keyword: Mapped[str | None] = mapped_column(String(255), nullable=True)
    condition_min_amount: Mapped[int | None] = mapped_column(Integer, nullable=True)
    condition_max_amount: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_weekend: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    is_holiday: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    usage_time_band: Mapped[str | None] = mapped_column(String(32), nullable=True)
    card_company_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    merchant_sector_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    merchant_sector_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # --- 결과 ---
    category_code: Mapped[str] = mapped_column(String(32), nullable=False)
    result_category: Mapped[str] = mapped_column(String(255), nullable=False)

    # --- 운영 ---
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<ReceiptRule id={self.id} company_id={self.company_id!r} "
            f"workplace_id={self.workplace_id!r} rule_name={self.rule_name!r} "
            f"priority={self.priority}>"
        )
