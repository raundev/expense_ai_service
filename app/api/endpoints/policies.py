"""Policy RAG — ingest 엔드포인트 (전환기 alias).

chat(/history/models)은 `endpoints/chat.py` 로 이관되었다(설계 §5, chat 로직은 chat_service).
본 파일은 한시적으로 `/ingest` 만 유지하며, 신규 적재는 공통 `/documents/ingest-text`
사용을 권장한다(설계 §9.3).
"""
from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.core.dependencies import TenantContext, get_tenant_info
from app.schemas.policies import PolicyIngestRequest, PolicyIngestResponse
from app.services.policy_service import PolicyService

router = APIRouter()


def get_policy_service() -> PolicyService:
    """PolicyService 주입용 FastAPI Dependency.

    엔드포인트가 서비스를 직접 생성하지 않고 이 의존성을 거치게 하여,
    테스트에서 `app.dependency_overrides` 로 in-memory 벡터스토어/대체 LLM 을
    주입할 수 있는 이음새(seam)를 만든다.
    """
    return PolicyService()


# ---------------------------------------------------------------------------- #
# POST /ingest  — 규정 텍스트 적재 (전환기 alias)
# ---------------------------------------------------------------------------- #
@router.post(
    "/ingest",
    response_model=PolicyIngestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="사내 규정 텍스트 적재 (테넌트 격리)",
)
def ingest_policy(
    payload: PolicyIngestRequest,
    tenant: Annotated[TenantContext, Depends(get_tenant_info)],
    service: Annotated[PolicyService, Depends(get_policy_service)],
) -> PolicyIngestResponse:
    """규정 원문을 청크로 분할해 벡터DB 에 적재한다.

    `company_id` / `workplace_id` 는 요청 헤더에서 자동 주입되어 각 청크 메타데이터에
    박힌다. 이후 chat 검색은 이 테넌트 키로만 매칭된다.
    """
    chunk_count = service.ingest_policy_text(
        text=payload.text,
        source_name=payload.source_name,
        tenant=tenant,
    )
    return PolicyIngestResponse(
        source_name=payload.source_name,
        chunk_count=chunk_count,
    )
