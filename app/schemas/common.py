"""공통 API 응답 래퍼 (ApiResponse).

⚠️ 도입 배경: 기존 코드베이스에는 응답 래퍼가 없었고(라우터들이 DTO 를 그대로 반환),
이 envelope 은 Policy RAG / Documents **신규 라우터용으로 새로 도입**한 컨벤션이다.
기존 라우터(rules/transactions/compliance/policies-ingest)는 종전 형태를 유지하므로,
전체 통일이 필요하면 별도 작업으로 retrofit 한다.

성공 응답만 이 래퍼로 감싼다. 에러는 앱 전체와 동일하게 HTTPException({detail})/전역
예외 핸들러를 사용한다(전역 에러 포맷 통일은 프론트 파싱 영향이 있어 별도 결정).
"""
from typing import Generic, Optional, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """표준 응답 envelope: `{ success, data, message, error }`."""

    success: bool = Field(True, description="요청 성공 여부")
    data: Optional[T] = Field(None, description="성공 시 페이로드")
    message: Optional[str] = Field(None, description="사람이 읽는 부가 메시지(선택)")
    error: Optional[str] = Field(None, description="실패 시 에러 코드/사유(선택)")

    @classmethod
    def ok(cls, data: Optional[T] = None, message: Optional[str] = None) -> "ApiResponse[T]":
        return cls(success=True, data=data, message=message)

    @classmethod
    def fail(cls, error: str, message: Optional[str] = None) -> "ApiResponse[T]":
        return cls(success=False, error=error, message=message)
