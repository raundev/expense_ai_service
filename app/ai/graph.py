"""영수증 용도 추천 + 컴플라이언스 파이프라인의 LangGraph StateGraph 정의 (10→12단계).

10단계의 추천 그래프(RULE→HISTORY→LLM)에, 11단계 RAG 엔진을 재활용하는
컴플라이언스 검증 노드를 결합한다(12단계). 용도 분류에 **성공한** 영수증은
END 로 바로 가지 않고 반드시 `compliance` 노드를 거쳐, 사칙 위배 여부를 판정한다.

      START
        │
        ▼
      ┌──────┐  RULE 매칭     ┌────────────┐
      │ rule │ ────────────► │            │
      └──┬───┘                │            │
         │ miss               │            │
         ▼                    │            │
      ┌─────────┐ HISTORY 매칭 │ compliance │ ──► END
      │ history │ ───────────►│            │
      └────┬────┘             │            │
           │ miss             │            │
           ▼                  │            │
        ┌──────┐  LLM 매칭     └────────────┘
        │ llm  │ ─────────────►   ▲
        └──┬───┘                  │
           │ NONE(분류 실패)        │
           └──────────────────► END  (compliance 생략)
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
from app.services.policy_service import PolicyService
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
        policy_service  : RAG 컴플라이언스 판정기 (DI -> 테스트 시 fake 임베딩 주입)

    Outputs (노드가 채워 넣음. 그래프 종료 시 match_type 은 반드시 채워져 있음):
        match_type, category_code, result_category, applied_rule_id
        is_compliant, violation_reason, explanation_status  (compliance 노드 경유 시)
    """

    # Inputs
    payload: SingleTransactionTestRequest
    tenant: TenantContext
    db_session: Session
    llm_recommender: ReceiptLLMRecommender
    policy_service: PolicyService

    # Outputs
    match_type: MatchType
    category_code: str
    result_category: str
    applied_rule_id: int | None

    # Compliance outputs (compliance_node 가 채움)
    is_compliant: bool
    violation_reason: str | None
    explanation_status: str | None


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


def compliance_node(state: TransactionState) -> dict:
    """4차 COMPLIANCE 검증. 분류된 용도가 현재 테넌트의 사칙에 위배되는지 판정.

    11단계 RAG 엔진(`PolicyService.check_compliance`)을 재활용한다. 위반이면
    PRD 요구사항에 따라 `explanation_status` 를 무조건 '미요청' 으로 자동 초기화하여
    소명 워크플로우의 시작점으로 만든다. 준수면 violation 관련 필드는 비운다.
    """
    result_category = state.get("result_category")
    # 분류 결과가 없으면(이론상 NONE 은 여기까지 안 오지만) 방어적으로 판정 생략.
    if not result_category:
        return {}

    policy_service = state["policy_service"]
    verdict = policy_service.check_compliance(
        payload=state["payload"],
        category_name=result_category,
        tenant=state["tenant"],
    )

    if verdict["is_compliant"]:
        return {"is_compliant": True, "violation_reason": None}

    # [중요] 위반 확정 -> 사유 기록 + 소명 상태를 '미요청' 으로 자동 초기화 (PRD).
    return {
        "is_compliant": False,
        "violation_reason": verdict["reason"],
        "explanation_status": "미요청",
    }


# ---------------------------------------------------------------------------- #
# Routers (conditional edges)
# ---------------------------------------------------------------------------- #
def _route_after_rule(state: TransactionState) -> str:
    # 매칭 성공 시 바로 END 가 아니라 compliance 를 거친다.
    return "compliance" if state.get("match_type") == "RULE" else "history"


def _route_after_history(state: TransactionState) -> str:
    return "compliance" if state.get("match_type") == "HISTORY" else "llm"


def _route_after_llm(state: TransactionState) -> str:
    # LLM 매칭 성공 -> compliance, 분류 실패(NONE) -> compliance 생략하고 END.
    return "compliance" if state.get("match_type") == "LLM" else "end"


# ---------------------------------------------------------------------------- #
# Compile
# ---------------------------------------------------------------------------- #
def compile_recommendation_graph():
    """추천 + 컴플라이언스 파이프라인 StateGraph 를 조립·컴파일하여 반환."""
    workflow = StateGraph(TransactionState)
    workflow.add_node("rule", rule_node)
    workflow.add_node("history", history_node)
    workflow.add_node("llm", llm_node)
    workflow.add_node("compliance", compliance_node)

    workflow.add_edge(START, "rule")
    workflow.add_conditional_edges(
        "rule",
        _route_after_rule,
        {"history": "history", "compliance": "compliance"},
    )
    workflow.add_conditional_edges(
        "history",
        _route_after_history,
        {"llm": "llm", "compliance": "compliance"},
    )
    workflow.add_conditional_edges(
        "llm",
        _route_after_llm,
        {"compliance": "compliance", "end": END},
    )
    # 분류에 성공한 모든 경로는 compliance 를 거친 뒤 종료한다.
    workflow.add_edge("compliance", END)

    return workflow.compile()


@lru_cache(maxsize=1)
def get_recommendation_graph():
    """프로세스 단위 1회 컴파일 캐싱. 매 요청마다 재컴파일하지 않는다."""
    return compile_recommendation_graph()
