"""llm_recommender 단위 테스트: 후보 collapse/정렬, LLMSelection, select() 동작."""
from __future__ import annotations

from app.ai.llm_recommender import (
    DEFAULT_CATEGORIES,
    CategoryCandidate,
    LLMSelection,
    ReceiptLLMRecommender,
    collapse_rules_to_candidates,
)
from app.models.rules import ReceiptRule


def _rule(code: str, name: str, priority: int) -> ReceiptRule:
    return ReceiptRule(
        category_code=code,
        result_category=name,
        priority=priority,
        rule_name=f"{code}-rule",
    )


# ---------------------------------------------------------------------------- #
# DEFAULT_CATEGORIES
# ---------------------------------------------------------------------------- #
def test_default_categories_shape():
    assert len(DEFAULT_CATEGORIES) == 8
    assert all(isinstance(c, CategoryCandidate) for c in DEFAULT_CATEGORIES)
    codes = [c.code for c in DEFAULT_CATEGORIES]
    assert len(set(codes)) == 8  # 코드 중복 없음
    assert all(c.code == c.code.upper() for c in DEFAULT_CATEGORIES)  # 영문 대문자 코드


# ---------------------------------------------------------------------------- #
# collapse_rules_to_candidates
# ---------------------------------------------------------------------------- #
def test_collapse_distinct_and_min_priority_order():
    rules = [
        _rule("MEAL", "식대", 10),
        _rule("MEAL", "식대", 3),  # 같은 후보 -> min priority 3 으로 collapse
        _rule("TAXI", "교통비", 5),
        _rule("BOOK", "도서비", 1),
    ]
    assert collapse_rules_to_candidates(rules) == [
        CategoryCandidate("BOOK", "도서비"),
        CategoryCandidate("MEAL", "식대"),
        CategoryCandidate("TAXI", "교통비"),
    ]


def test_collapse_empty_returns_empty():
    assert collapse_rules_to_candidates([]) == []


def test_collapse_tie_preserves_first_seen():
    rules = [_rule("CCC", "씨", 2), _rule("AAA", "에이", 2)]
    assert collapse_rules_to_candidates(rules) == [
        CategoryCandidate("CCC", "씨"),
        CategoryCandidate("AAA", "에이"),
    ]


def test_collapse_same_code_different_name_kept_separate():
    rules = [_rule("X", "이름1", 1), _rule("X", "이름2", 2)]
    assert collapse_rules_to_candidates(rules) == [
        CategoryCandidate("X", "이름1"),
        CategoryCandidate("X", "이름2"),
    ]


# ---------------------------------------------------------------------------- #
# LLMSelection
# ---------------------------------------------------------------------------- #
def test_llmselection_defaults_for_offlist():
    sel = LLMSelection(selection=0)
    assert sel.selection == 0
    assert sel.suggested_code is None
    assert sel.suggested_name is None


# ---------------------------------------------------------------------------- #
# ReceiptLLMRecommender.select  (__new__ 로 무거운 __init__ 우회 -- 순수 select 로직만 검증)
# ---------------------------------------------------------------------------- #
def _bare_recommender() -> ReceiptLLMRecommender:
    return ReceiptLLMRecommender.__new__(ReceiptLLMRecommender)


def test_select_returns_none_when_disabled(payload_factory):
    rec = _bare_recommender()
    rec.chain = None  # 비활성(OPENAI_API_KEY 부재 등) 상태
    assert rec.select(payload_factory(), DEFAULT_CATEGORIES) is None


def test_select_returns_none_on_empty_candidates(payload_factory):
    rec = _bare_recommender()

    class _Boom:
        def invoke(self, _d):  # 호출되면 실패해야 함 (빈 후보면 invoke 전에 None)
            raise AssertionError("빈 후보에서는 chain.invoke 가 호출되면 안 된다")

    rec.chain = _Boom()
    assert rec.select(payload_factory(), []) is None


def test_select_builds_numbered_catalog_and_passes_payload(payload_factory):
    captured = {}

    class _FakeChain:
        def invoke(self, d):
            captured.update(d)
            return LLMSelection(selection=1)

    rec = _bare_recommender()
    rec.chain = _FakeChain()
    candidates = [CategoryCandidate("MEAL", "식대"), CategoryCandidate("TAXI", "교통비")]

    result = rec.select(payload_factory(merchant_name="김밥천국", amount=8000), candidates)

    assert result.selection == 1
    assert captured["categories"] == "1. 식대 (MEAL)\n2. 교통비 (TAXI)"
    assert captured["merchant_name"] == "김밥천국"
    assert captured["amount"] == 8000


def test_select_swallows_invoke_errors(payload_factory):
    class _Raiser:
        def invoke(self, _d):
            raise RuntimeError("LLM 다운")

    rec = _bare_recommender()
    rec.chain = _Raiser()
    assert rec.select(payload_factory(), DEFAULT_CATEGORIES) is None
