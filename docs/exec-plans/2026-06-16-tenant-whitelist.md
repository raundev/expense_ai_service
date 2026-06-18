---
title: 테넌트 화이트리스트 게이트
slug: tenant-whitelist
status: active
owner: (진행 중 — 워킹 트리 변경으로 추정)
created: 2026-06-16
updated: 2026-06-16
related_gp: [GP-1, GP-5, GP-9]
---

# 테넌트 화이트리스트 게이트

> 이 계획은 현재 워킹 트리의 미커밋 변경(`app/models/tenant.py`, `app/api/endpoints/tenants.py`,
> `app/services/tenant_service.py`, `alembic/versions/e2c1a4b7d9f3_*.py`, `tests/test_tenant_enforcement.py` 등)에서
> **역으로 재구성**한 것이다. 작성 시점에 실제 의도를 가진 사람이 검증·보강해야 한다.

## 1. 목표 (왜)
등록된 테넌트만 도메인 API 를 호출할 수 있게 하는 화이트리스트 게이트를 도입한다.
`TENANT_ENFORCEMENT_MODE` = `off`(기본) / `log` / `enforce`(403) 3단 운영.

## 2. 배경 / 제약
- 라우터 레벨 dependency `require_registered_tenant` 로 적용(`app/api/router.py`).
- **admin·tenants 라우터는 게이트 비적용** — 등록 자체가 막히는 닭-달걀 방지.
- 멀티테넌트 제1원칙(GP-1)과 정합해야 하며, 새 모델이므로 alembic 리비전 필수(GP-5).

## 3. 계획
- [x] `Tenant` 모델 + 화이트리스트 테이블 마이그레이션(`e2c1a4b7d9f3`).
- [x] `tenant_service` + `tenants` 엔드포인트(등록/조회).
- [x] `require_registered_tenant` 게이트 + `TENANT_ENFORCEMENT_MODE` 설정.
- [x] 강제 테스트(`tests/test_tenant_enforcement.py`).
- [ ] 마이그레이션 드리프트 0 확인(`test_no_model_migration_drift`).
- [ ] 문서화: README / core-architecture 의 게이트 설명과 일치 확인(doc-gardening).

## 4. 검증 전략
- `python -m pytest tests/test_tenant_enforcement.py -q`
- `python -m pytest tests/test_cross_contamination.py -q` (격리 회귀 GP-1)
- CI 의 마이그레이션 드리프트 테스트 통과.

## 5. 진행 로그
- 2026-06-16: 워킹 트리 변경으로부터 계획 재구성(에이전트 우선 하네스 도입 작업의 일환).

## 6. 완료 요약
(미완)
