"""의도분류 + 검색어 재작성 (설계 §5.3).

- classify_intent: LLM 기반 RETRIEVE vs HISTORY_ONLY 분류(프롬프트 요구). 실패 시 안전하게
  RETRIEVE 로 폴백(환각 회피).
- needs_reformulation / looks_like_transform: 정규식 Tier-1 힌트(비용 절감).
- reformulate_query: 지시대명사 후속질문을 독립 검색어로 재작성(LLM 1콜).

Critical Design Rule #3 의 '첫 턴/출처없음 강제 RETRIEVE 폴백'은 세션 컨텍스트를 아는
chat_service 가 분류 결과 위에 적용한다(여기서는 순수 분류만 담당).
"""
from __future__ import annotations

import logging
import re
from enum import Enum

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class Intent(str, Enum):
    RETRIEVE = "RETRIEVE"
    HISTORY_ONLY = "HISTORY_ONLY"


# Tier-1 정규식: 순수 변환(번역/요약/단순화/형식변환) 키워드 — HISTORY_ONLY 후보 힌트.
_TRANSFORM_KEYWORDS = re.compile(
    r"(요약|간략|간단(히|하게)?|줄여|짧게|번역|translate|쉽게|풀어|다시\s*설명|"
    r"표로|정리해|개조식|bullet|한\s*문장|영어로|한국어로)",
    re.IGNORECASE,
)
# 지시대명사(후속질문) — 검색어 재작성 필요 힌트.
_ANAPHORA = re.compile(
    r"(그것|그거|이것|이거|위(의|에서|에)?\s|위 항목|아까|방금|그\s|저것|that|this|it|above|previous)",
    re.IGNORECASE,
)


class _IntentOut(BaseModel):
    """LLM 구조화 출력."""

    intent: str = Field(..., description='반드시 "RETRIEVE" 또는 "HISTORY_ONLY"')


_INTENT_SYSTEM = """당신은 사내 규정 챗봇의 질문 '의도'를 분류합니다.
- RETRIEVE: 새 정보·규정을 알아내려면 문서 검색이 필요한 질문.
- HISTORY_ONLY: 직전 대화 내용을 번역/요약/형식변환 등 '가공'만 하면 되는 질문(새 검색 불필요).
반드시 RETRIEVE 또는 HISTORY_ONLY 중 하나로만 분류하세요."""

_REFORMULATE_SYSTEM = """후속 질문을 이전 대화 맥락을 반영한 '독립적인 검색어'로 재작성하세요.
지시대명사(그거/위 항목/that 등)는 구체 명사로 치환하고, 변환 동사(요약/번역 등)는 제거해
핵심 주제어만 남기세요. 재작성된 검색어 한 줄만 출력하세요."""


def looks_like_transform(query: str) -> bool:
    """순수 변환(요약/번역 등) 키워드를 포함하는가(HISTORY_ONLY 후보 힌트)."""
    return bool(_TRANSFORM_KEYWORDS.search(query or ""))


def needs_reformulation(query: str) -> bool:
    """지시대명사가 있어 독립 검색어로의 재작성이 필요한가."""
    return bool(_ANAPHORA.search(query or ""))


def classify_intent(query: str, history_text: str, llm) -> Intent:
    """LLM 으로 RETRIEVE/HISTORY_ONLY 분류. 실패 시 안전하게 RETRIEVE(환각 회피).

    호출 측(chat_service)은 첫 턴(히스토리 없음)에는 이 함수를 부르지 않고 RETRIEVE 로 단락한다.
    """
    try:
        structured = llm.with_structured_output(_IntentOut)
        out = structured.invoke(
            [
                ("system", _INTENT_SYSTEM),
                (
                    "human",
                    f"이전 대화:\n{history_text}\n\n현재 질문: {query}\n\n"
                    "의도는 RETRIEVE 입니까, HISTORY_ONLY 입니까?",
                ),
            ]
        )
        value = str(getattr(out, "intent", "")).upper().strip()
        return Intent.HISTORY_ONLY if value == "HISTORY_ONLY" else Intent.RETRIEVE
    except Exception:  # noqa: BLE001 -- 분류 실패는 검색으로 폴백(누락보다 비용)
        logger.warning("의도분류 실패 -> RETRIEVE 폴백", exc_info=True)
        return Intent.RETRIEVE


def reformulate_query(query: str, history_text: str, llm) -> str:
    """지시어 후속질문을 독립 검색어로 재작성. 실패 시 원 질문 사용."""
    try:
        resp = llm.invoke(
            [
                ("system", _REFORMULATE_SYSTEM),
                ("human", f"이전 대화:\n{history_text}\n\n후속 질문: {query}\n\n검색어:"),
            ]
        )
        text = (getattr(resp, "content", "") or "").strip()
        return text or query
    except Exception:  # noqa: BLE001
        logger.warning("검색어 재작성 실패 -> 원 질문 사용", exc_info=True)
        return query
