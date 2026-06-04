from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.dependencies import TenantContext, get_tenant_info
from app.db.session import get_db
from app.schemas.transactions import (
    FileClassifySummaryDTO,
    RecommendResponse,
    SingleTransactionTestRequest,
    TransactionBatchUploadRequest,
    TransactionManualUpdateRequest,
    TransactionResultResponse,
    TransactionUploadSummaryResponse,
)
from app.services.transaction_service import (
    ReceiptFileNotFoundError,
    TenantMismatchError,
    TransactionService,
)

router = APIRouter()


def get_transaction_service(
    db: Annotated[Session, Depends(get_db)],
) -> TransactionService:
    """TransactionService 주입용 FastAPI Dependency.

    엔드포인트가 서비스를 직접 생성하지 않고 이 의존성을 거치게 하여,
    테스트에서 `app.dependency_overrides` 로 policy_service(가짜 임베딩) 를 주입한
    TransactionService 를 끼워 넣을 수 있는 이음새(seam)를 만든다(12단계 검증용).
    """
    return TransactionService(db)


# ---------------------------------------------------------------------------- #
# 단건 추천 (테스트)
# ---------------------------------------------------------------------------- #
@router.post(
    "/test-single-transaction/create",
    response_model=RecommendResponse,
    status_code=status.HTTP_200_OK,
    summary="단건 영수증 용도 추천 (테스트)",
)
def recommend_single_receipt(
    payload: SingleTransactionTestRequest,
    tenant: Annotated[TenantContext, Depends(get_tenant_info)],
    service: Annotated[TransactionService, Depends(get_transaction_service)],
) -> RecommendResponse:
    """영수증 한 건을 받아 `RULE → HISTORY → LLM` 다단 추천 + 컴플라이언스 검증을 수행한다.

    - **요청 헤더(필수)**: `X-Company-ID`, `X-Workplace-ID`
    - **입력**: 영수증 정보(가맹점/금액/일시/업종) + 선택 `department`(주부서)
    - **응답**: 분류 결과(`category_code`/`result_category`/`match_type`)와 컴플라이언스
      판정(`is_compliant`/`violation_reason`/`explanation_status`)을 함께 반환.
    - 단건 테스트용으로 DB 에 저장하지 않는다(영속화는 배치 업로드 경로 사용).
    """
    return service.recommend_single_receipt(payload, tenant)


# ---------------------------------------------------------------------------- #
# 다건 업로드
# ---------------------------------------------------------------------------- #
@router.post(
    "/transaction/batch",
    response_model=TransactionUploadSummaryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="영수증 다건 일괄 업로드 + 자동 추천",
)
def upload_batch_transactions(
    payload: TransactionBatchUploadRequest,
    tenant: Annotated[TenantContext, Depends(get_tenant_info)],
    service: Annotated[TransactionService, Depends(get_transaction_service)],
) -> TransactionUploadSummaryResponse:
    """수십~수백 건의 영수증을 한 번에 업로드한다.

    내부적으로 각 행에 대해 RULE → HISTORY → LLM → NONE 의 다단 추천 엔진을 돌리고,
    분류에 성공한 건은 컴플라이언스 검증까지 거쳐 결과를 `ReceiptTransaction` 에 적재한다.
    """
    return service.process_batch_transactions(payload, tenant)


# ---------------------------------------------------------------------------- #
# 파일 단위 트랜잭션 조회
# ---------------------------------------------------------------------------- #
@router.get(
    "/files/{file_id}/transactions",
    response_model=list[TransactionResultResponse],
    summary="파일별 분류된 영수증 내역 조회",
)
def get_transactions_in_file(
    file_id: int,
    tenant: Annotated[TenantContext, Depends(get_tenant_info)],
    service: Annotated[TransactionService, Depends(get_transaction_service)],
) -> list[TransactionResultResponse]:
    """업로드된 파일(`file_id`)의 모든 트랜잭션을 ID 오름차순으로 조회.

    파일이 다른 테넌트 소유이거나 존재하지 않으면 404. (정보 노출 방지를 위해
    '존재하지 않음' 과 '권한 없음' 을 같은 404 로 응답한다.)
    """
    try:
        rows = service.get_transactions_by_file(file_id, tenant)
    except ReceiptFileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    return [TransactionResultResponse.model_validate(tx) for tx in rows]


# ---------------------------------------------------------------------------- #
# 수동 교정
# ---------------------------------------------------------------------------- #
@router.put(
    "/files/{file_id}/rows",
    response_model=list[TransactionResultResponse],
    summary="자동 분류 결과 수동 교정 (일괄)",
)
def update_rows_manually(
    file_id: int,
    payload: TransactionManualUpdateRequest,
    tenant: Annotated[TenantContext, Depends(get_tenant_info)],
    service: Annotated[TransactionService, Depends(get_transaction_service)],
) -> list[TransactionResultResponse]:
    """한 파일 안의 여러 행을 한 번에 수동 교정한다 (atomic).

    각 행의 `category_code` / `result_category` 를 덮어쓰고 `is_manually_modified=True`
    로 마킹. 요청에 다른 테넌트/다른 파일의 transaction_id 가 섞여 있으면 전체 거부(404).
    """
    try:
        updated = service.update_transactions_manually(file_id, payload, tenant)
    except ReceiptFileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    return [TransactionResultResponse.model_validate(tx) for tx in updated]


# ---------------------------------------------------------------------------- #
# 회사별 분류 요약 리포트
# ---------------------------------------------------------------------------- #
@router.get(
    "/files/corp/{corp_no}/classify-summaries",
    response_model=list[FileClassifySummaryDTO],
    summary="회사별 분류 파일 요약 리포트",
)
def get_company_summaries(
    corp_no: str,
    tenant: Annotated[TenantContext, Depends(get_tenant_info)],
    service: Annotated[TransactionService, Depends(get_transaction_service)],
) -> list[FileClassifySummaryDTO]:
    """회사(`corp_no`) 단위의 업로드 파일 요약 목록.

    URL 의 `corp_no` 와 헤더의 `X-Company-ID` 가 다르면 403 Forbidden.
    같은 회사 내 모든 사업장(workplace)의 파일을 포함한다.
    """
    try:
        files = service.get_company_classify_summaries(corp_no, tenant)
    except TenantMismatchError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)
        ) from exc
    return [
        FileClassifySummaryDTO(
            file_id=f.id,
            file_name=f.file_name,
            upload_time=f.upload_time,
            total_count=f.total_count,
        )
        for f in files
    ]
