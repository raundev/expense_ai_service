"""관리자용 컴플라이언스 감사 서비스 (13단계).

12단계에서 적재한 `ReceiptTransaction` 의 컴플라이언스/소명 필드를 다루는 관리자
도메인 로직. 모든 조회·변경은 TenantContext(company_id + workplace_id) 로 격리된다.

소명 워크플로우 상태 전이:
    위반탐지 -> '미요청' --(request_explanation)--> '요청완료'
            --(process_explanation)--> '정상처리' | '위반확정'
"""
from __future__ import annotations

import logging
from datetime import date, datetime

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.core.dependencies import TenantContext
from app.models.transactions import ReceiptTransaction
from app.schemas.compliance import (
    ExplanationProcessPayload,
    ExplanationRequestPayload,
)

logger = logging.getLogger(__name__)

# explanation_status enum 값 (모델 String 컬럼에 저장)
STATUS_NOT_REQUESTED = "미요청"
STATUS_REQUESTED = "요청완료"
STATUS_NORMAL = "정상처리"
STATUS_VIOLATION = "위반확정"


class ComplianceTransactionNotFoundError(Exception):
    """요청한 transaction_ids 중 현재 테넌트 소유가 아니거나 존재하지 않는 ID가 있을 때.

    보안상 부분 적용을 피하고 전체를 거부한다(타 테넌트 데이터 노출/오변경 방지).
    """

    def __init__(self, missing: list[int]) -> None:
        self.missing = missing
        super().__init__(f"compliance transactions not found or not owned: {missing}")


