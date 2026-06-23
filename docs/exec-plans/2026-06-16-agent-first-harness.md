---
title: 에이전트 우선(Agent-First) 하네스 구축
slug: agent-first-harness
status: active
owner: Claude (Opus 4.8)
created: 2026-06-16
updated: 2026-06-16
related_gp: [GP-10]
---

# 에이전트 우선 하네스 구축

사람이 코드를 한 줄도 직접 쓰지 않고 프롬프트·피드백만으로 라이프사이클을 통제하는
'하네스 엔지니어링' 환경을 이 리포에 도입한다. 이 문서 자체가 그 방법론의 자기 증명이다.

## 1. 목표
4개 기둥을 스캐폴딩한다: (1) 지식 베이스 `docs/`, (2) 관측 하네스(눈), (3) 자율 PR 루프, (4) doc-gardening/code-GC.

## 2. 배경 / 제약
- **기존 자산 보존**: 풍부했던 루트 `CLAUDE.md` 는 [core-architecture.md](../design-docs/core-architecture.md) 로 무손실 이전(사용자 승인). 루트는 ≤100줄 목차로 재작성.
- **안전 우선**: 자율 루프는 스켈레톤(수동 트리거·자동 머지 없음). 비가역 외부 행동은 사람 게이트.
- Windows/PowerShell 로컬 + ubuntu CI 이중 환경 고려.

## 3. 계획
- [x] `docs/` 5종 디렉터리 + 인덱스/템플릿/원장.
- [x] 루트 `CLAUDE.md` → 목차화(OVERRIDE 규칙 보존), 기존 내용 이전.
- [x] 관측: `scripts/observability/`(CDP UI 캡처 + 워크트리별 Loki/Prometheus 스택).
- [x] 자율 루프: `.github/workflows/agent-pr-loop.yml`·`agent-review.yml` + `scripts/agent/ralph-loop.ps1`.
- [x] 정원 관리: `.github/workflows/doc-gardening.yml` + `scripts/gardening/`(드리프트·황금원칙 체커, 스키마 생성기).
- [x] 운영 매뉴얼 + 멱등 스캐폴딩 스크립트.
- [ ] 실제 에이전트 CLI 결선(시크릿) — DEBT-5.
- [ ] 앱 `/metrics` 노출 여부 결정 — DEBT-4.

## 4. 검증 전략
- `scripts/scaffold-agent-repo.ps1` 멱등 재실행 시 변경 0.
- `scripts/gardening/doc-drift-check.ps1` 가 깨진 링크 0 보고.
- 기존 테스트 영향 없음: `python -m pytest -q` 그린 유지.

## 5. 진행 로그
- 2026-06-16: 4개 기둥 스캐폴딩 1차 완료. 자율 호출/메트릭 노출은 후속(원장 DEBT-4/5).

## 6. 완료 요약
(스켈레톤 단계 완료 — 실 결선은 후속)
