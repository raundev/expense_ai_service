"""LangChain 기반 영수증 용도 추천기 (3차 fallback) -- 테넌트 인지 번호 선택 방식.

Rule(1차) / History(2차) 매칭이 모두 실패한 영수증에 대해, **그 테넌트의 규칙에서
추출한 용도 후보 목록**(없으면 전역 기본값 `DEFAULT_CATEGORIES`)을 번호로 제시하고
LLM 에게 그중 하나를 고르게 한다(자유 텍스트 생성이 아니라 '번호 선택').

설계 핵심:
    * 2-Field 분리: LLM 은 텍스트가 아니라 번호(`selection`)를 반환한다. 목록에 없으면
      `selection=0` 을 반환하며, 이때만 `suggested_code`/`suggested_name` 을 자유 제안한다.
    * 콜드스타트 통일: 규칙이 0개인 신규 테넌트도 자유 텍스트 모드로 분기하지 않고
      `DEFAULT_CATEGORIES` 를 주입받아 동일한 '번호 선택' 파서를 탄다(주입은 호출측 책임).

graceful-degrade: `OPENAI_API_KEY` 미설정 또는 LangChain 미설치 환경에서도 서비스 전체가
깨지지 않도록 `select()` 가 None 을 반환한다(상위 그래프가 NONE 으로 자연 폴스루).
"""
from __future__ import annotations

import logging
import os
from typing import NamedTuple, Optional

from pydantic import BaseModel, Field

from app.core.config import settings
from app.models.rules import ReceiptRule
from app.schemas.transactions import SingleTransactionTestRequest

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------- #
# 용도 후보 (LLM 에게 번호로 제시되는 한 줄)
# ---------------------------------------------------------------------------- #
class CategoryCandidate(NamedTuple):
    """LLM 번호 선택의 한 항목. `code`(영문 코드) + `name`(한글 용도명)."""

    code: str
    name: str


# 후보군 상한. 초과하면 호출측(rule_node)이 절단하고 경고 로그를 남긴다.
TOP_N_CANDIDATES = 30

# 콜드스타트(규칙 0개) 또는 후보 추출 실패 시 주입할 전역 기본 용도 8종.
# 자유 텍스트 모드로 분기하지 않고 이 목록으로 동일한 번호 선택 파서를 타게 한다.
DEFAULT_CATEGORIES: list[CategoryCandidate] = [
    CategoryCandidate("MEAL", "식대"),
    CategoryCandidate("TRANSPORT", "교통비"),
    CategoryCandidate("TRAVEL", "출장비"),
    CategoryCandidate("ENTERTAINMENT", "접대비"),
    CategoryCandidate("OFFICE_SUPPLIES", "사무용품비"),
    CategoryCandidate("COMMUNICATION", "통신비"),
    CategoryCandidate("EDUCATION", "교육훈련비"),
    CategoryCandidate("OTHERS", "기타"),
]


def collapse_rules_to_candidates(rules: list[ReceiptRule]) -> list[CategoryCandidate]:
    """활성 규칙 목록을 LLM 후보군으로 distinct-collapse + 정렬한다.

    * distinct 키: (category_code, result_category) 쌍. 같은 용도를 가리키는 여러 규칙은
      한 후보로 접는다(collapse). 코드가 같아도 표시명이 다르면 별개 후보로 본다.
    * 각 후보의 대표 우선순위 = 해당 후보를 만든 규칙들의 `priority` 중 최솟값(min_priority).
    * 최종 정렬: min_priority 오름차순(낮을수록 먼저). 동률은 최초 등장 순서를 유지한다
      (입력이 priority ASC 로 들어오므로 안정 정렬로 자연스러운 순서가 보존된다).

    상한 절단(Top-N)은 호출측(rule_node)의 책임이라 여기서는 자르지 않고 전량 반환한다.
    """
    min_priority: dict[CategoryCandidate, int] = {}
    for rule in rules:
        candidate = CategoryCandidate(code=rule.category_code, name=rule.result_category)
        if candidate not in min_priority or rule.priority < min_priority[candidate]:
            min_priority[candidate] = rule.priority

    # dict 는 삽입 순서를 보존하고 sorted 는 안정 정렬이므로 동률 시 최초 등장 순서 유지.
    return [c for c, _ in sorted(min_priority.items(), key=lambda kv: kv[1])]


# ---------------------------------------------------------------------------- #
# LLM 정형 출력 스키마 (번호 선택 + off-list 자유 제안)
# ---------------------------------------------------------------------------- #
class LLMSelection(BaseModel):
    """LLM 출력 파싱 모델. 텍스트가 아닌 '번호'를 받는다(2-Field 분리 구조)."""

    selection: int = Field(
        description="가장 적합한 용도의 번호. 일치하는 항목이 전혀 없으면 0을 반환하세요."
    )
    suggested_code: str | None = Field(
        default=None,
        description="selection이 0일 때만 LLM이 자유롭게 제안하는 영문 대문자 기반 용도 코드",
    )
    suggested_name: str | None = Field(
        default=None,
        description="selection이 0일 때만 LLM이 자유롭게 제안하는 한글 용도명",
    )


