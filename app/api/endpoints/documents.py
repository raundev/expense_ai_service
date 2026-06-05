"""공통 Documents API 라우터 (설계 §4.1) — [tag: Documents API].

Critical Design Rule #2: 파라미터는 범용 `owner_id`+`domain` 만 사용(bot_id 미노출).
Critical Design Rule #4: DELETE 는 Soft Delete(status="DELETING")만 수행.
Critical Design Rule #5: 모든 요청은 X-Company-ID/X-Workplace-ID 로 테넌트 격리.

성공 응답은 ApiResponse 로 감싼다. 다운로드만 바이너리 스트림이라 FileResponse 로 예외.
"""
from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.dependencies import TenantContext, get_tenant_info
from app.db.session import get_db
from app.schemas.common import ApiResponse
from app.schemas.documents import DocumentIngestTextRequest, DocumentResponse
from app.services.document_service import (
    DocumentNotFoundError,
    DocumentService,
    process_document_embedding,
)

router = APIRouter()


def get_document_service(
    db: Annotated[Session, Depends(get_db)],
) -> DocumentService:
    """DocumentService 주입용 의존성 (테스트에서 dependency_overrides 로 교체 가능)."""
    return DocumentService(db)


# ---------------------------------------------------------------------------- #
# GET /  — 문서 목록 (테넌트 + 선택 domain/owner_id 필터)
# ---------------------------------------------------------------------------- #
@router.get(
    "",
    response_model=ApiResponse[list[DocumentResponse]],
    summary="문서 목록 조회 (테넌트 격리, DELETING 제외)",
)
def list_documents(
    tenant: Annotated[TenantContext, Depends(get_tenant_info)],
    service: Annotated[DocumentService, Depends(get_document_service)],
    domain: Annotated[str | None, Query(description='문서 도메인 필터(예: "policy", "expense_rule")')] = None,
    owner_id: Annotated[str | None, Query(description="소유 주체(범용) 필터")] = None,
) -> ApiResponse[list[DocumentResponse]]:
    docs = service.list_documents(tenant, domain=domain, owner_id=owner_id)
    return ApiResponse.ok([DocumentResponse.model_validate(d) for d in docs])


# ---------------------------------------------------------------------------- #
# POST /upload  — 파일 업로드(비동기 임베딩 예약)
# ---------------------------------------------------------------------------- #
@router.post(
    "/upload",
    response_model=ApiResponse[DocumentResponse],
    status_code=status.HTTP_201_CREATED,
    summary="문서 파일 업로드 (비동기 임베딩, status=PROCESSING)",
)
def upload_document(
    tenant: Annotated[TenantContext, Depends(get_tenant_info)],
    service: Annotated[DocumentService, Depends(get_document_service)],
    background_tasks: BackgroundTasks,
    file: Annotated[UploadFile, File(description="업로드 파일")],
    title: Annotated[str, Form(description="문서 제목")],
    owner_id: Annotated[str | None, Form(description="소유 주체(범용). policy 도메인은 봇 UUID.")] = None,
    domain: Annotated[str, Form(description='문서 도메인(기본 "policy")')] = "policy",
    is_compliance_source: Annotated[bool, Form(description="컴플라이언스 근거 문서 여부")] = False,
) -> ApiResponse[DocumentResponse]:
    """파일을 테넌트 격리 경로에 저장하고 문서 행을 생성(PROCESSING)한 뒤 즉시 201 반환.

    실제 임베딩은 BackgroundTasks 로 예약된다(Phase B 에서 구현).
    """
    doc = service.create_from_upload(
        tenant,
        file=file,
        title=title,
        owner_id=owner_id,
        domain=domain,
        is_compliance_source=is_compliance_source,
    )
    background_tasks.add_task(process_document_embedding, doc.id)
    return ApiResponse.ok(DocumentResponse.model_validate(doc))


# ---------------------------------------------------------------------------- #
# POST /ingest-text  — 텍스트 즉시 적재
# ---------------------------------------------------------------------------- #
@router.post(
    "/ingest-text",
    response_model=ApiResponse[DocumentResponse],
    status_code=status.HTTP_201_CREATED,
    summary="텍스트 즉시 적재 (동기)",
)
def ingest_text(
    payload: DocumentIngestTextRequest,
    tenant: Annotated[TenantContext, Depends(get_tenant_info)],
    service: Annotated[DocumentService, Depends(get_document_service)],
) -> ApiResponse[DocumentResponse]:
    doc = service.ingest_text(tenant, payload)
    return ApiResponse.ok(DocumentResponse.model_validate(doc))


# ---------------------------------------------------------------------------- #
# GET /{doc_id}  — 단건 메타/상태
# ---------------------------------------------------------------------------- #
@router.get(
    "/{doc_id}",
    response_model=ApiResponse[DocumentResponse],
    summary="문서 단건 메타/상태 조회",
)
def get_document(
    doc_id: str,
    tenant: Annotated[TenantContext, Depends(get_tenant_info)],
    service: Annotated[DocumentService, Depends(get_document_service)],
) -> ApiResponse[DocumentResponse]:
    try:
        doc = service.get_document(doc_id, tenant)
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return ApiResponse.ok(DocumentResponse.model_validate(doc))


# ---------------------------------------------------------------------------- #
# GET /{doc_id}/download  — 원본 파일 다운로드 (바이너리 — ApiResponse 예외)
# ---------------------------------------------------------------------------- #
@router.get(
    "/{doc_id}/download",
    summary="원본 파일 다운로드",
)
def download_document(
    doc_id: str,
    tenant: Annotated[TenantContext, Depends(get_tenant_info)],
    service: Annotated[DocumentService, Depends(get_document_service)],
) -> FileResponse:
    try:
        doc = service.get_for_download(doc_id, tenant)
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return FileResponse(
        path=doc.file_path,
        filename=doc.file_name or doc.id,
        media_type=doc.content_type or "application/octet-stream",
    )


# ---------------------------------------------------------------------------- #
# DELETE /{doc_id}  — Soft Delete (status=DELETING)
# ---------------------------------------------------------------------------- #
@router.delete(
    "/{doc_id}",
    response_model=ApiResponse[DocumentResponse],
    summary="문서 Soft Delete (status=DELETING — 워커가 물리 정리)",
)
def delete_document(
    doc_id: str,
    tenant: Annotated[TenantContext, Depends(get_tenant_info)],
    service: Annotated[DocumentService, Depends(get_document_service)],
) -> ApiResponse[DocumentResponse]:
    """실제 DB 삭제를 하지 않고 status="DELETING" 으로만 전이한다(즉시 조회/검색 제외)."""
    try:
        doc = service.soft_delete(doc_id, tenant)
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return ApiResponse.ok(
        DocumentResponse.model_validate(doc), message="삭제 예약됨(DELETING). 물리 정리는 워커가 수행합니다."
    )
