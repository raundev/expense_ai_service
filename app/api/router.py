from fastapi import APIRouter, Depends

from app.api.endpoints import (
    admin,
    bots,
    chat,
    compliance,
    documents,
    policies,
    rules,
    tenants,
    transactions,
)
from app.core.dependencies import require_registered_tenant

# 등록된 테넌트만 도메인 API 에 접근하도록 막는 게이트(설정 TENANT_ENFORCEMENT_MODE 로 제어).
# 모든 도메인 라우터의 라우트가 이미 X-Company-ID/X-Workplace-ID 를 요구하므로, 라우터 레벨에
# 얹어도 새 헤더를 강제하지 않는다. admin / tenants 라우터에는 적용하지 않는다
# (닭-달걀: 테넌트 등록·운영 자체가 막히면 안 됨).
_tenant_guard = [Depends(require_registered_tenant)]

api_router = APIRouter()
api_router.include_router(
    rules.router, prefix="/v1/rules", tags=["Rule API"], dependencies=_tenant_guard
)
api_router.include_router(
    transactions.router, prefix="/v1/transactions", tags=["Transaction API"], dependencies=_tenant_guard
)
# --- Policy RAG API (chat·bots·recommend) — 설계 §7 ---
api_router.include_router(
    bots.router, prefix="/v1/bots", tags=["Policy RAG API"], dependencies=_tenant_guard
)
# chat 은 설계 경로(/v1/policies/chat*)를 유지하되 파일은 분리. policies(ingest)와 동일 prefix
# 공유(서브경로 /chat vs /ingest 로 충돌 없음).
api_router.include_router(
    chat.router, prefix="/v1/policies", tags=["Policy RAG API"], dependencies=_tenant_guard
)
api_router.include_router(
    policies.router, prefix="/v1/policies", tags=["Policy RAG API"], dependencies=_tenant_guard
)
# --- Common Documents API (도메인 비종속) — 설계 §7 ---
api_router.include_router(
    documents.router, prefix="/v1/documents", tags=["Documents API"], dependencies=_tenant_guard
)
api_router.include_router(
    compliance.router, prefix="/compliance", tags=["Compliance Admin API"], dependencies=_tenant_guard
)
# --- 운영(Soft Delete 물리 정리 워커 트리거) — 설계 §4.3. 게이트 비적용(테넌트 비종속). ---
api_router.include_router(admin.router, prefix="/admin", tags=["Admin API"])
# --- 테넌트 화이트리스트 관리. 게이트 비적용(등록 자체가 막히면 안 됨). ---
api_router.include_router(tenants.router, prefix="/admin/tenants", tags=["Admin API"])
