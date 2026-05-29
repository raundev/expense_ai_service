from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.dependencies import TenantContext
from app.models.rules import ReceiptRule
from app.schemas.rules import RuleRequest


class RuleNotFoundError(Exception):
    """대상 규칙이 존재하지 않거나, 요청 테넌트의 소유가 아닐 때 발생.

    보안상 '존재하지만 권한 없음'과 '존재하지 않음'을 구분하지 않는다
    (타 테넌트 데이터의 존재 여부 노출을 방지).
    """

    def __init__(self, rule_id: int) -> None:
        self.rule_id = rule_id
        super().__init__(f"Rule {rule_id} not found")


class RuleService:
    """ReceiptRule 도메인 비즈니스 로직.

    멀티테넌트 격리를 서비스 레이어에서 강제한다:
    - 쓰기(create/update): TenantContext 의 company_id / workplace_id 로 소유권 강제.
    - 읽기(get_active_rules): company_id 일치 + (workplace_id 일치 또는 NULL=회사 공통)
      조건으로 필터.
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------ #
    # Create
    # ------------------------------------------------------------------ #
    def create_rule(self, payload: RuleRequest, tenant: TenantContext) -> ReceiptRule:
        """신규 규칙 등록. 테넌트 식별자는 헤더(TenantContext)의 값으로 강제 설정한다."""
        rule = ReceiptRule(
            company_id=tenant.company_id,
            workplace_id=tenant.workplace_id,
            **payload.model_dump(),
        )
        self.db.add(rule)
        self.db.commit()
        self.db.refresh(rule)
        return rule

    # ------------------------------------------------------------------ #
    # Update
    # ------------------------------------------------------------------ #
    def update_rule(
        self,
        rule_id: int,
        payload: RuleRequest,
        tenant: TenantContext,
    ) -> ReceiptRule:
        """기존 규칙 수정.

        권한 검증: rule_id 가 (company_id, workplace_id) 가 모두 일치하는 본인
        테넌트의 규칙일 때만 수정 가능. 그렇지 않으면 RuleNotFoundError.

        Body 의 company_id / workplace_id 는 어차피 RuleRequest 스키마에 없으므로
        테넌트 소유권은 변하지 않는다.
        """
        stmt = select(ReceiptRule).where(
            ReceiptRule.id == rule_id,
            ReceiptRule.company_id == tenant.company_id,
            ReceiptRule.workplace_id == tenant.workplace_id,
        )
        rule = self.db.execute(stmt).scalar_one_or_none()
        if rule is None:
            raise RuleNotFoundError(rule_id)

        for field, value in payload.model_dump().items():
            setattr(rule, field, value)

        self.db.commit()
        self.db.refresh(rule)
        return rule

    # ------------------------------------------------------------------ #
    # Read
    # ------------------------------------------------------------------ #
    def get_active_rules(self, tenant: TenantContext) -> list[ReceiptRule]:
        """활성화된 규칙 목록 조회.

        비즈니스 규칙:
            * company_id 가 일치해야 한다.
            * workplace_id 가 요청 사업장과 일치하거나, NULL(=회사 공통 규칙) 이어야 한다.
            * is_active=True 만 대상.
            * priority 오름차순 (낮을수록 먼저 적용).
        """
        stmt = (
            select(ReceiptRule)
            .where(
                ReceiptRule.company_id == tenant.company_id,
                or_(
                    ReceiptRule.workplace_id == tenant.workplace_id,
                    ReceiptRule.workplace_id.is_(None),
                ),
                ReceiptRule.is_active.is_(True),
            )
            .order_by(ReceiptRule.priority.asc())
        )
        return list(self.db.execute(stmt).scalars().all())
