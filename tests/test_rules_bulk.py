"""규칙 일괄 등록(POST /api/v1/rules/bulk) 통합/서비스 테스트.

검증 포인트:
    * 여러 규칙을 한 번에 등록하고 created_count + id 부여 결과를 돌려준다.
    * company_id/workplace_id 는 Body 가 아니라 헤더(TenantContext)로 강제된다(격리).
    * 빈 배열은 422(min_length=1).
    * 등록 후 활성 규칙 목록 조회에 일괄분이 모두 노출된다.
    * 원자성: 하나라도 검증 실패면 전체가 들어가지 않는다.
"""
from app.core.dependencies import TenantContext
from app.models.rules import ReceiptRule
from app.schemas.rules import RuleRequest
from app.services.rule_service import RuleService

HEADERS = {"X-Company-ID": "COMPANY_A", "X-Workplace-ID": "HQ"}
RULES = "/api/v1/rules"


def _payload(n: int) -> dict:
    return {
        "rules": [
            {
                "rule_name": f"규칙{i}",
                "condition_keyword": f"키워드{i}",
                "category_code": "MEAL",
                "result_category": "식대",
                "priority": i,
            }
            for i in range(n)
        ]
    }


# ---------------------------------------------------------------------------- #
# 서비스 레이어
# ---------------------------------------------------------------------------- #
def test_create_rules_bulk_injects_tenant_and_returns_ids(db_session):
    tenant = TenantContext(company_id="C1", workplace_id="W1")
    payloads = [
        RuleRequest(rule_name="식대", category_code="MEAL", result_category="식대"),
        RuleRequest(rule_name="교통", category_code="TRANSPORT", result_category="교통비"),
    ]
    created = RuleService(db_session).create_rules_bulk(payloads, tenant)

    assert len(created) == 2
    assert all(r.id is not None for r in created)  # DB 가 PK 채움
    # 테넌트 식별자는 헤더 값으로 강제 주입(Body 에 없음).
    assert {r.company_id for r in created} == {"C1"}
    assert {r.workplace_id for r in created} == {"W1"}


# ---------------------------------------------------------------------------- #
# API 레이어
# ---------------------------------------------------------------------------- #
def test_bulk_endpoint_creates_and_lists(client, session_factory):
    r = client.post(f"{RULES}/bulk", headers=HEADERS, json=_payload(3))
    assert r.status_code == 201
    body = r.json()
    assert body["created_count"] == 3
    assert len(body["rules"]) == 3
    assert all(rule["id"] for rule in body["rules"])
    assert all(rule["company_id"] == "COMPANY_A" for rule in body["rules"])

    # 등록분이 활성 규칙 목록 조회에 모두 노출되어야 한다.
    listed = client.get(f"{RULES}/", headers=HEADERS)
    assert listed.status_code == 200
    assert len(listed.json()) == 3


def test_bulk_endpoint_rejects_empty(client):
    r = client.post(f"{RULES}/bulk", headers=HEADERS, json={"rules": []})
    assert r.status_code == 422  # min_length=1


def test_bulk_endpoint_isolates_by_header_tenant(client, session_factory):
    """Body 에 다른 회사 정보를 넣어도 무시되고 헤더 테넌트로만 등록된다."""
    payload = _payload(2)
    for rule in payload["rules"]:
        rule["company_id"] = "EVIL_CORP"  # 무시되어야 함(스키마에 없음)
        rule["workplace_id"] = "EVIL_WP"

    r = client.post(f"{RULES}/bulk", headers=HEADERS, json=payload)
    assert r.status_code == 201

    db = session_factory()
    try:
        rows = db.query(ReceiptRule).all()
        assert len(rows) == 2
        assert all(row.company_id == "COMPANY_A" for row in rows)
        assert all(row.workplace_id == "HQ" for row in rows)
    finally:
        db.close()


def test_bulk_is_atomic_on_validation_failure(client, session_factory):
    """한 항목이라도 검증 실패(필수 누락)면 422 + 어떤 행도 적재되지 않는다."""
    payload = _payload(2)
    del payload["rules"][1]["category_code"]  # 두 번째 항목 필수 필드 누락

    r = client.post(f"{RULES}/bulk", headers=HEADERS, json=payload)
    assert r.status_code == 422  # pydantic 검증 단계에서 전체 거부

    db = session_factory()
    try:
        assert db.query(ReceiptRule).count() == 0  # 부분 적재 없음
    finally:
        db.close()
