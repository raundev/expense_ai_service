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
