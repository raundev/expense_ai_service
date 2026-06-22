"""데이터 플라이휠 영속화 정책 테스트.

- 배치(process_batch_transactions): off-list 제안(llm_suggested_*)을 DB 에 적재.
- 단건(recommend_single_receipt): DB 에 적재하지 않고 구조화 로그만 남김.
"""
from __future__ import annotations

import logging
from datetime import date

from sqlalchemy import select

from app.ai.llm_recommender import LLMSelection
from app.models.rules import ReceiptRule
from app.models.transactions import ReceiptTransaction
from app.schemas.transactions import TransactionBatchUploadRequest, TransactionRowDTO
from app.services.transaction_service import TransactionService


def _row(**overrides) -> TransactionRowDTO:
    data = dict(
        receipt_date=date(2026, 6, 4),
        receipt_time="12:30",
        merchant_name="듣보잡상점",
        merchant_sector_code=None,
        amount=99000,
    )
    data.update(overrides)
    return TransactionRowDTO(**data)


def _seed_meal_rule(db_session, tenant) -> None:
    """LLM 후보군을 만들기 위한 활성 규칙 1건 시드.

    조건 키워드를 어떤 영수증에도 매칭되지 않게 두어 1차 RULE 은 미스시키고,
    LLM 후보군(=[MEAL/식대])만 채워 3차 LLM 단계까지 흐르게 한다.
    (등록된 룰이 0개면 그래프가 NO_RULE 로 즉시 종료하므로 LLM 단계 검증 자체가 불가.)
    """
    db_session.add(
        ReceiptRule(
            company_id=tenant.company_id,
            workplace_id=tenant.workplace_id,
            rule_name="식대",
            condition_keyword="매칭되지않는키워드_ZZZ",
            category_code="MEAL",
            result_category="식대",
            priority=0,
            is_active=True,
        )
    )
    db_session.commit()


def test_batch_persists_offlist_suggestions(db_session, tenant, make_recommender, make_policy):
    _seed_meal_rule(db_session, tenant)  # LLM 단계까지 흐르도록 후보군 확보
    rec = make_recommender(LLMSelection(selection=0, suggested_code="GIFT", suggested_name="선물비"))
    svc = TransactionService(db=db_session, llm_recommender=rec, policy_service=make_policy())

    summary = svc.process_batch_transactions(
        TransactionBatchUploadRequest(file_name="f.xlsx", transactions=[_row()]), tenant
    )

    assert summary.total_count == 1
    assert summary.success_count == 0  # match_type=NONE 은 성공 아님

    rows = db_session.execute(select(ReceiptTransaction)).scalars().all()
    assert len(rows) == 1
    tx = rows[0]
    assert tx.match_type == "NONE"
    assert tx.recommended_category_code == "UNCLASSIFIED"
    assert tx.llm_suggested_code == "GIFT"  # off-list 제안이 영속화됨
    assert tx.llm_suggested_name == "선물비"


def test_batch_llm_match_persists_without_suggestion(db_session, tenant, make_recommender, make_policy):
    # 등록된 룰에서 추출한 후보([MEAL/식대]) 중 selection=1 -> MEAL/식대 채택.
    _seed_meal_rule(db_session, tenant)
    rec = make_recommender(LLMSelection(selection=1))
    policy = make_policy(is_compliant=True)
    svc = TransactionService(db=db_session, llm_recommender=rec, policy_service=policy)

    summary = svc.process_batch_transactions(
        TransactionBatchUploadRequest(file_name="f.xlsx", transactions=[_row()]), tenant
    )

    assert summary.success_count == 1
    tx = db_session.execute(select(ReceiptTransaction)).scalars().first()
    assert tx.match_type == "LLM"
    assert tx.recommended_category_code == "MEAL"
    assert tx.recommended_result_category == "식대"
    assert tx.llm_suggested_code is None  # 정상 매칭엔 제안값 없음
    assert tx.llm_suggested_name is None
    assert policy.called is True  # LLM 매칭은 컴플라이언스 노드를 거친다


def test_single_test_does_not_persist_but_logs(
    db_session, tenant, make_recommender, make_policy, payload_factory, caplog
):
    _seed_meal_rule(db_session, tenant)
    rec = make_recommender(LLMSelection(selection=0, suggested_code="GIFT", suggested_name="선물비"))
    svc = TransactionService(db=db_session, llm_recommender=rec, policy_service=make_policy())

    with caplog.at_level(logging.INFO, logger="app.services.transaction_service"):
        resp = svc.recommend_single_receipt(payload_factory(merchant_name="듣보잡상점"), tenant)

    assert resp.match_type == "NONE"
    # 단건 테스트는 DB 에 적재하지 않는다.
    assert db_session.execute(select(ReceiptTransaction)).scalars().all() == []
    # 구조화 로그(offlist_suggestion)만 남긴다.
    messages = [r.getMessage() for r in caplog.records]
    assert any(
        "offlist_suggestion" in m and "GIFT" in m and "선물비" in m for m in messages
    )


def test_single_test_llm_match_emits_no_offlist_log(
    db_session, tenant, make_recommender, make_policy, payload_factory, caplog
):
    # 정상 LLM 매칭(selection=1)은 off-list 제안 로그를 남기지 않아야 한다.
    _seed_meal_rule(db_session, tenant)
    rec = make_recommender(LLMSelection(selection=1))
    svc = TransactionService(db=db_session, llm_recommender=rec, policy_service=make_policy())

    with caplog.at_level(logging.INFO, logger="app.services.transaction_service"):
        resp = svc.recommend_single_receipt(payload_factory(), tenant)

    assert resp.match_type == "LLM"
    assert not any("offlist_suggestion" in r.getMessage() for r in caplog.records)
