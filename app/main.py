"""FastAPI 애플리케이션 부트스트랩 (15단계: 운영 준비).

- 풍부한 OpenAPI 메타데이터(/docs Swagger UI) 로 프론트엔드 연동성을 높인다.
- 전역 예외 처리기로 예기치 못한 오류를 규격화된 JSON 으로 응답한다(스택 노출 방지).
"""
import logging
from typing import Annotated

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.core.config import settings
from app.core.dependencies import TenantContext, get_tenant_info

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------- #
# OpenAPI 메타데이터
# ---------------------------------------------------------------------------- #
API_DESCRIPTION = """
영수증 **용도 자동 추천**과 **RAG 기반 사내 규정 컴플라이언스 감사**를 제공하는
멀티테넌트 백엔드 API 입니다.

### 멀티테넌트 인증 헤더 (필수)
모든 도메인 API 는 아래 헤더로 회사/사업장을 식별합니다. 누락 시 422 가 반환됩니다.
- `X-Company-ID` : 회사 식별자 (필수)
- `X-Workplace-ID` : 사업장 식별자 (필수)
- `X-Admin-ID` : 관리자 식별자 (컴플라이언스 소명 **요청/처리/취소** 시에만 필수, 감사 추적용)

### 핵심 파이프라인
1. **추천** : `RULE → HISTORY → LLM` 다단 분류 (LangGraph StateGraph)
2. **컴플라이언스** : 분류에 성공한 영수증은 RAG 로 사칙 위배 여부를 자동 판정하고,
   위반 시 소명(해명) 워크플로우(`미요청 → 요청완료 → 정상처리/위반확정`)를 시작합니다.
3. **감사** : 관리자 대시보드(KPI/차트), 위반 그리드 조회/엑셀 다운로드, 소명 요청·처리·취소

### 표준 에러 응답
예기치 못한 서버 오류는 아래 형식의 JSON 으로 반환됩니다(원시 스택은 노출되지 않습니다).
```json
{ "error_code": "INTERNAL_SERVER_ERROR", "message": "서버 내부 오류가 발생했습니다." }
```
"""

OPENAPI_TAGS = [
    {"name": "system", "description": "헬스체크 등 시스템 상태 점검 엔드포인트."},
    {
        "name": "Transaction API",
        "description": "영수증 용도 자동 추천 + 컴플라이언스 검증 파이프라인. 단건 추천/다건 배치 업로드, "
        "결과 조회·수동 교정·회사별 요약을 제공합니다.",
    },
    {"name": "Rule API", "description": "테넌트별 용도 분류 규칙(Rule Engine) 등록/수정/조회."},
    {
        "name": "Policy RAG API",
        "description": "Policy RAG 챗봇: 봇 관리(bots)·RAG 채팅(chat)·추천 질문(recommend). "
        "봇별 LLM 설정 오버라이드와 Qdrant Payload Filter 로 테넌트/봇 격리.",
    },
    {
        "name": "Documents API",
        "description": "공통(도메인 비종속) 문서 모듈: 업로드/텍스트 적재(비동기 임베딩)·목록·다운로드·Soft Delete. "
        "범용 owner_id+domain 으로 챗봇 외 주체(컴플라이언스 엔진 등)도 재사용.",
    },
    {
        "name": "Compliance Admin API",
        "description": "관리자용 컴플라이언스 감사: 대시보드 KPI/시각화 차트, 위반 그리드 조회/엑셀(CSV) 다운로드, "
        "소명 요청/처리/취소 워크플로우.",
    },
    {
        "name": "Admin API",
        "description": "운영용 엔드포인트. Soft Delete(status=DELETING) 봇·문서의 물리 정리 워커"
        "(벡터→파일→행) 수동/배치 트리거.",
    },
]


def create_app() -> FastAPI:
    app = FastAPI(
        title="Bizplay AI Compliance & Recommendation API",
        version="1.0.0",
        description=API_DESCRIPTION,
        openapi_tags=OPENAPI_TAGS,
        contact={"name": "Bizplay AI Backend", "email": "ai-backend@bizplay.co.kr"},
        # debug=False: 운영에서 예외 스택을 클라이언트에 노출하지 않고, 항상 아래 전역
        # 예외 처리기를 통해 규격화된 JSON 을 반환하도록 강제한다(스택은 서버 로그로만).
        debug=False,
    )

    # CORS: 프론트엔드 테스트 콘솔(Vercel/localhost)에서의 호출을 허용한다.
    # 테스트 단계에서는 모든 오리진을 허용한다(운영에서는 settings.cors_origins_list 로
    # 화이트리스트 제한 권장). allow_credentials=True 와 "*" 조합은 Starlette 가 요청
    # Origin 을 echo 하여 처리하므로, 헤더 기반(쿠키 미사용) 호출에서 CORS 에러가 없다.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ------------------------------------------------------------------ #
    # 전역 예외 처리기 (운영 레벨)
    # ------------------------------------------------------------------ #
    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        """예측하지 못한 모든 예외를 가로채 규격화된 500 JSON 으로 응답한다.

        FastAPI 의 HTTPException / RequestValidationError 는 각자의 핸들러가 먼저
        처리하므로 여기엔 '진짜 예기치 못한' 오류만 도달한다. 전체 스택은 서버 로그에만
        남기고 클라이언트에는 노출하지 않는다.
        """
        logger.exception(
            "Unhandled exception on %s %s", request.method, request.url.path
        )
        return JSONResponse(
            status_code=500,
            content={
                "error_code": "INTERNAL_SERVER_ERROR",
                "message": "서버 내부 오류가 발생했습니다.",
            },
        )

    @app.get("/health", tags=["system"], summary="헬스체크 (테넌트 헤더 점검 포함)")
    async def health_check(
        tenant: Annotated[TenantContext, Depends(get_tenant_info)],
    ) -> dict:
        """서비스 가동 상태와 테넌트 헤더(`X-Company-ID`/`X-Workplace-ID`) 주입을 함께 확인한다."""
        return {
            "status": "ok",
            "app": "Bizplay AI Compliance & Recommendation API",
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
