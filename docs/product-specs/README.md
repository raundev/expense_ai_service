# product-specs/ — 제품 명세 & 사용자 여정

"무엇을, 왜" 만든다 — 기능 요구, 사용자 시나리오, 수용 기준. 구현 "어떻게" 는 [design-docs/](../design-docs/) 와 [references/](../references/) 가 담당한다.

## 현재 명세
- [PRD_Phase2_Draft.md](../PRD_Phase2_Draft.md) — Phase 2 제품 요구(초안). *위치 유지*(기존 인용 경로).
- (신규 명세는 이 디렉터리에 `NN-<기능>.md` 로 추가)

## 핵심 사용자 여정 (요약)
1. **용도 자동 추천** — 직원이 영수증 제출 → RULE→HISTORY→LLM 다단 분류로 용도(계정과목) 추천.
2. **컴플라이언스 감사** — 분류 성공 시 RAG 로 사내 규정 위반 판정 → 위반 시 소명 워크플로우(미요청→요청완료→정상처리/위반확정).
3. **규정 문서 관리** — 관리자가 규정/정책 문서를 업로드 → 임베딩 → 감사 근거로 사용.

상세 흐름·노드는 [core-architecture.md](../design-docs/core-architecture.md) §AI 파이프라인 참조.

## 작성 규칙
- 사용자 관점의 수용 기준(Given/When/Then)을 포함한다.
- 구현 결정이 아니라 *요구*를 적는다. 결정은 design-docs 로, 작업은 exec-plans 로 분리.
