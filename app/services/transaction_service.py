from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.graph import get_recommendation_graph
from app.ai.llm_recommender import ReceiptLLMRecommender
from app.core.dependencies import TenantContext
from app.models.transactions import ReceiptFile, ReceiptTransaction
from app.schemas.transactions import (
    RecommendResponse,
    SingleTransactionTestRequest,
    TransactionBatchUploadRequest,
    TransactionManualUpdateRequest,
    TransactionUploadSummaryResponse,
)
from app.services.rule_service import RuleService


# ---------------------------------------------------------------------------- #
# Domain exceptions
# ---------------------------------------------------------------------------- #
class ReceiptFileNotFoundError(Exception):
    """대상 파일이 존재하지 않거나, 요청 테넌트의 소유가 아닐 때 발생.

    보안상 '존재하지만 권한 없음' 과 '존재하지 않음' 을 분리하지 않는다.
    """

    def __init__(self, file_id: int) -> None:
        self.file_id = file_id
        super().__init__(f"ReceiptFile {file_id} not found")


class TenantMismatchError(Exception):
    """URL 의 corp_no 와 헤더의 tenant.company_id 가 일치하지 않을 때 발생.

    리소스 URL 과 인증 컨텍스트가 다르면 명백한 권한 위반 -> 403 으로 매핑.
    """

    def __init__(self, requested: str, actual: str) -> None:
        self.requested = requested
        self.actual = actual
        super().__init__(
            f"corp_no '{requested}' does not match tenant company_id '{actual}'"
        )

