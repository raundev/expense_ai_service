from fastapi import APIRouter

from app.api.endpoints import compliance, policies, rules, transactions

api_router = APIRouter()
api_router.include_router(rules.router, prefix="/v1/rules", tags=["Rule API"])
api_router.include_router(transactions.router, prefix="/v1/transactions", tags=["Transaction API"])
api_router.include_router(policies.router, prefix="/v1/policies", tags=["Policy RAG API"])
api_router.include_router(compliance.router, prefix="/compliance", tags=["Compliance Admin API"])
