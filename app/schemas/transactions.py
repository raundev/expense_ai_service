from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# 규칙 엔진(RULE) 외에 향후 단계에서 채워질 매칭 출처들.
#   * HISTORY : 과거 승인 내역 기반 Few-shot 추론
#   * LLM     : LangChain 에이전트의 LLM 추론
#   * NONE    : 어떤 방법으로도 분류 실패 → 사용자 수동 분류 필요
MatchType = Literal["RULE", "HISTORY", "LLM", "NONE"]


class SingleTransactionTestRequest(BaseModel):
    """단건 영수증 추천 요청.

    초기 구현이므로 카드 정보, 사용자 정보 등은 포함하지 않는다.
    """

    receipt_date: date = Field(..., description="영수증 일자")
    receipt_time: str = Field(..., description="HH:MM 또는 HH 형식 (예: '12:30', '19')")
    merchant_name: str = Field(..., description="가맹점명")
    merchant_sector_code: str | None = Field(default=None, description="가맹점 업종 코드")
    amount: int = Field(..., description="금액(원)")


class RecommendResponse(BaseModel):
    """추천 결과."""

    category_code: str = Field(..., description="용도 코드")
    result_category: str = Field(..., description="용도명")
    applied_rule_id: int | None = Field(default=None, description="매칭된 ReceiptRule.id (RULE 일 때만)")
    match_type: MatchType = Field(..., description="매칭 출처: RULE/HISTORY/LLM/NONE")


# ---------------------------------------------------------------------------- #
# Batch upload DTOs
# ---------------------------------------------------------------------------- #
class TransactionRowDTO(SingleTransactionTestRequest):
    """배치 업로드 시 개별 영수증 1건 (단건 추천 요청과 동일 스키마).

    향후 행 단위 메타(외부 거래 ID, 카드사 등)가 늘어나면 여기에 확장한다.
    """

    pass


class TransactionBatchUploadRequest(BaseModel):
    """다건 영수증 일괄 업로드 요청."""

    file_name: str = Field(..., description="원본 파일명(예: 'May_card_statement.xlsx')")
    transactions: list[TransactionRowDTO] = Field(
        ..., description="업로드할 영수증 행 리스트"
    )


class TransactionUploadSummaryResponse(BaseModel):
    """일괄 업로드 결과 요약.

    `success_count` 는 추천 엔진이 의미 있는 분류를 만든 행 수
    (match_type != 'NONE'). 사용자 보정이 필요한 미분류 건수는
    `total_count - success_count` 로 계산한다.
    """

    file_id: int = Field(..., description="생성된 ReceiptFile.id")
    total_count: int = Field(..., description="요청에 포함된 전체 영수증 수")
    success_count: int = Field(..., description="match_type != 'NONE' 인 행 수")


# ---------------------------------------------------------------------------- #
# Read / Update / Summary DTOs (9단계)
# ---------------------------------------------------------------------------- #
class TransactionResultResponse(BaseModel):
    """개별 트랜잭션 조회 응답. ORM 모델(ReceiptTransaction) → 자동 변환."""

    id: int
    file_id: int
    receipt_date: date
    receipt_time: str
    merchant_name: str
    merchant_sector_code: str | None = None
    amount: int
    recommended_category_code: str
    recommended_result_category: str
    applied_rule_id: int | None = None
    match_type: MatchType
    is_manually_modified: bool

    model_config = ConfigDict(from_attributes=True)


class TransactionManualUpdateRow(BaseModel):
    """수동 교정할 단건 데이터."""

    transaction_id: int = Field(..., description="대상 ReceiptTransaction.id")
    category_code: str = Field(..., max_length=64, description="새 용도 코드")
    result_category: str = Field(..., max_length=255, description="새 용도명")


class TransactionManualUpdateRequest(BaseModel):
    """수동 교정 일괄 요청. 한 파일 내의 여러 행을 atomic 으로 갱신한다."""

    rows: list[TransactionManualUpdateRow] = Field(..., min_length=1)


class FileClassifySummaryDTO(BaseModel):
    """회사별 파일 요약."""

    file_id: int = Field(..., description="ReceiptFile.id")
    file_name: str
    upload_time: datetime
    total_count: int

    model_config = ConfigDict(from_attributes=True)
