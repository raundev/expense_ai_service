"""관리자용 운영 엔드포인트 — [tag: Admin API].

Soft Delete 물리 정리 워커 수동/배치 트리거. 테넌트 비종속(전체 DELETING 대상)이므로
멀티테넌트 헤더를 요구하지 않는다(시스템 운영 작업).

⚠️ 운영 보안: 실서비스에서는 내부망/관리자 인증으로 보호해야 한다(현재는 데모/배치용 무인증).
"""
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.common import ApiResponse
from app.services.cleanup_service import run_cleanup

router = APIRouter()


@router.post(
    "/cleanup",
    response_model=ApiResponse[dict],
    summary="Soft Delete 물리 정리 워커 수동 실행 (벡터→파일→행)",
)
def trigger_cleanup(
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[dict]:
    """`status`/`embedding_status == "DELETING"` 인 봇·문서를 물리 삭제한다(멱등).

    문서: Qdrant 벡터 → 파일 → RDB 행. 봇: 잔여 문서 0건일 때 RDB 행(cascade).
    실패 항목은 DELETING 으로 남아 다음 호출에서 재시도된다.
    """
    result = run_cleanup(db)
    return ApiResponse.ok(result, message="cleanup 실행 완료")
