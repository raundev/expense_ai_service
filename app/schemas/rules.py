from pydantic import BaseModel, ConfigDict, Field


class RuleBase(BaseModel):
    """ReceiptRule 의 공통 입력 필드.

    id / company_id / workplace_id 는 시스템(테넌트 컨텍스트)에서 강제 주입되므로
    클라이언트 입력에서 제외한다.
    """

    rule_name: str = Field(..., max_length=255, description="규칙 이름")

    # --- 적용 조건 ---
    condition_keyword: str | None = Field(default=None, max_length=255)
    condition_min_amount: int | None = Field(default=None, ge=0)
    condition_max_amount: int | None = Field(default=None, ge=0)
    is_weekend: bool | None = None
    is_holiday: bool | None = None
    usage_time_band: str | None = Field(default=None, max_length=32, description="예: 'LUNCH', 'DINNER', '22-06'")
    card_company_code: str | None = Field(default=None, max_length=32)
    merchant_sector_code: str | None = Field(default=None, max_length=32)
    merchant_sector_name: str | None = Field(default=None, max_length=255)

    # --- 결과 ---
    category_code: str = Field(..., max_length=32, description="결과 카테고리 코드")
    result_category: str = Field(..., max_length=255, description="결과 카테고리 명")

    # --- 운영 ---
    priority: int = Field(default=0, description="낮을수록 우선 적용")
    is_active: bool = Field(default=True)


class RuleRequest(RuleBase):
    """규칙 생성 및 수정 요청 스키마.

    POST /create, PUT /update/{rule_id} 양쪽에서 동일하게 사용한다.
    id / company_id / workplace_id 는 포함하지 않으며, 시스템이 강제 주입한다.
    """

    pass


class RuleResponse(RuleBase):
    """규칙 조회 응답 스키마. ORM 모델 → Pydantic 자동 변환 지원."""

    id: int
    company_id: str
    workplace_id: str | None = None

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------- #
# Bulk(일괄) 등록 DTO
# ---------------------------------------------------------------------------- #
class RuleBulkCreateRequest(BaseModel):
    """규칙 일괄 등록 요청.

    신규 테넌트 온보딩/시드용. 거래(Transaction) 배치 업로드와 동일하게 한 번의
    요청으로 여러 규칙을 원자적(all-or-nothing)으로 등록한다.
    개별 항목은 단건 등록과 동일한 `RuleRequest` 스키마이며, company_id/workplace_id
    는 헤더(TenantContext)에서 강제 주입되므로 Body 에서 받지 않는다.
    """

    rules: list[RuleRequest] = Field(
        ..., min_length=1, description="등록할 규칙 목록(최소 1건)"
    )


class RuleBulkCreateResponse(BaseModel):
    """규칙 일괄 등록 결과.

    `created_count` 는 실제 생성된 규칙 수이며, `rules` 는 생성된 규칙 전체를
    (DB 가 채운 id 포함) 입력 순서대로 돌려준다.
    """

    created_count: int = Field(..., description="생성된 규칙 수")
    rules: list[RuleResponse] = Field(..., description="생성된 규칙 목록(id 포함)")
