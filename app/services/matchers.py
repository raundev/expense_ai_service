"""순수(에 가까운) 매칭 헬퍼들 -- TransactionService 와 LangGraph 노드가 공유.

transaction_service.py 안에 두면 graph.py 와 순환 import 가 되므로,
중립 모듈로 분리한다. 다음 두 가지를 제공한다:

* `rule_matches(rule, payload) -> bool` -- RULE 매칭 (1차 엔진)
* `find_recent_approved_history(db, payload, tenant) -> ApprovalHistory | None`
  -- HISTORY 매칭 (2차 엔진)
"""
from __future__ import annotations

from datetime import time

from sqlalchemy import literal, or_, select
from sqlalchemy.orm import Session

from app.core.dependencies import TenantContext
from app.models.history import ApprovalHistory
from app.models.rules import ReceiptRule
from app.schemas.transactions import SingleTransactionTestRequest


# ---------------------------------------------------------------------------- #
# Time band helpers
# ---------------------------------------------------------------------------- #
_NAMED_BANDS: dict[str, tuple[time, time]] = {
    "BREAKFAST": (time(6, 0), time(10, 0)),
    "LUNCH": (time(11, 0), time(14, 0)),
    "DINNER": (time(17, 0), time(21, 0)),
    "LATE_NIGHT": (time(22, 0), time(6, 0)),  # 자정 걸침
}


def _parse_hhmm(s: str) -> time | None:
    try:
        if ":" in s:
            h, m = s.split(":", 1)
            return time(int(h), int(m))
        return time(int(s), 0)
    except (ValueError, IndexError):
        return None


def _parse_time_band(band: str) -> tuple[time, time] | None:
    if band.upper() in _NAMED_BANDS:
        return _NAMED_BANDS[band.upper()]
    if "-" not in band:
        return None
    start_str, end_str = band.split("-", 1)
    start = _parse_hhmm(start_str)
    end = _parse_hhmm(end_str)
    if start is None or end is None:
        return None
    return start, end


def _in_time_band(t: time, start: time, end: time) -> bool:
    if start <= end:
        return start <= t < end
    return t >= start or t < end


# ---------------------------------------------------------------------------- #
# Rule matcher
# ---------------------------------------------------------------------------- #
def rule_matches(rule: ReceiptRule, payload: SingleTransactionTestRequest) -> bool:
    """규칙의 NULL 이 아닌 조건들이 모두 영수증을 만족하면 True."""
    if rule.condition_keyword is not None:
        if rule.condition_keyword not in payload.merchant_name:
            return False

    if rule.condition_min_amount is not None and payload.amount < rule.condition_min_amount:
        return False
    if rule.condition_max_amount is not None and payload.amount > rule.condition_max_amount:
        return False

    if rule.is_weekend is not None:
        is_weekend_actual = payload.receipt_date.weekday() >= 5  # 토(5)/일(6)
        if rule.is_weekend != is_weekend_actual:
            return False

    if rule.is_holiday is not None:
        # TODO: 공휴일 캘린더 연동. 현재는 평일(False) 로 가정.
        is_holiday_actual = False
        if rule.is_holiday != is_holiday_actual:
            return False

    if rule.usage_time_band is not None:
        band = _parse_time_band(rule.usage_time_band)
        if band is None:
            return False
        receipt_t = _parse_hhmm(payload.receipt_time)
        if receipt_t is None:
            return False
        if not _in_time_band(receipt_t, band[0], band[1]):
            return False

    if rule.merchant_sector_code is not None:
        if payload.merchant_sector_code is None:
            return False
        if rule.merchant_sector_code != payload.merchant_sector_code:
            return False

    # payload 에 원천 필드가 없는 조건들은 보수적으로 미매칭 처리.
    if rule.card_company_code is not None:
        return False
    if rule.merchant_sector_name is not None:
        return False

    return True


# ---------------------------------------------------------------------------- #
# History lookup
# ---------------------------------------------------------------------------- #
def find_recent_approved_history(
    db: Session,
    payload: SingleTransactionTestRequest,
    tenant: TenantContext,
) -> ApprovalHistory | None:
    """같은 테넌트의 'APPROVED' 이력 중 가맹점명 양방향 부분 일치 1건(최신순)."""
    merchant = payload.merchant_name
    stmt = (
        select(ApprovalHistory)
        .where(
            ApprovalHistory.company_id == tenant.company_id,
            ApprovalHistory.workplace_id == tenant.workplace_id,
            ApprovalHistory.status == "APPROVED",
            or_(
                ApprovalHistory.receipt_merchant.contains(merchant),
                literal(merchant).contains(ApprovalHistory.receipt_merchant),
            ),
        )
        .order_by(ApprovalHistory.receipt_date.desc())
        .limit(1)
    )
    return db.execute(stmt).scalar_one_or_none()
