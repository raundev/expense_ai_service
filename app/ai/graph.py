"""영수증 용도 추천 파이프라인의 LangGraph StateGraph 정의 (10단계).

이전(9단계)까지의 하드코딩된 순차 if-return 체인을 그래프로 모델링한다.
외부 동작은 동일하지만 노드/엣지가 명시적으로 분리되어, 추후 컴플라이언스
검증/사용자 확인 등의 노드를 레고처럼 끼워 넣기 쉽다.

      START
        │
        ▼
      ┌──────┐  RULE 매칭  ┌─────┐
      │ rule │ ──────────► │ END │
      └──┬───┘              └─────┘
         │ miss
         ▼
      ┌─────────┐  HISTORY  ┌─────┐
      │ history │ ────────► │ END │
      └────┬────┘            └─────┘
           │ miss
           ▼
        ┌──────┐  LLM / NONE  ┌─────┐
        │ llm  │ ───────────► │ END │
        └──────┘              └─────┘
"""
from __future__ import annotations

from functools import lru_cache
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy.orm import Session

from app.ai.llm_recommender import ReceiptLLMRecommender
from app.core.dependencies import TenantContext
from app.schemas.transactions import MatchType, SingleTransactionTestRequest
from app.services.matchers import find_recent_approved_history, rule_matches
from app.services.rule_service import RuleService


# ---------------------------------------------------------------------------- #
# State
# ---------------------------------------------------------------------------- #
class TransactionState(TypedDict, total=False):
    """그래프 전체를 관통하는 상태.

    Inputs (호출 시 반드시 모두 주입):
        payload         : 추천 대상 영수증 데이터
        tenant          : 멀티테넌트 식별 (company_id / workplace_id)
        db_session      : SQLAlchemy Session (rule/history 쿼리에 사용)
        llm_recommender : LLM 3차 fallback 구현체 (DI -> 테스트 mock 가능)

    Outputs (노드가 채워 넣음. 그래프 종료 시 match_type 은 반드시 채워져 있음):
        match_type, category_code, result_category, applied_rule_id
    """

    # Inputs
    payload: SingleTransactionTestRequest
    tenant: TenantContext
    db_session: Session
    llm_recommender: ReceiptLLMRecommender

    # Outputs
    match_type: MatchType
    category_code: str
    result_category: str
    applied_rule_id: int | None


# ---------------------------------------------------------------------------- #
# Nodes
# ---------------------------------------------------------------------------- #
def rule_node(state: TransactionState) -> dict:
    """1차 RULE 매칭. 활성 규칙을 priority ASC 로 가져와 첫 매칭을 채택."""
    db = state["db_session"]
    payload = state["payload"]
    tenant = state["tenant"]

    active_rules = RuleService(db).get_active_rules(tenant)
    for rule in active_rules:
        if rule_matches(rule, payload):
            return {
                "match_type": "RULE",
                "category_code": rule.category_code,
                "result_category": rule.result_category,
                "applied_rule_id": rule.id,
            }
    return {}  # 미매칭 -- 상태 변화 없음 -> 라우터가 history 로 보냄


def history_node(state: TransactionState) -> dict:
    """2차 HISTORY 매칭. 같은 테넌트의 가장 최근 APPROVED 이력 1건."""
    db = state["db_session"]
    payload = state["payload"]
    tenant = state["tenant"]

    history = find_recent_approved_history(db, payload, tenant)
    if history is not None:
        return {
            "match_type": "HISTORY",
            "category_code": "HISTORY_MATCH",
            "result_category": history.approved_category,
            "applied_rule_id": None,
        }
    return {}


def llm_node(state: TransactionState) -> dict:
    """3차 LLM 추론. 실패 시 최종 NONE/UNCLASSIFIED 로 그래프를 닫는다."""
    payload = state["payload"]
    llm_recommender = state["llm_recommender"]

    rec = llm_recommender.recommend(payload)
    if rec is not None:
        return {
            "match_type": "LLM",
            "category_code": rec.category_code,
            "result_category": rec.result_category,
            "applied_rule_id": None,
        }
    return {
        "match_type": "NONE",
        "category_code": "UNCLASSIFIED",
        "result_category": "미분류",
        "applied_rule_id": None,
    }


# ---------------------------------------------------------------------------- #
# Routers (conditional edges)
# ---------------------------------------------------------------------------- #
def _route_after_rule(state: TransactionState) -> str:
    return "end" if state.get("match_type") == "RULE" else "history"


def _route_after_history(state: TransactionState) -> str:
    return "end" if state.get("match_type") == "HISTORY" else "llm"


# ---------------------------------------------------------------------------- #
# Compile
# ---------------------------------------------------------------------------- #
def compile_recommendation_graph():
    """추천 파이프라인 StateGraph 를 조립·컴파일하여 반환."""
    workflow = StateGraph(TransactionState)
    workflow.add_node("rule", rule_node)
    workflow.add_node("history", history_node)
    workflow.add_node("llm", llm_node)

    workflow.add_edge(START, "rule")
    workflow.add_conditional_edges(
        "rule",
        _route_after_rule,
        {"history": "history", "end": END},
    )
    workflow.add_conditional_edges(
        "history",
        _route_after_history,
        {"llm": "llm", "end": END},
    )
    workflow.add_edge("llm", END)

    return workflow.compile()


@lru_cache(maxsize=1)
def get_recommendation_graph():
    """프로세스 단위 1회 컴파일 캐싱. 매 요청마다 재컴파일하지 않는다."""
    return compile_recommendation_graph()