class ComplianceService:
    """ReceiptTransaction 의 컴플라이언스 감사 도메인 서비스 (DB 전용, LLM 미사용)."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------ #
    # Dashboard KPI
    # ------------------------------------------------------------------ #
    def get_dashboard_kpi(
        self,
        tenant: TenantContext,
        start_date: date | None = None,
        end_date: date | None = None,
        department: str | None = None,
    ) -> dict:
        """현재 테넌트 범위의 컴플라이언스 KPI 집계.

        start_date/end_date 는 영수증 일자(receipt_date) 기준 필터.
        department 는 PRD 요구사항상 시그니처에 포함하나, 현재 ReceiptTransaction 에
        부서 컬럼이 없어 적용되지 않는다(향후 부서 컬럼 추가 시 연동할 예약 파라미터).
        """
        if department:
            logger.debug(
                "get_dashboard_kpi: department=%r 전달됐으나 모델에 부서 컬럼 부재로 미적용",
                department,
            )

        filters = self._base_filters(tenant, start_date, end_date)

        def _count(cond) -> object:
            # COUNT(*) FILTER 대신 dialect 안전한 SUM(CASE WHEN ...) 사용.
            return func.coalesce(func.sum(case((cond, 1), else_=0)), 0)

        stmt = select(
            _count(ReceiptTransaction.is_compliant.is_(False)).label("total_detected"),
            _count(ReceiptTransaction.explanation_status == STATUS_NOT_REQUESTED).label("not_requested"),
            _count(ReceiptTransaction.explanation_status == STATUS_REQUESTED).label("requested"),
            _count(ReceiptTransaction.explanation_status == STATUS_NORMAL).label("normal_processed"),
            _count(ReceiptTransaction.explanation_status == STATUS_VIOLATION).label("violation_confirmed"),
        ).where(*filters)

        row = self.db.execute(stmt).one()
        return {
            "total_detected": int(row.total_detected),
            "not_requested": int(row.not_requested),
            "requested": int(row.requested),
            "normal_processed": int(row.normal_processed),
            "violation_confirmed": int(row.violation_confirmed),
        }

    # ------------------------------------------------------------------ #
    # Violation grid
    # ------------------------------------------------------------------ #
    def get_violation_list(
        self,
        tenant: TenantContext,
        status: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        department: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[ReceiptTransaction]:
        """위반(is_compliant=False) 영수증 목록을 그리드용으로 조회(페이지네이션).

        status 가 주어지면 해당 소명 상태만 필터. 최신 영수증 일자 우선 정렬.
        """
        if department:
            logger.debug(
                "get_violation_list: department=%r 전달됐으나 모델에 부서 컬럼 부재로 미적용",
                department,
            )

        filters = self._base_filters(tenant, start_date, end_date)
        filters.append(ReceiptTransaction.is_compliant.is_(False))
        if status is not None:
            filters.append(ReceiptTransaction.explanation_status == status)

        stmt = (
            select(ReceiptTransaction)
            .where(*filters)
            .order_by(
                ReceiptTransaction.receipt_date.desc(),
                ReceiptTransaction.id.desc(),
            )
            .offset(skip)
            .limit(limit)
        )
        return list(self.db.execute(stmt).scalars().all())

    # ------------------------------------------------------------------ #
    # Explanation workflow
    # ------------------------------------------------------------------ #
    def request_explanation(
        self,
        tenant: TenantContext,
        payload: ExplanationRequestPayload,
        admin_id: str,
    ) -> list[ReceiptTransaction]:
        """대상 건들의 소명 상태를 '요청완료' 로 변경하고 요청 메타를 기록한다."""
        rows = self._fetch_owned(payload.transaction_ids, tenant)
        now = datetime.utcnow()
        for tx in rows:
            tx.explanation_status = STATUS_REQUESTED
            tx.explanation_request_dt = now
            tx.explanation_requester = admin_id
            tx.explanation_request_msg = payload.request_message

        self.db.commit()
        for tx in rows:
            self.db.refresh(tx)
        logger.info(
            "소명 요청: tenant=%s/%s admin=%s ids=%s",
            tenant.company_id,
            tenant.workplace_id,
            admin_id,
            payload.transaction_ids,
        )
        return rows

    def process_explanation(
        self,
        tenant: TenantContext,
        payload: ExplanationProcessPayload,
        admin_id: str,
    ) -> list[ReceiptTransaction]:
        """대상 건들의 소명 상태를 전달받은 status('정상처리'/'위반확정')로 종결 처리한다."""
        rows = self._fetch_owned(payload.transaction_ids, tenant)
        now = datetime.utcnow()
        for tx in rows:
            tx.explanation_status = payload.status
            tx.explanation_process_dt = now
            tx.explanation_processor = admin_id
            tx.explanation_process_comment = payload.process_comment

        self.db.commit()
        for tx in rows:
            self.db.refresh(tx)
        logger.info(
            "소명 처리: tenant=%s/%s admin=%s status=%s ids=%s",
            tenant.company_id,
            tenant.workplace_id,
            admin_id,
            payload.status,
            payload.transaction_ids,
        )
        return rows

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _base_filters(
        tenant: TenantContext,
        start_date: date | None,
        end_date: date | None,
    ) -> list:
        """테넌트 격리 + 선택적 영수증 일자 범위 필터."""
        filters = [
            ReceiptTransaction.company_id == tenant.company_id,
            ReceiptTransaction.workplace_id == tenant.workplace_id,
        ]
        if start_date is not None:
            filters.append(ReceiptTransaction.receipt_date >= start_date)
        if end_date is not None:
            filters.append(ReceiptTransaction.receipt_date <= end_date)
        return filters

    def _fetch_owned(
        self,
        transaction_ids: list[int],
        tenant: TenantContext,
    ) -> list[ReceiptTransaction]:
        """transaction_ids 를 현재 테넌트 범위로 조회. 하나라도 없으면 전체 거부."""
        stmt = select(ReceiptTransaction).where(
            ReceiptTransaction.id.in_(transaction_ids),
            ReceiptTransaction.company_id == tenant.company_id,
            ReceiptTransaction.workplace_id == tenant.workplace_id,
        )
        found = {tx.id: tx for tx in self.db.execute(stmt).scalars().all()}
        missing = [tid for tid in transaction_ids if tid not in found]
        if missing:
            raise ComplianceTransactionNotFoundError(missing)
        # 요청 순서를 보존하여 반환.
        return [found[tid] for tid in transaction_ids]
