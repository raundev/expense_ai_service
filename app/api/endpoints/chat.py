"""Policy RAG 챗봇 — Chat API 라우터 (설계 §5.1) — [tag: Policy RAG API].

경로는 설계대로 `/api/v1/policies/chat*` 를 유지하되, 파일은 policies.py 와 분리한다
(chat 로직은 chat_service 로 이관). 모든 응답은 ApiResponse 로 감싼다.

- POST /chat                       : RAG 채팅(메인) — bot_id 필수(§5.1)
- GET  /chat/history/{session_id}  : 세션 히스토리
- GET  /chat/models                : 사용 가능 LLM 모델 목록
"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.dependencies import TenantContext, get_tenant_info
from app.db.session import get_db
from app.schemas.chat import ChatHistoryResponse, ChatModelsResponse
from app.schemas.common import ApiResponse
from app.schemas.policies import PolicyChatRequest, PolicyChatResponse
from app.services.bot_service import BotDisabledError, BotNotFoundError
from app.services.chat_service import ChatService, ChatSessionNotFoundError

router = APIRouter()


def get_chat_service(db: Annotated[Session, Depends(get_db)]) -> ChatService:
    """ChatService 주입용 의존성 (테스트에서 dependency_overrides 로 교체 가능)."""
    return ChatService(db)


# ---------------------------------------------------------------------------- #
# POST /chat  — RAG 채팅 (메인)
# ---------------------------------------------------------------------------- #
@router.post(
    "/chat",
    response_model=ApiResponse[PolicyChatResponse],
    summary="사내 규정 RAG 채팅 (bot_id 필수, 테넌트 격리)",
)
def chat(
    payload: PolicyChatRequest,
    tenant: Annotated[TenantContext, Depends(get_tenant_info)],
    service: Annotated[ChatService, Depends(get_chat_service)],
) -> ApiResponse[PolicyChatResponse]:
    """봇 검증(404/409) → 세션 조회·생성 → (Phase C: RAG 파이프라인) → 답변/세션/출처 반환."""
    try:
        result = service.chat(tenant, payload)
    except BotNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except BotDisabledError as exc:
        # 비활성 봇으로의 chat 은 409 (설계 §1)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ChatSessionNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return ApiResponse.ok(PolicyChatResponse(**result))


# ---------------------------------------------------------------------------- #
# GET /chat/history/{session_id}  — 세션 히스토리
# ---------------------------------------------------------------------------- #
@router.get(
    "/chat/history/{session_id}",
    response_model=ApiResponse[ChatHistoryResponse],
    summary="대화 세션 히스토리 조회 (테넌트 격리)",
)
def get_chat_history(
    session_id: str,
    tenant: Annotated[TenantContext, Depends(get_tenant_info)],
    service: Annotated[ChatService, Depends(get_chat_service)],
) -> ApiResponse[ChatHistoryResponse]:
    try:
        history = service.get_history(tenant, session_id)
    except ChatSessionNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return ApiResponse.ok(history)


# ---------------------------------------------------------------------------- #
# GET /chat/models  — 사용 가능 LLM 모델 목록
# ---------------------------------------------------------------------------- #
@router.get(
    "/chat/models",
    response_model=ApiResponse[ChatModelsResponse],
    summary="사용 가능 LLM 모델 목록",
)
def get_chat_models(
    tenant: Annotated[TenantContext, Depends(get_tenant_info)],
    service: Annotated[ChatService, Depends(get_chat_service)],
) -> ApiResponse[ChatModelsResponse]:
    return ApiResponse.ok(ChatModelsResponse(models=service.get_available_models()))
