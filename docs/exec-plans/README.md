# exec-plans/ — 실행 계획 & 기술 부채 추적

에이전트가 하는 모든 비자명한 작업은 **여기 계획으로 먼저 존재**해야 한다(GP-10). 계획은 작업의
메모리이자 인수인계 문서다 — 세션이 끊겨도 다음 에이전트가 이어받을 수 있어야 한다.

## 규칙
- 새 작업 시작 시 [_TEMPLATE.md](_TEMPLATE.md) 를 복사해 `YYYY-MM-DD-<슬러그>.md` 로 만든다.
- 상단 frontmatter 의 `status` 를 `active`/`blocked`/`done`/`abandoned` 로 항상 최신화한다.
- 완료되면 `status: done` + `완료 요약` 을 채운다. 파일은 지우지 않는다(이력 보존).
- 기술 부채는 개별 계획이 아니라 [tech-debt-ledger.md](tech-debt-ledger.md) 한 곳에 누적한다.

## 자동 점검
- `scripts/gardening/doc-drift-check.ps1` 가 `status: active` 인데 30일 이상 갱신 없는 계획을 'stale' 로 보고한다.
- doc-gardening 워크플로가 주기적으로 stale 계획을 리뷰 대상으로 올린다.

## 현재 계획
<!-- doc-gardening 이 이 목록을 갱신한다. 수동 편집해도 무방. -->
- [2026-06-16-tenant-whitelist.md](2026-06-16-tenant-whitelist.md) — `status: active` — 테넌트 화이트리스트 게이트.
- [2026-06-16-agent-first-harness.md](2026-06-16-agent-first-harness.md) — `status: active` — 본 에이전트 우선 하네스 구축.
