"""관리자용 컴플라이언스 감사 API 스키마 (13단계, PRD '5. 기능 요구사항').

대시보드 KPI 집계와 소명(해명) 워크플로우 요청/처리 페이로드를 정의한다.
explanation_status 의 4가지 값('미요청'/'요청완료'/'정상처리'/'위반확정')을 축으로
관리자가 위반 영수증의 소명 절차를 진행한다.
"""
from typing import Literal

from pydantic import BaseModel, Field


class DashboardKpiResponse(BaseModel):
    """컴플라이언스 대시보드 KPI 집계 응답.

    `total_detected` 는 위반 탐지(is_compliant=False) 총건수이며, 나머지 4개는
    소명 상태(explanation_status)별 분포다. 정상 흐름에서는
    total_detected == not_requested + requested + normal_processed + violation_confirmed.
    """

    total_detected: int = Field(..., description="전체 위반 탐지 건수 (is_compliant=False)")
    not_requested: int = Field(..., description="소명 미요청 건수 ('미요청')")
    requested: int = Field(..., description="소명 요청완료 건수 ('요청완료')")
    normal_processed: int = Field(..., description="정상처리 건수 ('정상처리')")
    violation_confirmed: int = Field(..., description="위반확정 건수 ('위반확정')")


class ExplanationRequestPayload(BaseModel):
    """소명 요청 페이로드. 관리자가 위반 건들에 대해 사용자에게 해명을 요청한다."""

    transaction_ids: list[int] = Field(
        ..., min_length=1, description="소명을 요청할 ReceiptTransaction ID 목록"
    )
    request_message: str = Field(
        ..., min_length=1, description="사용자에게 전달할 소명 요청 메시지"
    )


class ExplanationProcessPayload(BaseModel):
    """소명 처리 페이로드. 관리자가 소명을 검토해 정상처리/위반확정으로 종결한다."""

    transaction_ids: list[int] = Field(
        ..., min_length=1, description="처리할 ReceiptTransaction ID 목록"
    )
    status: Literal["정상처리", "위반확정"] = Field(
        ..., description="처리 결과 상태 ('정상처리' 또는 '위반확정')"
    )
    process_comment: str | None = Field(default=None, description="처리 코멘트(선택)")
