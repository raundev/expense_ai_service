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
    ExplanationCancelPayload,
    ExplanationProcessPayload,
    ExplanationRequestPayload,
)

logger = logging.getLogger(__name__)

# explanation_status enum 값 (모델 String 컬럼에 저장)
STATUS_NOT_REQUESTED = "미요청"
STATUS_REQUESTED = "요청완료"
STATUS_SUBMITTED = "소명제출"  # Phase 2: 직원이 소명 제출
STATUS_OVERDUE = "기한초과"  # Phase 2: 기한 내 미제출(에스컬레이션)
STATUS_NORMAL = "정상처리"
STATUS_VIOLATION = "위반확정"

# 관리자가 최종 처리(정상처리/위반확정)할 수 있는 상태 집합 (Phase 2 확장).
# 요청완료(직접 처리) / 소명제출(직원 제출 검토) / 기한초과(미제출 종결)에서 처리 가능.
PROCESSABLE_STATES = {STATUS_REQUESTED, STATUS_SUBMITTED, STATUS_OVERDUE}


class ComplianceTransactionNotFoundError(Exception):
    """요청한 transaction_ids 중 현재 테넌트 소유가 아니거나 존재하지 않는 ID가 있을 때.

    보안상 부분 적용을 피하고 전체를 거부한다(타 테넌트 데이터 노출/오변경 방지).
    """

    def __init__(self, missing: list[int]) -> None:
        self.missing = missing
        super().__init__(f"compliance transactions not found or not owned: {missing}")