# ---------------------------------------------------------------------------- #
# 프롬프트 템플릿 (번호 선택 전용 -- 기존 자유 텍스트 분류 프롬프트는 폐기)
# ---------------------------------------------------------------------------- #
_SYSTEM_PROMPT = """당신은 한국 기업의 법인카드 사용 용도를 분류하는 회계 전문가입니다.
'사람' 메시지에는 영수증 정보와 번호가 매겨진 '용도 후보 목록'이 함께 주어집니다.
영수증에 가장 적합한 용도 후보의 '번호'를 골라 응답하세요.

응답 규칙:
- 후보 목록에서 가장 적합한 항목 하나의 번호를 selection 으로 반환합니다(1 이상의 정수).
- 후보 목록 어디에도 적합한 항목이 전혀 없을 때만 selection=0 을 반환합니다.
- selection 이 1 이상이면 suggested_code 와 suggested_name 은 반드시 비워 둡니다(null).
- selection=0 일 때만 suggested_code(영문 대문자·언더스코어)와 suggested_name(한글 용도명)을
  새로 제안합니다.
- 가맹점명, 금액, 시간, 업종 코드 등 모든 단서를 종합적으로 고려합니다.
- 반드시 주어진 후보 목록의 번호 체계 안에서만 선택합니다(목록에 없는 번호를 만들지 않습니다)."""

_HUMAN_TEMPLATE = """다음 영수증의 법인카드 사용 용도를 분류하세요.

[영수증 정보]
- 가맹점명: {merchant_name}
- 금액: {amount}원
- 일자: {receipt_date}
- 시간: {receipt_time}
- 업종 코드: {sector_code}

[용도 후보 목록]
{categories}"""


# ---------------------------------------------------------------------------- #
# Recommender
# ---------------------------------------------------------------------------- #
class ReceiptLLMRecommender:
    """LangChain 기반 영수증 용도 추천기(번호 선택 방식).

    동작 정책:
        * `OPENAI_API_KEY` 가 없으면 인스턴스는 비활성 상태가 되고 `select()` 가 None 반환.
        * `langchain-openai` / `langchain-core` 미설치 시에도 비활성 상태로만 떨어지고
          import 자체가 실패하지 않도록 LangChain 의존성은 `__init__` 내부에서 lazy import.
        * 실제 LLM 호출/파싱 도중 예외가 발생해도 None 반환(상위 그래프가 NONE 으로 자연 폴스루).
    """

    def __init__(self) -> None:
        self.chain = None  # type: ignore[assignment]

        if not settings.OPENAI_API_KEY:
            logger.info(
                "OPENAI_API_KEY 미설정 -- LLM 추천 비활성화 (select() 는 항상 None)"
            )
            return

        try:
            import httpx
            from langchain_core.prompts import ChatPromptTemplate
            from langchain_openai import ChatOpenAI
        except ImportError as exc:  # langchain 미설치 환경 대비
            logger.warning("LangChain 의존성 부재 -- LLM 추천 비활성화 (%s)", exc)
            return

        llm_kwargs: dict = {
            "api_key": settings.OPENAI_API_KEY,
            "base_url": settings.OPENAI_API_BASE,
            "model": settings.LLM_MODEL,
            "temperature": 0,
        }

        # httpx 는 SSL_CERT_FILE 환경변수를 자동으로 안 읽고 certifi 번들만 사용한다.
        # 사내 CA 가 있으면 명시적으로 verify=path 로 http_client 를 주입해서
        # 회사 SSL 인터셉션을 통과시킨다.
        ssl_cert = os.environ.get("SSL_CERT_FILE")
        if ssl_cert and os.path.isfile(ssl_cert):
            llm_kwargs["http_client"] = httpx.Client(
                verify=ssl_cert, timeout=settings.llm_http_timeout
            )
            logger.info("Custom http_client 주입 (SSL CA: %s)", ssl_cert)

        # 번호 선택은 with_structured_output 으로 받는다. RunPod Qwen 챗 모델이
        # 정형 출력을 지원하며(컴플라이언스 판정 경로에서 이미 사용 중), category 목록은
        # 호출마다 달라지므로 `{categories}` 자리표시자로 invoke 시점에 주입한다.
        structured_llm = ChatOpenAI(**llm_kwargs).with_structured_output(LLMSelection)
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", _SYSTEM_PROMPT),
                ("human", _HUMAN_TEMPLATE),
            ]
        )
        self.chain = prompt | structured_llm
        logger.info(
            "LLM Recommender 활성화 (model=%s, base_url=%s)",
            settings.LLM_MODEL,
            settings.OPENAI_API_BASE,
        )

    # ------------------------------------------------------------------ #
    def select(
        self,
        payload: SingleTransactionTestRequest,
        candidates: list[CategoryCandidate],
    ) -> Optional[LLMSelection]:
        """후보 목록을 번호로 제시하고 LLM 에게 하나를 고르게 한다. 비활성/실패 시 None.

        예외는 모두 None 으로 흡수한다 -- 추천 엔진은 fallback 체인의 일원이며,
        LLM 다운/네트워크 장애가 전체 API 를 죽이면 안 됨.
        """
        if self.chain is None:
            return None
        if not candidates:
            # 후보가 없으면 번호 선택이 무의미하다. 후보 주입(콜드스타트 DEFAULT_CATEGORIES)은
            # 호출측(llm_node) 책임이므로, 여기까지 빈 목록이 오면 방어적으로 None.
            return None

        catalog = "\n".join(
            f"{idx}. {c.name} ({c.code})" for idx, c in enumerate(candidates, start=1)
        )
        try:
            return self.chain.invoke(
                {
                    "merchant_name": payload.merchant_name,
                    "amount": payload.amount,
                    "receipt_date": str(payload.receipt_date),
                    "receipt_time": payload.receipt_time,
                    "sector_code": payload.merchant_sector_code or "(없음)",
                    "categories": catalog,
                }
            )
        except Exception as exc:  # noqa: BLE001 -- 의도된 광범위 캡처
            logger.exception("LLM 선택 호출/파싱 실패: %s", exc)
            return None
