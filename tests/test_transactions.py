"""영수증 추천 API 통합 테스트 (단건/배치 + DB 적재 + 컴플라이언스 결합)."""
from app.core.dependencies import TenantContext
from app.models.rules import ReceiptRule
from app.models.transactions import ReceiptTransaction

HEADERS = {"X-Company-ID": "COMPANY_A", "X-Workplace-ID": "HQ"}
TX = "/api/v1/transactions"


def _seed_meal_rule(session_factory):
    """'맥도날드' -> '식대' 분류 규칙 시드 (금액 조건 없음)."""
    db = session_factory()
    db.add(
        ReceiptRule(
            company_id="COMPANY_A",
            workplace_id="HQ",
            rule_name="식대 분류",
            condition_keyword="맥도날드",
            category_code="MEAL",
            result_category="식대",
            priority=0,
            is_active=True,
        )
    )
    db.commit()
    db.close()


def test_single_recommend_rule_match(client, session_factory):
    """단건 추천: Rule 매칭 + department 에코 + (정책 미적재 시) 준수 처리."""
    _seed_meal_rule(session_factory)
    r = client.post(
        f"{TX}/test-single-transaction/create",
        headers=HEADERS,
        json={
            "receipt_date": "2026-05-28",
            "receipt_time": "19:30",
            "merchant_name": "맥도날드",
            "amount": 9000,
            "department": "개발팀",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["match_type"] == "RULE"
    assert body["result_category"] == "식대"
    assert body["department"] == "개발팀"
    assert body["is_compliant"] is True  # 정책 미적재 -> 준수


def test_batch_upload_persists_to_db(client, session_factory):
    """배치 업로드: 201 + 파일 단위 조회 + DB 적재(부서 포함) 확인."""
    _seed_meal_rule(session_factory)
    r = client.post(
        f"{TX}/transaction/batch",
        headers=HEADERS,
        json={
            "file_name": "may.xlsx",
            "transactions": [
                {"receipt_date": "2026-05-28", "receipt_time": "12:30", "merchant_name": "맥도날드", "amount": 9000, "department": "개발팀"},
                {"receipt_date": "2026-05-28", "receipt_time": "13:00", "merchant_name": "스타벅스", "amount": 5000, "department": "영업팀"},
            ],
        },
    )
    assert r.status_code == 201
    summary = r.json()
    assert summary["total_count"] == 2
    file_id = summary["file_id"]

    # 응답(DB read + 직렬화) 확인
    g = client.get(f"{TX}/files/{file_id}/transactions", headers=HEADERS)
    assert g.status_code == 200
    rows = g.json()
    assert len(rows) == 2
    mcd = next(x for x in rows if x["merchant_name"] == "맥도날드")
    assert mcd["match_type"] == "RULE"
    assert mcd["recommended_result_category"] == "식대"
    assert mcd["department"] == "개발팀"

    # DB 직접 적재 확인
    db = session_factory()
    count = (
        db.query(ReceiptTransaction)
        .filter(ReceiptTransaction.file_id == file_id)
        .count()
    )
    db.close()
    assert count == 2


def test_batch_violation_sets_compliance(client, session_factory, mock_policy_service):
    """정책 적재 후 한도 초과 영수증 -> compliance_node 가 위반/미요청 으로 적재."""
    _seed_meal_rule(session_factory)
    mock_policy_service.ingest_policy_text(
        "우리 회사의 야근 식대 한도는 15,000원입니다.",
        "취업규칙",
        TenantContext(company_id="COMPANY_A", workplace_id="HQ"),
    )
    r = client.post(
        f"{TX}/transaction/batch",
        headers=HEADERS,
        json={
            "file_name": "viol.xlsx",
            "transactions": [
                {"receipt_date": "2026-05-28", "receipt_time": "19:30", "merchant_name": "맥도날드", "amount": 20000, "department": "개발팀"},
            ],
        },
    )
    assert r.status_code == 201
    file_id = r.json()["file_id"]
    row = client.get(f"{TX}/files/{file_id}/transactions", headers=HEADERS).json()[0]
    assert row["is_compliant"] is False
    assert "초과" in (row["violation_reason"] or "")
    assert row["explanation_status"] == "미요청"


def test_missing_tenant_header_422(client):
    """멀티테넌트 헤더 누락 시 422."""
    r = client.post(
        f"{TX}/test-single-transaction/create",
        json={"receipt_date": "2026-05-28", "receipt_time": "19:30", "merchant_name": "맥도날드", "amount": 9000},
    )
    assert r.status_code == 422
