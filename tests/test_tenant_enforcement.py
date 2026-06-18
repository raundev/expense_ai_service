"""테넌트 등록 검증(require_registered_tenant) 통합 테스트.

기본 모드("off")에서는 미등록이어도 통과하고, "enforce" 모드에서는 미등록/SUSPENDED 가
403 으로 차단되는지 검증한다. 등록은 게이트 비적용 admin API(/api/admin/tenants)로 수행한다.
공용 `client` 픽스처(conftest)는 get_db 를 인메모리 테스트 DB 로 오버라이드하므로,
같은 DB 에 등록 → 게이트 조회가 일관되게 동작한다(StaticPool 단일 커넥션).
"""
from __future__ import annotations

import pytest

from app.core.config import settings

# 게이트 대상(도메인) 엔드포인트 — 읽기 호출로 게이트만 검증(리소스 데이터 불필요).
_BOTS_URL = "/api/v1/bots"
_TENANTS_URL = "/api/admin/tenants"

_HEADERS = {"X-Company-ID": "COMPANY_A", "X-Workplace-ID": "HQ"}


@pytest.fixture
def enforce(monkeypatch):
    """TENANT_ENFORCEMENT_MODE 를 enforce 로 강제(의존성이 요청 시점에 읽으므로 monkeypatch 면 충분)."""
    monkeypatch.setattr(settings, "TENANT_ENFORCEMENT_MODE", "enforce")


def _register(client, company_id: str = "COMPANY_A", workplace_id: str = "HQ") -> dict:
    resp = client.post(
        _TENANTS_URL,
        json={"company_id": company_id, "workplace_id": workplace_id},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


def test_off_mode_allows_unregistered(client):
    """기본(off) 모드: 미등록 테넌트도 도메인 API 통과(기존 동작 보존)."""
    resp = client.get(_BOTS_URL, headers=_HEADERS)
    assert resp.status_code == 200, resp.text


def test_enforce_blocks_unregistered(client, enforce):
    """enforce 모드: 미등록 테넌트는 403."""
    resp = client.get(_BOTS_URL, headers=_HEADERS)
    assert resp.status_code == 403, resp.text


def test_enforce_allows_registered(client, enforce):
    """enforce 모드: 등록(ACTIVE)된 테넌트는 통과."""
    _register(client)
    resp = client.get(_BOTS_URL, headers=_HEADERS)
    assert resp.status_code == 200, resp.text


def test_enforce_blocks_suspended(client, enforce):
    """enforce 모드: SUSPENDED 로 전환된 테넌트는 403."""
    created = _register(client)
    patched = client.patch(
        f"{_TENANTS_URL}/{created['id']}",
        json={"status": "SUSPENDED"},
    )
    assert patched.status_code == 200, patched.text
    resp = client.get(_BOTS_URL, headers=_HEADERS)
    assert resp.status_code == 403, resp.text


def test_enforce_reactivate_restores_access(client, enforce):
    """enforce 모드: SUSPENDED → ACTIVE 복구 시 다시 통과."""
    created = _register(client)
    client.patch(f"{_TENANTS_URL}/{created['id']}", json={"status": "SUSPENDED"})
    assert client.get(_BOTS_URL, headers=_HEADERS).status_code == 403
    client.patch(f"{_TENANTS_URL}/{created['id']}", json={"status": "ACTIVE"})
    assert client.get(_BOTS_URL, headers=_HEADERS).status_code == 200


def test_register_duplicate_conflict(client):
    """동일 (company_id, workplace_id) 재등록은 409."""
    _register(client)
    dup = client.post(
        _TENANTS_URL,
        json={"company_id": "COMPANY_A", "workplace_id": "HQ"},
    )
    assert dup.status_code == 409, dup.text


def test_tenants_endpoint_not_gated(client, enforce):
    """enforce 모드여도 테넌트 등록 API 자체는 게이트 비적용(닭-달걀 방지)."""
    resp = client.post(
        _TENANTS_URL,
        json={"company_id": "COMPANY_NEW", "workplace_id": "BR1"},
    )
    assert resp.status_code == 201, resp.text


def test_list_tenants(client):
    """등록한 테넌트가 목록에 노출된다."""
    _register(client, "COMPANY_A", "HQ")
    _register(client, "COMPANY_B", "HQ")
    resp = client.get(_TENANTS_URL)
    assert resp.status_code == 200, resp.text
    pairs = {(t["company_id"], t["workplace_id"]) for t in resp.json()["data"]}
    assert ("COMPANY_A", "HQ") in pairs
    assert ("COMPANY_B", "HQ") in pairs
