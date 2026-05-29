from typing import Annotated

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.core.dependencies import TenantContext, get_tenant_info


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        debug=settings.DEBUG,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health", tags=["system"])
    async def health_check(
        tenant: Annotated[TenantContext, Depends(get_tenant_info)],
    ) -> dict:
        """헬스체크. 테넌트 헤더가 정상 주입되는지 함께 확인한다."""
        return {
            "status": "ok",
            "app": settings.APP_NAME,
            "environment": settings.ENVIRONMENT,
            "tenant": {
                "company_id": tenant.company_id,
                "workplace_id": tenant.workplace_id,
            },
        }

    # 도메인 라우터 등록
    app.include_router(api_router, prefix=settings.API_PREFIX)

    return app


app = create_app()
