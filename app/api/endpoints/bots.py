"""Policy RAG 챗봇 — Bots API 라우터 (설계 §6.1) — [tag: Policy RAG API].

봇 CRUD / 활성화·비활성화 / Soft Delete / 통계 / 세션 / 추천질문. 모든 응답은 ApiResponse
로 감싼다. 모든 요청은 X-Company-ID/X-Workplace-ID 로 테넌트 격리(불일치 404).
"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.dependencies import TenantContext, get_tenant_info
from app.db.session import get_db
from app.schemas.bots import (
    BotCreateRequest,
    BotDailyStatisticsResponse,
    BotResponse,
    BotStatisticsResponse,
    BotUpdateRequest,
    RecommendedQuestionResponse,
)
from app.schemas.chat import BotSessionSummary
from app.schemas.common import ApiResponse
from app.services.bot_service import (
    BotNameConflictError,
    BotNotFoundError,
    BotService,
)

router = APIRouter()


def get_bot_service(db: Annotated[Session, Depends(get_db)]) -> BotService:
    """BotService 주입용 의존성 (테스트에서 dependency_overrides 로 교체 가능)."""
    return BotService(db)


# ---------------------------------------------------------------------------- #
# POST /  — 봇 생성 (생성 직후 비활성)
# ---------------------------------------------------------------------------- #
@router.post(
    "",
    response_model=ApiResponse[BotResponse],
    status_code=status.HTTP_201_CREATED,
    summary="봇 생성 (생성 직후 disabled=true)",
)
def create_bot(
    payload: BotCreateRequest,
    tenant: Annotated[TenantContext, Depends(get_tenant_info)],
    service: Annotated[BotService, Depends(get_bot_service)],
) -> ApiResponse[BotResponse]:
    try:
        bot = service.create_bot(payload, tenant)
    except BotNameConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return ApiResponse.ok(BotResponse.model_validate(bot))


# ---------------------------------------------------------------------------- #
# GET /  — 봇 목록 (name ASC)
# ---------------------------------------------------------------------------- #
@router.get(
    "",
    response_model=ApiResponse[list[BotResponse]],
    summary="테넌트 봇 목록 조회",
)
def list_bots(
    tenant: Annotated[TenantContext, Depends(get_tenant_info)],
    service: Annotated[BotService, Depends(get_bot_service)],
) -> ApiResponse[list[BotResponse]]:
    bots = service.list_bots(tenant)
    return ApiResponse.ok([BotResponse.model_validate(b) for b in bots])


# ---------------------------------------------------------------------------- #
# GET /{bot_id}  — 단건 조회
# ---------------------------------------------------------------------------- #
@router.get(
    "/{bot_id}",
    response_model=ApiResponse[BotResponse],
    summary="봇 단건 조회",
)
def get_bot(
    bot_id: str,
    tenant: Annotated[TenantContext, Depends(get_tenant_info)],
    service: Annotated[BotService, Depends(get_bot_service)],
) -> ApiResponse[BotResponse]:
    try:
        bot = service.get_bot(bot_id, tenant)
    except BotNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return ApiResponse.ok(BotResponse.model_validate(bot))


# ---------------------------------------------------------------------------- #
# PUT /{bot_id}  — 설정 수정 (PATCH 시맨틱)
# ---------------------------------------------------------------------------- #
@router.put(
    "/{bot_id}",
    response_model=ApiResponse[BotResponse],
    summary="봇 설정 수정 (전달된 필드만 갱신)",
)
def update_bot(
    bot_id: str,
    payload: BotUpdateRequest,
    tenant: Annotated[TenantContext, Depends(get_tenant_info)],
    service: Annotated[BotService, Depends(get_bot_service)],
) -> ApiResponse[BotResponse]:
    try:
        bot = service.update_bot(bot_id, payload, tenant)
    except BotNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except BotNameConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return ApiResponse.ok(BotResponse.model_validate(bot))


# ---------------------------------------------------------------------------- #
# PATCH /{bot_id}/enable · /disable  — 활성화/비활성화
# ---------------------------------------------------------------------------- #
@router.patch(
    "/{bot_id}/enable",
    response_model=ApiResponse[BotResponse],
    summary="봇 활성화",
)
def enable_bot(
    bot_id: str,
    tenant: Annotated[TenantContext, Depends(get_tenant_info)],
    service: Annotated[BotService, Depends(get_bot_service)],
) -> ApiResponse[BotResponse]:
    try:
        bot = service.set_disabled(bot_id, tenant, disabled=False)
    except BotNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return ApiResponse.ok(BotResponse.model_validate(bot))


@router.patch(
    "/{bot_id}/disable",
    response_model=ApiResponse[BotResponse],
    summary="봇 비활성화",
)
def disable_bot(
    bot_id: str,
    tenant: Annotated[TenantContext, Depends(get_tenant_info)],
    service: Annotated[BotService, Depends(get_bot_service)],
) -> ApiResponse[BotResponse]:
    try:
        bot = service.set_disabled(bot_id, tenant, disabled=True)
    except BotNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return ApiResponse.ok(BotResponse.model_validate(bot))


# ---------------------------------------------------------------------------- #
# DELETE /{bot_id}  — Soft Delete (status=DELETING)
# ---------------------------------------------------------------------------- #
@router.delete(
    "/{bot_id}",
    response_model=ApiResponse[BotResponse],
    summary="봇 Soft Delete (status=DELETING — 워커가 물리 정리)",
)
def delete_bot(
    bot_id: str,
    tenant: Annotated[TenantContext, Depends(get_tenant_info)],
    service: Annotated[BotService, Depends(get_bot_service)],
) -> ApiResponse[BotResponse]:
    """실제 DB 삭제를 하지 않고 status="DELETING" 으로만 전이한다(즉시 조회/chat 제외)."""
    try:
        bot = service.soft_delete_bot(bot_id, tenant)
    except BotNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return ApiResponse.ok(
        BotResponse.model_validate(bot), message="삭제 예약됨(DELETING). 물리 정리는 워커가 수행합니다."
    )


# ---------------------------------------------------------------------------- #
# GET /{bot_id}/statistics · /statistics/daily  — 통계
# ---------------------------------------------------------------------------- #
@router.get(
    "/{bot_id}/statistics",
    response_model=ApiResponse[BotStatisticsResponse],
    summary="봇 통계 (문서/세션/메시지/토큰)",
)
def get_bot_statistics(
    bot_id: str,
    tenant: Annotated[TenantContext, Depends(get_tenant_info)],
    service: Annotated[BotService, Depends(get_bot_service)],
) -> ApiResponse[BotStatisticsResponse]:
    try:
        stats = service.get_statistics(bot_id, tenant)
    except BotNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return ApiResponse.ok(BotStatisticsResponse(**stats))


@router.get(
    "/{bot_id}/statistics/daily",
    response_model=ApiResponse[BotDailyStatisticsResponse],
    summary="봇 일별 통계 (최근 N일 세션 수)",
)
def get_bot_daily_statistics(
    bot_id: str,
    tenant: Annotated[TenantContext, Depends(get_tenant_info)],
    service: Annotated[BotService, Depends(get_bot_service)],
    window_days: Annotated[int, Query(ge=1, le=90, description="집계 일수(1~90)")] = 7,
) -> ApiResponse[BotDailyStatisticsResponse]:
    try:
        stats = service.get_daily_statistics(bot_id, tenant, window_days=window_days)
    except BotNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return ApiResponse.ok(BotDailyStatisticsResponse(**stats))


# ---------------------------------------------------------------------------- #
# GET /{bot_id}/sessions  — 봇 세션 목록
# ---------------------------------------------------------------------------- #
@router.get(
    "/{bot_id}/sessions",
    response_model=ApiResponse[list[BotSessionSummary]],
    summary="봇 세션 목록 조회",
)
def list_bot_sessions(
    bot_id: str,
    tenant: Annotated[TenantContext, Depends(get_tenant_info)],
    service: Annotated[BotService, Depends(get_bot_service)],
) -> ApiResponse[list[BotSessionSummary]]:
    try:
        sessions = service.list_sessions(bot_id, tenant)
    except BotNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return ApiResponse.ok([BotSessionSummary.model_validate(s) for s in sessions])


# ---------------------------------------------------------------------------- #
# GET /{bot_id}/recommend  — 추천 질문 목록 (조회 전용)
# ---------------------------------------------------------------------------- #
@router.get(
    "/{bot_id}/recommend",
    response_model=ApiResponse[list[RecommendedQuestionResponse]],
    summary="봇 추천 질문 목록 (sort_order ASC)",
)
def get_bot_recommend(
    bot_id: str,
    tenant: Annotated[TenantContext, Depends(get_tenant_info)],
    service: Annotated[BotService, Depends(get_bot_service)],
) -> ApiResponse[list[RecommendedQuestionResponse]]:
    try:
        questions = service.get_recommended_questions(bot_id, tenant)
    except BotNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return ApiResponse.ok([RecommendedQuestionResponse.model_validate(q) for q in questions])
