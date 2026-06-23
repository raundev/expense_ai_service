# 기술 부채 원장 (Tech Debt Ledger)

에이전트가 코드를 계속 생성하면 엔트로피가 쌓인다. 이 원장은 그 부채를 **한 곳에** 누적해
가비지 컬렉션(자동 리팩터링 PR)의 작업 큐로 쓴다. `scripts/gardening/` 이 일부를 자동 적발한다.

> 형식: `[ ] DEBT-N (심각도) — 설명 / 근거 / 제안`. 해결되면 `[x]` 로 바꾸고 PR 링크를 단다.
> **주의**: 아래 항목은 리포 스캔으로 도출한 *후보*다. 실행 전 반드시 현 상태를 재검증한다(파괴 금지).

## 미해결
- [ ] **DEBT-1** (low) — 레거시 `venv/` 디렉터리. core-architecture 가 "사용하지 않는다"고 명시. 추적 여부·삭제 안전성 확인 후 제거 제안. 근거: [core-architecture.md](../design-docs/core-architecture.md) §Python 레이아웃.
- [ ] **DEBT-2** (low) — 루트 코드 덤프 산출물 `code_context_for_gemini.txt`(~150KB)·`export_code.py`. 일회성 컨텍스트 추출 흔적으로 보임 → `.gitignore` 대상인지/삭제 가능한지 검토.
- [ ] **DEBT-3** (med) — `expense_ai.db` / `expense_ai.db.bak` 가 워킹 트리에 존재. 로컬 dev DB 는 커밋되면 안 됨 — `.gitignore` 등재 및 추적 중이면 `git rm --cached` 검토(GP-8 인접).
- [ ] **DEBT-4** (low) — 관측 하네스의 Prometheus 메트릭은 앱에 `/metrics` 엔드포인트가 있어야 의미가 있다. `prometheus-fastapi-instrumentator` 도입 여부는 미결(현재 스켈레톤은 스크레이프 설정만 둠). 근거: [observability-harness.md](../references/observability-harness.md).
- [ ] **DEBT-5** (low) — 자율 PR/리뷰 워크플로의 에이전트 호출 단계가 placeholder. 실제 CLI(`claude`/SDK) 결선 및 시크릿 주입 필요. 근거: [scripts/agent/README.md](../../scripts/agent/README.md).

## 해결됨
<!-- 해결 시 위에서 옮겨 적는다. -->
- (없음)
