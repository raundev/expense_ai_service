"""LangChain 기반 영수증 용도 추천기 (3차 fallback).

Rule(1차) / History(2차) 매칭이 모두 실패한 영수증에 대해 LLM 에게 상식적인
용도 분류를 요청한다. OPENAI_API_KEY 미설정 또는 LangChain 미설치 환경에서도
서비스 전체가 깨지지 않도록 `recommend()` 가 None 을 반환하는 graceful-degrade
구조로 작성한다.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from pydantic import BaseModel, Field

from app.core.config import settings
from app.schemas.transactions import SingleTransactionTestRequest

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------- #
# LLM 정형 출력 스키마
# ---------------------------------------------------------------------------- #
class LLMRecommendation(BaseModel):
    """LLM 추론 결과 (PydanticOutputParser 로 자동 파싱)."""

    category_code: str = Field(
        ...,
        description=(
            "영문 대문자와 언더스코어만 사용하는 카테고리 코드. "
            "예: MEAL, TRAVEL, IT_SUBSCRIPTION, OFFICE_SUPPLIES, "
            "ENTERTAINMENT, COMMUNICATION, EDUCATION, OTHERS"
        ),
    )
    result_category: str = Field(
        ...,
        description=(
            "한국 회계 실무에서 통용되는 한글 비용명. "
            "예: 식대, 출장/숙박비, IT구독료, 사무용품비, 접대비, "
            "통신비, 교육훈련비, 도서인쇄비, 기타"
        ),
    )


# ---------------------------------------------------------------------------- #
# 프롬프트 템플릿
# ---------------------------------------------------------------------------- #
_SYSTEM_PROMPT = """당신은 한국 기업의 법인카드 사용 용도를 분류하는 회계 전문가입니다.
입력된 영수증 정보를 보고 가장 적절한 비용 분류 카테고리 한 가지를 선택해 정확히 응답하세요.

응답 규칙:
- category_code 는 영문 대문자와 언더스코어(_)만 사용합니다.
- result_category 는 한국 회계 실무에서 흔히 쓰는 한글 비용명을 사용합니다.
- 가맹점명, 금액, 시간, 업종 등 모든 단서를 종합적으로 고려합니다.
- 정보가 불완전하더라도 가장 그럴듯한 카테고리 하나를 반드시 응답합니다."""

_HUMAN_TEMPLATE = """다음 영수증의 가장 적절한 법인카드 사용 용도를 분류하세요.

- 가맹점명: {merchant_name}
- 금액: {amount}원
- 일자: {receipt_date}
- 시간: {receipt_time}
- 업종 코드: {sector_code}

{format_instructions}"""


# ---------------------------------------------------------------------------- #
# Recommender
# ---------------------------------------------------------------------------- #
class ReceiptLLMRecommender:
    """LangChain 기반 영수증 용도 추천기.

    동작 정책:
        * `OPENAI_API_KEY` 가 없으면 인스턴스는 비활성 상태가 되고 `recommend()` 가 None 반환.
        * `langchain-openai` / `langchain-core` 미설치 시에도 비활성 상태로만 떨어지고
          import 자체가 실패하지 않도록 LangChain 의존성은 `__init__` 내부에서 lazy import.
        * 실제 LLM 호출/파싱 도중 예외가 발생해도 None 반환 (상위 서비스가 NONE 으로 자연 폴스루).
    """

    def __init__(self) -> None:
        self.chain = None  # type: ignore[assignment]

        if not settings.OPENAI_API_KEY:
            logger.info(
                "OPENAI_API_KEY 미설정 -- LLM 추천 비활성화 (recommend() 는 항상 None)"
            )
            return

        try:
            import httpx
            from langchain_core.output_parsers import PydanticOutputParser
            from langchain_core.prompts import ChatPromptTemplate
            from langchain_openai import ChatOpenAI
        except ImportError as exc:  # langchain 미설치 환경 대비
            logger.warning("LangChain 의존성 부재 -- LLM 추천 비활성화 (%s)", exc)
            return

        parser = PydanticOutputParser(pydantic_object=LLMRecommendation)

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

        llm = ChatOpenAI(**llm_kwargs)
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", _SYSTEM_PROMPT),
                ("human", _HUMAN_TEMPLATE),
            ]
        ).partial(format_instructions=parser.get_format_instructions())

        self.chain = prompt | llm | parser
        logger.info(
            "LLM Recommender 활성화 (model=%s, base_url=%s)",
            settings.LLM_MODEL,
            settings.OPENAI_API_BASE,
        )

    # ------------------------------------------------------------------ #
    def recommend(
        self,
        payload: SingleTransactionTestRequest,
    ) -> Optional[LLMRecommendation]:
        """영수증 데이터를 LLM 에 던져 카테고리를 추론. 비활성/실패 시 None.

        예외는 모두 None 으로 흡수한다 -- 추천 엔진은 fallback 체인의 일원이며,
        LLM 다운/네트워크 장애가 전체 API 를 죽이면 안 됨.
        """
        if self.chain is None:
            return None
        try:
            return self.chain.invoke(
                {
                    "merchant_name": payload.merchant_name,
                    "amount": payload.amount,
                    "receipt_date": str(payload.receipt_date),
                    "receipt_time": payload.receipt_time,
                    "sector_code": payload.merchant_sector_code or "(없음)",
                }
            )
        except Exception as exc:  # noqa: BLE001 -- 의도된 광범위 캡처
            logger.exception("LLM 호출/파싱 실패: %s", exc)
            return None