class ComplianceInvalidStateError(Exception):
    """허용되지 않는 소명 상태 전이 시도 (예: '요청완료'가 아닌 건을 취소하려 할 때)."""

    def __init__(self, ids: list[int], expected: str) -> None:
        self.ids = ids
        self.expected = expected
        super().__init__(f"transactions {ids} are not in expected state '{expected}'")


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

        start_date/end_date 는 영수증 일자(receipt_date) 기준 필터, department 는 부서 필터.
        """
        filters = self._base_filters(tenant, start_date, end_date, department)

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

        status 가 주어지면 해당 소명 상태만, department 가 주어지면 해당 부서만 필터.
        최신 영수증 일자 우선 정렬.
        """
        stmt = (
            self._violation_select(tenant, status, start_date, end_date, department)
            .offset(skip)
            .limit(limit)
        )
        return list(self.db.execute(stmt).scalars().all())

    def get_violations_for_export(
        self,
        tenant: TenantContext,
        status: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        department: str | None = None,
    ) -> list[ReceiptTransaction]:
        """엑셀 다운로드용 -- 그리드와 동일 필터에 **페이지네이션 없이** 전체 위반을 조회."""
        stmt = self._violation_select(tenant, status, start_date, end_date, department)
        return list(self.db.execute(stmt).scalars().all())

    # ------------------------------------------------------------------ #
    # Dashboard charts (PRD 5.1)
    # ------------------------------------------------------------------ #
    def get_dashboard_charts(
        self,
        tenant: TenantContext,
        start_date: date | None = None,
        end_date: date | None = None,
        department: str | None = None,
    ) -> dict:
        """시각화용 집계: 일별 추이 / 항목(용도)별 분포 / 부서별 현황.

        모두 위반(is_compliant=False) + 테넌트/기간/부서 필터를 공유하며 SQL GROUP BY 로 집계.
        """
        filters = self._base_filters(tenant, start_date, end_date, department)
        filters.append(ReceiptTransaction.is_compliant.is_(False))

        # 1) 일별 위반 탐지 추이
        trend_stmt = (
            select(ReceiptTransaction.receipt_date, func.count().label("cnt"))
            .where(*filters)
            .group_by(ReceiptTransaction.receipt_date)
            .order_by(ReceiptTransaction.receipt_date)
        )
        violation_trend = [
            {"date": str(r.receipt_date), "count": int(r.cnt)}
            for r in self.db.execute(trend_stmt)
        ]

        # 2) 위반 항목(용도)별 분포 (건수 내림차순)
        cat_stmt = (
            select(ReceiptTransaction.recommended_result_category, func.count().label("cnt"))
            .where(*filters)
            .group_by(ReceiptTransaction.recommended_result_category)
            .order_by(func.count().desc())
        )
        violation_by_category = [
            {"label": r.recommended_result_category, "count": int(r.cnt)}
            for r in self.db.execute(cat_stmt)
        ]

        # 3) 부서별 위반 현황 (건수 내림차순, 미지정은 '미지정')
        dept_stmt = (
            select(ReceiptTransaction.department, func.count().label("cnt"))
            .where(*filters)
            .group_by(ReceiptTransaction.department)
            .order_by(func.count().desc())
        )
        violation_by_department = [
            {"label": r.department or "미지정", "count": int(r.cnt)}
            for r in self.db.execute(dept_stmt)
        ]

        return {
            "violation_trend": violation_trend,
            "violation_by_category": violation_by_category,
            "violation_by_department": violation_by_department,
        }

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
            tx.due_date = payload.due_date  # Phase 2: 소명 기한(선택)

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
        """대상 건들의 소명 상태를 전달받은 status('정상처리'/'위반확정')로 종결 처리한다.

        [상태 전이 가드] '요청완료' / '소명제출' / '기한초과' 상태에서만 처리 가능하다.
        그 외(미요청·이미 종결됨)가 섞여 있으면 전체 거부(409).
        """
        rows = self._fetch_owned(payload.transaction_ids, tenant)
        invalid = [tx.id for tx in rows if tx.explanation_status not in PROCESSABLE_STATES]
        if invalid:
            raise ComplianceInvalidStateError(invalid, "요청완료/소명제출/기한초과")

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

    def cancel_explanation(
        self,
        tenant: TenantContext,
        payload: ExplanationCancelPayload,
        admin_id: str,
    ) -> list[ReceiptTransaction]:
        """소명 요청을 취소해 상태를 '요청완료' -> '미요청' 으로 롤백한다 (PRD 5.3).

        '요청완료' 상태가 아닌 건이 섞여 있으면 전체 거부(ComplianceInvalidStateError).
        롤백 시 요청 메타(요청일시/요청자/요청메시지)를 초기화한다.
        """
        rows = self._fetch_owned(payload.transaction_ids, tenant)

        invalid = [tx.id for tx in rows if tx.explanation_status != STATUS_REQUESTED]
        if invalid:
            raise ComplianceInvalidStateError(invalid, STATUS_REQUESTED)

        for tx in rows:
            tx.explanation_status = STATUS_NOT_REQUESTED
            tx.explanation_request_dt = None
            tx.explanation_requester = None
            tx.explanation_request_msg = None

        self.db.commit()
        for tx in rows:
            self.db.refresh(tx)
        logger.info(
            "소명 요청 취소(rollback->미요청): tenant=%s/%s admin=%s ids=%s reason=%r",
            tenant.company_id,
            tenant.workplace_id,
            admin_id,
            payload.transaction_ids,
            payload.cancel_reason,
        )
        return rows

    # ------------------------------------------------------------------ #
    # Employee self-service (Phase 2, 17단계)
    # ------------------------------------------------------------------ #
    def get_my_violations(
        self,
        tenant: TenantContext,
        employee_id: str,
        status: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[ReceiptTransaction]:
        """직원 **본인**의 위반/소명 대상 영수증만 조회한다.

        보안: (company_id, workplace_id, employee_id) **3중 격리**. 타인/타테넌트 건은
        애초에 쿼리에 포함되지 않는다. status 로 특정 소명 상태만 필터 가능.
        """
        filters = [
            ReceiptTransaction.company_id == tenant.company_id,
            ReceiptTransaction.workplace_id == tenant.workplace_id,
            ReceiptTransaction.employee_id == employee_id,
            ReceiptTransaction.is_compliant.is_(False),
        ]
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

    def submit_explanation(
        self,
        tenant: TenantContext,
        transaction_id: int,
        employee_id: str,
        content: str,
    ) -> ReceiptTransaction:
        """직원이 본인 위반 건에 소명을 제출한다 ('요청완료' -> '소명제출').

        보안/검증:
            - (company_id, workplace_id, employee_id, id) 모두 일치하는 본인 건만 대상.
              아니면 ComplianceTransactionNotFoundError(404) -- 타인 건 존재조차 비노출.
            - 현재 상태가 '요청완료' 가 아니면 ComplianceInvalidStateError(409).
        """
        stmt = select(ReceiptTransaction).where(
            ReceiptTransaction.id == transaction_id,
            ReceiptTransaction.company_id == tenant.company_id,
            ReceiptTransaction.workplace_id == tenant.workplace_id,
            ReceiptTransaction.employee_id == employee_id,
        )
        tx = self.db.execute(stmt).scalar_one_or_none()
        if tx is None:
            raise ComplianceTransactionNotFoundError([transaction_id])
        if tx.explanation_status != STATUS_REQUESTED:
            raise ComplianceInvalidStateError([transaction_id], STATUS_REQUESTED)

        tx.explanation_status = STATUS_SUBMITTED
        tx.explanation_content = content
        tx.explanation_submit_dt = datetime.utcnow()
        self.db.commit()
        self.db.refresh(tx)
        logger.info(
            "직원 소명 제출: tenant=%s/%s employee=%s tx=%s -> 소명제출",
            tenant.company_id,
            tenant.workplace_id,
            employee_id,
            transaction_id,
        )
        return tx

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _base_filters(
        tenant: TenantContext,
        start_date: date | None,
        end_date: date | None,
        department: str | None = None,
    ) -> list:
        """테넌트 격리 + 선택적 영수증 일자 범위/부서 필터 (14단계부터 department 실제 적용)."""
        filters = [
            ReceiptTransaction.company_id == tenant.company_id,
            ReceiptTransaction.workplace_id == tenant.workplace_id,
        ]
        if start_date is not None:
            filters.append(ReceiptTransaction.receipt_date >= start_date)
        if end_date is not None:
            filters.append(ReceiptTransaction.receipt_date <= end_date)
        if department:
            filters.append(ReceiptTransaction.department == department)
        return filters

    def _violation_select(
        self,
        tenant: TenantContext,
        status: str | None,
        start_date: date | None,
        end_date: date | None,
        department: str | None,
    ):
        """위반(is_compliant=False) 영수증 정렬 SELECT (offset/limit 미적용).

        그리드 조회(get_violation_list)와 엑셀 export(get_violations_for_export)가 공유.
        """
        filters = self._base_filters(tenant, start_date, end_date, department)
        filters.append(ReceiptTransaction.is_compliant.is_(False))
        if status is not None:
            filters.append(ReceiptTransaction.explanation_status == status)
        return (
            select(ReceiptTransaction)
            .where(*filters)
            .order_by(
                ReceiptTransaction.receipt_date.desc(),
                ReceiptTransaction.id.desc(),
            )
        )

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
