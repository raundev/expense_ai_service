"""관리자 컴플라이언스 워크플로우 API 통합 테스트 (KPI/차트/엑셀/소명 상태전이)."""
from datetime import date

import csv
import io

from app.models.transactions import ReceiptFile, ReceiptTransaction

HEADERS = {"X-Company-ID": "COMPANY_A", "X-Workplace-ID": "HQ"}
HEADERS_ADMIN = {**HEADERS, "X-Admin-ID": "admin_kim"}
C = "/api/compliance"


def _seed_violations(session_factory) -> dict:
    """회사A 위반 3건(+준수 1건) / 회사B 위반 1건 시드. 반환: 주요 트랜잭션 id."""
    db = session_factory()
    fa = ReceiptFile(company_id="COMPANY_A", workplace_id="HQ", file_name="a.xlsx", total_count=4)
    fb = ReceiptFile(company_id="COMPANY_B", workplace_id="HQ", file_name="b.xlsx", total_count=1)
    db.add_all([fa, fb])
    db.flush()

    def mk(file_id, company, dept, d, merchant, amount, *, compliant=False, employee="emp_kim"):
        return ReceiptTransaction(
            file_id=file_id,
            company_id=company,
            workplace_id="HQ",
            department=dept,
            employee_id=employee,
            receipt_date=d,
            receipt_time="19:30",
            merchant_name=merchant,
            amount=amount,
            recommended_category_code="MEAL",
            recommended_result_category="식대",
            applied_rule_id=None,
            match_type="RULE",
            is_manually_modified=False,
            is_compliant=compliant,
            violation_reason=None if compliant else "한도 15,000원 초과",
            explanation_status=None if compliant else "미요청",
        )

    rows = [
        mk(fa.id, "COMPANY_A", "개발팀", date(2026, 5, 26), "맥도날드", 20000, employee="emp_kim"),
        mk(fa.id, "COMPANY_A", "개발팀", date(2026, 5, 27), "스타벅스", 18000, employee="emp_kim"),
        mk(fa.id, "COMPANY_A", "영업팀", date(2026, 5, 27), "롯데리아", 25000, employee="emp_lee"),
        mk(fa.id, "COMPANY_A", "개발팀", date(2026, 5, 26), "김밥천국", 9000, compliant=True, employee="emp_kim"),
        mk(fb.id, "COMPANY_B", "개발팀", date(2026, 5, 28), "KFC", 30000, employee="emp_park"),
    ]
    db.add_all(rows)
    db.commit()
    ids = {"a_first": rows[0].id, "a_lee": rows[2].id, "b_first": rows[4].id}
    db.close()
    return ids


def test_dashboard_kpi(client, session_factory):
    _seed_violations(session_factory)
    k = client.get(f"{C}/dashboard/kpi", headers=HEADERS).json()
    assert k["total_detected"] == 3  # 준수/타테넌트 제외
    assert k["not_requested"] == 3
    assert k["requested"] == 0


def test_dashboard_charts_grouping(client, session_factory):
    _seed_violations(session_factory)
    charts = client.get(f"{C}/dashboard/charts", headers=HEADERS).json()
    trend = {p["date"]: p["count"] for p in charts["violation_trend"]}
    by_dept = {p["label"]: p["count"] for p in charts["violation_by_department"]}
    assert trend == {"2026-05-26": 1, "2026-05-27": 2}
    assert by_dept == {"개발팀": 2, "영업팀": 1}


def test_export_csv(client, session_factory):
    _seed_violations(session_factory)
    r = client.get(f"{C}/transactions/export", headers=HEADERS)
    assert r.status_code == 200
    assert "text/csv" in r.headers["content-type"]
    assert r.content.startswith(b"\xef\xbb\xbf")  # UTF-8 BOM
    parsed = list(csv.reader(io.StringIO(r.content.decode("utf-8-sig"))))
    assert "부서" in parsed[0]
    assert len(parsed) - 1 == 3  # 헤더 제외 위반 3건 (준수/타테넌트 제외)


def test_request_then_cancel_rollback(client, session_factory):
    ids = _seed_violations(session_factory)
    tid = ids["a_first"]

    # 소명 요청 -> '요청완료'
    r1 = client.post(
        f"{C}/transactions/request-explanation",
        headers=HEADERS_ADMIN,
        json={"transaction_ids": [tid], "request_message": "소명 바랍니다"},
    )
    assert r1.status_code == 200
    assert r1.json()[0]["explanation_status"] == "요청완료"

    # 취소 -> '미요청' 롤백 + 요청메타 초기화
    r2 = client.post(
        f"{C}/transactions/cancel-explanation",
        headers=HEADERS_ADMIN,
        json={"transaction_ids": [tid], "cancel_reason": "오탐 판단"},
    )
    assert r2.status_code == 200
    assert r2.json()[0]["explanation_status"] == "미요청"

    db = session_factory()
    row = db.get(ReceiptTransaction, tid)
    db.close()
    assert row.explanation_status == "미요청"
    assert row.explanation_requester is None
    assert row.explanation_request_dt is None

    # 이미 '미요청' 인 건 재취소 -> 409
    r3 = client.post(
        f"{C}/transactions/cancel-explanation",
        headers=HEADERS_ADMIN,
        json={"transaction_ids": [tid]},
    )
    assert r3.status_code == 409