# ---------------------------------------------------------------------------- #
# Service
# ---------------------------------------------------------------------------- #
class TransactionService:
    """단건 영수증 추천(Transaction) 도메인 서비스."""

    def __init__(
        self,
        db: Session,
        llm_recommender: ReceiptLLMRecommender | None = None,
    ) -> None:
        self.db = db
        self.rule_service = RuleService(db)
        # 테스트/대체 구현 주입이 가능하도록 DI 형태. 기본은 LangChain 기반 구현.
        # TODO: 매 요청 인스턴스화 비용 부담 시 모듈 싱글톤(lru_cache)으로 캐싱.
        self.llm_recommender = (
            llm_recommender if llm_recommender is not None else ReceiptLLMRecommender()
        )

    def recommend_single_receipt(
        self,
        payload: SingleTransactionTestRequest,
        tenant: TenantContext,
    ) -> RecommendResponse:
        """RULE -> HISTORY -> LLM -> NONE 다단 추천을 LangGraph 에 위임 (10단계).

        그래프는 `app.ai.graph.get_recommendation_graph()` 가 프로세스 단위
        1회 컴파일·캐싱하므로, 매 요청마다 새로 만들지 않는다. 외부 응답 스펙
        (RecommendResponse 의 4개 필드)은 9단계까지와 완전히 동일하다.
        """
        graph = get_recommendation_graph()
        final_state = graph.invoke(
            {
                "payload": payload,
                "tenant": tenant,
                "db_session": self.db,
                "llm_recommender": self.llm_recommender,
            }
        )
        return RecommendResponse(
            category_code=final_state["category_code"],
            result_category=final_state["result_category"],
            applied_rule_id=final_state.get("applied_rule_id"),
            match_type=final_state["match_type"],
        )

    # ------------------------------------------------------------------ #
    # Batch upload
    # ------------------------------------------------------------------ #
    def process_batch_transactions(
        self,
        payload: TransactionBatchUploadRequest,
        tenant: TenantContext,
    ) -> TransactionUploadSummaryResponse:
        """다건 영수증 일괄 처리.

        흐름:
            1) `ReceiptFile` 레코드 생성 + flush 로 file.id 확보.
            2) 각 row 에 대해 기존 `recommend_single_receipt` 로 분류 결과 산출.
            3) 모든 결과를 `ReceiptTransaction` 객체 리스트로 모아 `add_all` 일괄 저장.
            4) commit 후 요약 반환.

        성능 메모: 행 수가 매우 많아지면 LLM/HISTORY 단계가 행마다 호출되어
        N x latency 가 누적된다. 추후 단계에서는 1차 RULE 평가를 배치화하고
        LLM 호출을 모아 한번에 보내는 최적화가 필요.
        """
        receipt_file = ReceiptFile(
            company_id=tenant.company_id,
            workplace_id=tenant.workplace_id,
            file_name=payload.file_name,
            total_count=len(payload.transactions),
        )
        self.db.add(receipt_file)
        self.db.flush()  # PK 확보용. commit 은 마지막에 한꺼번에.

        rows: list[ReceiptTransaction] = []
        success_count = 0
        for tx in payload.transactions:
            result = self.recommend_single_receipt(tx, tenant)
            if result.match_type != "NONE":
                success_count += 1

            rows.append(
                ReceiptTransaction(
                    file_id=receipt_file.id,
                    company_id=tenant.company_id,
                    workplace_id=tenant.workplace_id,
                    receipt_date=tx.receipt_date,
                    receipt_time=tx.receipt_time,
                    merchant_name=tx.merchant_name,
                    merchant_sector_code=tx.merchant_sector_code,
                    amount=tx.amount,
                    recommended_category_code=result.category_code,
                    recommended_result_category=result.result_category,
                    applied_rule_id=result.applied_rule_id,
                    match_type=result.match_type,
                    is_manually_modified=False,
                )
            )

        self.db.add_all(rows)
        self.db.commit()

        return TransactionUploadSummaryResponse(
            file_id=receipt_file.id,
            total_count=len(payload.transactions),
            success_count=success_count,
        )

    # ------------------------------------------------------------------ #
    # Read / Update / Summary (9단계)
    # ------------------------------------------------------------------ #
    def get_transactions_by_file(
        self,
        file_id: int,
        tenant: TenantContext,
    ) -> list[ReceiptTransaction]:
        """파일 단위 트랜잭션 목록 조회.

        파일 자체가 테넌트(company_id + workplace_id) 소유인지 먼저 검증한 뒤,
        같은 조건의 자식 트랜잭션만 반환. 다른 테넌트 파일 ID 를 넣으면 404 처리.
        """
        if self._find_owned_file(file_id, tenant) is None:
            raise ReceiptFileNotFoundError(file_id)

        stmt = (
            select(ReceiptTransaction)
            .where(
                ReceiptTransaction.file_id == file_id,
                ReceiptTransaction.company_id == tenant.company_id,
                ReceiptTransaction.workplace_id == tenant.workplace_id,
            )
            .order_by(ReceiptTransaction.id)
        )
        return list(self.db.execute(stmt).scalars().all())

    def update_transactions_manually(
        self,
        file_id: int,
        payload: TransactionManualUpdateRequest,
        tenant: TenantContext,
    ) -> list[ReceiptTransaction]:
        """수동 교정 일괄 적용 (atomic).

        - 파일 자체 소유권 검증.
        - 요청 row 들이 모두 같은 파일 + 같은 테넌트 소속인지 일괄 확인.
            * 하나라도 검증 실패 시 어떤 행도 수정하지 않고 404 반환.
        - 통과 시 category_code / result_category 덮어쓰고 is_manually_modified=True.
        """
        if self._find_owned_file(file_id, tenant) is None:
            raise ReceiptFileNotFoundError(file_id)

        tx_ids = [row.transaction_id for row in payload.rows]
        stmt = select(ReceiptTransaction).where(
            ReceiptTransaction.id.in_(tx_ids),
            ReceiptTransaction.file_id == file_id,
            ReceiptTransaction.company_id == tenant.company_id,
            ReceiptTransaction.workplace_id == tenant.workplace_id,
        )
        found_by_id = {tx.id: tx for tx in self.db.execute(stmt).scalars().all()}

        # 하나라도 못 찾으면 전체 거부 -- 다른 테넌트/다른 파일의 행 ID 가 섞여 있어도
        # 노이즈 부분 적용을 피하기 위함.
        missing = [tid for tid in tx_ids if tid not in found_by_id]
        if missing:
            raise ReceiptFileNotFoundError(file_id)

        updated_in_order: list[ReceiptTransaction] = []
        for row in payload.rows:
            tx = found_by_id[row.transaction_id]
            tx.recommended_category_code = row.category_code
            tx.recommended_result_category = row.result_category
            tx.is_manually_modified = True
            updated_in_order.append(tx)

        self.db.commit()
        for tx in updated_in_order:
            self.db.refresh(tx)
        return updated_in_order

    def get_company_classify_summaries(
        self,
        corp_no: str,
        tenant: TenantContext,
    ) -> list[ReceiptFile]:
        """회사 단위 파일 요약 목록.

        보안: URL 의 corp_no 와 헤더 tenant.company_id 가 일치하지 않으면
        TenantMismatchError(=403). 같은 회사 내 모든 workplace 의 파일을 포함한다.
        """
        if corp_no != tenant.company_id:
            raise TenantMismatchError(requested=corp_no, actual=tenant.company_id)

        stmt = (
            select(ReceiptFile)
            .where(ReceiptFile.company_id == corp_no)
            .order_by(ReceiptFile.upload_time.desc(), ReceiptFile.id.desc())
        )
        return list(self.db.execute(stmt).scalars().all())

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #
    def _find_owned_file(
        self,
        file_id: int,
        tenant: TenantContext,
    ) -> ReceiptFile | None:
        """현재 테넌트(company_id + workplace_id) 소유 파일이면 반환, 아니면 None."""
        stmt = select(ReceiptFile).where(
            ReceiptFile.id == file_id,
            ReceiptFile.company_id == tenant.company_id,
            ReceiptFile.workplace_id == tenant.workplace_id,
        )
        return self.db.execute(stmt).scalar_one_or_none()

    # HISTORY 매칭 로직은 LangGraph 의 `history_node` 가 직접 호출하는
    # `app.services.matchers.find_recent_approved_history` 로 이전됨 (10단계).
