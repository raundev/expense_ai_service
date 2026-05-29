from fastapi import APIRouter

from app.api.endpoints import rules, transactions

api_router = APIRouter()
api_router.include_router(rules.router, prefix="/v1/rules", tags=["Rule API"])
api_router.include_router(transactions.router, prefix="/v1/transactions", tags=["Transaction API"])
