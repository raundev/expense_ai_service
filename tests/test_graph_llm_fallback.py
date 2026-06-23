"""graph.py 노드 단위 테스트: rule_node 후보 추출/절단, llm_node 번호 선택 매핑."""
from __future__ import annotations

import logging

from app.ai.graph import (
    NO_RECOMMENDATION_MESSAGE,
    NO_RULE_MESSAGE,
    llm_node,
    rule_node,
)
from app.ai.llm_recommender import (
    TOP_N_CANDIDATES,
    CategoryCandidate,
    LLMSelection,
)
from app.models.rules import ReceiptRule


def _seed_rule(session, **kw) -> ReceiptRule:
    defaults = dict(
        company_id="C1",
        workplace_id="W1",
        rule_name="r",
        category_code="X",
        result_category="엑스",
        priority=0,
        is_active=True,
    )
    defaults.update(kw)
    rule = ReceiptRule(**defaults)
    session.add(rule)
    return rule


class _Rec:
    """select() 가 고정 결과를 반환하고 받은 후보를 기록하는 경량 fake."""

    def __init__(self, result):
        self.result = result
        self.seen = None

    def select(self, payload, candidates):
        self.seen = list(candidates)
        return self.result


# ---------------------------------------------------------------------------- #
# rule_node
# ---------------------------------------------------------------------------- #
def test_rule_node_match_returns_rule(db_session, tenant, payload_factory):
    _seed_rule(
        db_session,
        condition_keyword="스타벅스",
        category_code="MEAL",
        result_category="식대",
        priority=1,
    )
    db_session.commit()
    out = rule_node(
        {
            "db_session": db_session,
            "payload": payload_factory(merchant_name="스타벅스 강남점"),
            "tenant": tenant,
        }
    )
    assert out["match_type"] == "RULE"
    assert out["category_code"] == "MEAL"
    assert out["applied_rule_id"] is not None
    assert "category_candidates" not in out  # 매칭 시 후보군은 만들지 않음


def test_rule_node_miss_returns_sorted_candidates(db_session, tenant, payload_factory):
    # 어떤 규칙도 매칭되지 않도록 영수증에 없는 키워드를 건다.
    _seed_rule(db_session, condition_keyword="택시", category_code="TAXI", result_category="교통비", priority=5)
    _seed_rule(db_session, condition_keyword="서점", category_code="BOOK", result_category="도서비", priority=1)
    db_session.commit()
    out = rule_node(
        {
            "db_session": db_session,
            "payload": payload_factory(merchant_name="스타벅스 강남점"),
            "tenant": tenant,
        }
    )
    assert "match_type" not in out
    assert out["category_candidates"] == [
        CategoryCandidate("BOOK", "도서비"),
        CategoryCandidate("TAXI", "교통비"),
    ]


def test_rule_node_truncates_to_top_n_and_warns(db_session, tenant, payload_factory, caplog):
    total = TOP_N_CANDIDATES + 5
    for i in range(total):
        _seed_rule(
            db_session,
            condition_keyword=f"ZZZ{i}",  # 영수증에 없는 키워드 -> 전부 미매칭
            category_code=f"CODE{i:02d}",
            result_category=f"용도{i:02d}",
            priority=i,
        )
    db_session.commit()
    with caplog.at_level(logging.WARNING, logger="app.ai.graph"):
        out = rule_node(
            {
                "db_session": db_session,
                "payload": payload_factory(merchant_name="스타벅스 강남점"),
                "tenant": tenant,
            }
        )
    assert len(out["category_candidates"]) == TOP_N_CANDIDATES
    assert any(
        r.levelno == logging.WARNING and "절단" in r.getMessage() for r in caplog.records
    )