def test_process_explanation(client, session_factory):
    ids = _seed_violations(session_factory)
    tid = ids["a_first"]
    # 상태 전이 가드: '미요청' 에서는 처리 불가 -> 먼저 요청완료로 만든다.
    client.post(
        f"{C}/transactions/request-explanation",
        headers=HEADERS_ADMIN,
        json={"transaction_ids": [tid], "request_message": "x"},
    )
    r = client.post(
        f"{C}/transactions/process-explanation",
        headers=HEADERS_ADMIN,
        json={"transaction_ids": [tid], "status": "위반확정", "process_comment": "확정"},
    )
    assert r.status_code == 200
    assert r.json()[0]["explanation_status"] == "위반확정"


def test_process_guard_rejects_not_requested(client, session_factory):
    """상태 전이 가드: '미요청'(요청 전) 건을 바로 처리하면 409."""
    ids = _seed_violations(session_factory)
    r = client.post(
        f"{C}/transactions/process-explanation",
        headers=HEADERS_ADMIN,
        json={"transaction_ids": [ids["a_first"]], "status": "위반확정"},
    )
    assert r.status_code == 409


# ---------------------------------------------------------------------------- #
# Phase 2 — 직원 직접 소명 제출 워크플로우 (17단계)
# ---------------------------------------------------------------------------- #
def _emp(employee_id: str) -> dict:
    return {**HEADERS, "X-Employee-ID": employee_id}


def test_employee_submit_e2e(client, session_factory):
    """E2E: 관리자 요청(+기한) -> 직원 본인 조회 -> 소명 제출 -> 관리자 위반확정."""
    ids = _seed_violations(session_factory)
    tid = ids["a_first"]  # emp_kim 의 맥도날드 위반

    # 0) 관리자 소명 요청 (+ due_date) -> 요청완료
    rq = client.post(
        f"{C}/transactions/request-explanation",
        headers=HEADERS_ADMIN,
        json={
            "transaction_ids": [tid],
            "request_message": "소명 바랍니다",
            "due_date": "2026-06-10T00:00:00",
        },
    )
    assert rq.status_code == 200

    # 1) 직원 본인 목록 조회 -> 본인(emp_kim) 위반만, 요청건 due_date 노출
    my = client.get(f"{C}/my/transactions", headers=_emp("emp_kim"))
    assert my.status_code == 200
    my_rows = my.json()
    assert all(x["employee_id"] == "emp_kim" for x in my_rows)
    target = next(x for x in my_rows if x["id"] == tid)
    assert target["explanation_status"] == "요청완료"
    assert target["due_date"] is not None

    # 2) 직원 소명 제출 -> 소명제출
    sub = client.post(
        f"{C}/transactions/{tid}/submit-explanation",
        headers=_emp("emp_kim"),
        json={"content": "출장 중 부득이한 야근 식대였습니다."},
    )
    assert sub.status_code == 200
    body = sub.json()
    assert body["explanation_status"] == "소명제출"
    assert body["explanation_content"] == "출장 중 부득이한 야근 식대였습니다."
    assert body["explanation_submit_dt"] is not None

    # 3) 관리자 최종 처리 -> 위반확정 ('소명제출' 상태에서 처리 가능)
    proc = client.post(
        f"{C}/transactions/process-explanation",
        headers=HEADERS_ADMIN,
        json={"transaction_ids": [tid], "status": "위반확정", "process_comment": "한도 초과 확정"},
    )
    assert proc.status_code == 200
    assert proc.json()[0]["explanation_status"] == "위반확정"

    db = session_factory()
    row = db.get(ReceiptTransaction, tid)
    db.close()
    assert row.explanation_status == "위반확정"
    assert row.explanation_content == "출장 중 부득이한 야근 식대였습니다."


def test_employee_isolation(client, session_factory):
    """직원은 본인 건만 조회 — 타 직원 위반은 노출되지 않는다."""
    ids = _seed_violations(session_factory)
    lee_rows = client.get(f"{C}/my/transactions", headers=_emp("emp_lee")).json()
    lee_ids = {x["id"] for x in lee_rows}
    assert ids["a_first"] not in lee_ids  # emp_kim 의 건은 안 보임
    assert ids["a_lee"] in lee_ids        # 본인 건은 보임


def test_employee_submit_foreign_404(client, session_factory):
    """타 직원의 건을 제출 시도하면 404(존재 비노출)."""
    ids = _seed_violations(session_factory)
    client.post(
        f"{C}/transactions/request-explanation",
        headers=HEADERS_ADMIN,
        json={"transaction_ids": [ids["a_first"]], "request_message": "x"},
    )
    r = client.post(
        f"{C}/transactions/{ids['a_first']}/submit-explanation",
        headers=_emp("emp_lee"),
        json={"content": "타인 건 제출 시도"},
    )
    assert r.status_code == 404


def test_employee_submit_wrong_state_409(client, session_factory):
    """요청 전('미요청') 건에 소명 제출하면 409."""
    ids = _seed_violations(session_factory)
    r = client.post(
        f"{C}/transactions/{ids['a_first']}/submit-explanation",
        headers=_emp("emp_kim"),
        json={"content": "요청 전 제출"},
    )
    assert r.status_code == 409


def test_cross_tenant_request_404(client, session_factory):
    """회사A 헤더로 회사B 트랜잭션 소명 요청 -> 404 (원자적 격리)."""
    ids = _seed_violations(session_factory)
    r = client.post(
        f"{C}/transactions/request-explanation",
        headers=HEADERS_ADMIN,
        json={"transaction_ids": [ids["b_first"]], "request_message": "x"},
    )
    assert r.status_code == 404
