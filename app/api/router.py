from fastapi import APIRouter

from app.api.endpoints import (
    admin,
    bots,
    chat,
    compliance,
    documents,
    policies,
    rules,
    transactions,
)

api_router = APIRouter()
api_router.include_router(rules.router, prefix="/v1/rules", tags=["Rule API"])
api_router.include_router(transactions.router, prefix="/v1/transactions", tags=["Transaction API"])
# --- Policy RAG API (chat·bots·recommend) — 설계 §7 ---
api_router.include_router(bots.router, prefix="/v1/bots", tags=["Policy RAG API"])
# chat 은 설계 경로(/v1/policies/chat*)를 유지하되 파일은 분리. policies(ingest)와 동일 prefix
# 공유(서브경로 /chat vs /ingest 로 충돌 없음).
api_router.include_router(chat.router, prefix="/v1/policies", tags=["Policy RAG API"])
api_router.include_router(policies.router, prefix="/v1/policies", tags=["Policy RAG API"])
# --- Common Documents API (도메인 비종속) — 설계 §7 ---
api_router.include_router(documents.router, prefix="/v1/documents", tags=["Documents API"])
api_router.include_router(compliance.router, prefix="/compliance", tags=["Compliance Admin API"])
# --- 운영(Soft Delete 물리 정리 워커 트리거) — 설계 §4.3 ---
api_router.include_router(admin.router, prefix="/admin", tags=["Admin API"])