def test_rule_node_no_rules_returns_none_with_admin_message(db_session, tenant, payload_factory):
    # 활성 규칙이 0개면 후보를 만들지 않고 즉시 NONE(NO_RULE) + 관리자 문의 안내로 종료한다.
    out = rule_node(
        {"db_session": db_session, "payload": payload_factory(), "tenant": tenant}
    )
    assert out["match_type"] == "NONE"
    assert out["category_code"] == "NO_RULE"
    assert out["message"] == NO_RULE_MESSAGE
    assert "category_candidates" not in out  # LLM 후보군을 만들지 않는다


# ---------------------------------------------------------------------------- #
# llm_node
# ---------------------------------------------------------------------------- #
def test_llm_node_selection_maps_candidate(payload_factory):
    cands = [CategoryCandidate("A", "에이"), CategoryCandidate("B", "비"), CategoryCandidate("C", "씨")]
    rec = _Rec(LLMSelection(selection=2))
    out = llm_node(
        {"payload": payload_factory(), "llm_recommender": rec, "category_candidates": cands}
    )
    assert out["match_type"] == "LLM"
    assert out["category_code"] == "B"
    assert out["result_category"] == "비"
    assert out["applied_rule_id"] is None


def test_llm_node_offlist_sets_none_with_suggestions(payload_factory):
    cands = [CategoryCandidate("A", "에이")]
    rec = _Rec(LLMSelection(selection=0, suggested_code="GIFT", suggested_name="선물비"))
    out = llm_node(
        {"payload": payload_factory(), "llm_recommender": rec, "category_candidates": cands}
    )
    assert out["match_type"] == "NONE"
    assert out["category_code"] == "UNCLASSIFIED"
    assert out["result_category"] == "미분류"
    assert out["message"] == NO_RECOMMENDATION_MESSAGE
    assert out["llm_suggested_code"] == "GIFT"  # 데이터 플라이휠용 제안은 계속 보존
    assert out["llm_suggested_name"] == "선물비"


def test_llm_node_no_candidates_returns_none_without_calling_llm(payload_factory):
    # 후보군 미설정 -> 콜드스타트 기본값을 주입하지 않고 '추천 용도 없음(NONE)' 으로 닫는다.
    rec = _Rec(LLMSelection(selection=1))
    out = llm_node({"payload": payload_factory(), "llm_recommender": rec})
    assert rec.seen is None  # LLM 을 아예 호출하지 않는다(룰 없이 추측 금지)
    assert out["match_type"] == "NONE"
    assert out["category_code"] == "UNCLASSIFIED"
    assert out["message"] == NO_RECOMMENDATION_MESSAGE


def test_llm_node_empty_candidates_returns_none_without_calling_llm(payload_factory):
    rec = _Rec(LLMSelection(selection=1))
    out = llm_node(
        {"payload": payload_factory(), "llm_recommender": rec, "category_candidates": []}
    )
    assert rec.seen is None
    assert out["match_type"] == "NONE"
    assert out["category_code"] == "UNCLASSIFIED"


def test_llm_node_disabled_recommender_returns_none(payload_factory):
    rec = _Rec(None)  # select() 가 None -> 비활성/실패
    out = llm_node(
        {
            "payload": payload_factory(),
            "llm_recommender": rec,
            "category_candidates": [CategoryCandidate("A", "에이")],
        }
    )
    assert out["match_type"] == "NONE"
    assert out["category_code"] == "UNCLASSIFIED"
    assert "llm_suggested_code" not in out  # 실패 경로엔 제안값이 없다


def test_llm_node_out_of_range_treated_as_offlist_with_warning(payload_factory, caplog):
    cands = [CategoryCandidate("A", "에이"), CategoryCandidate("B", "비")]
    rec = _Rec(LLMSelection(selection=99))  # 범위 밖(이상 응답)
    with caplog.at_level(logging.WARNING, logger="app.ai.graph"):
        out = llm_node(
            {"payload": payload_factory(), "llm_recommender": rec, "category_candidates": cands}
        )
    assert out["match_type"] == "NONE"
    assert out["llm_suggested_code"] is None
    assert any("범위 밖" in r.getMessage() for r in caplog.records)
