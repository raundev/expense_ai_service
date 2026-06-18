# docs/ — 리포지토리 지식 베이스 (Agent-First Knowledge Base)

이 디렉터리는 **단일 진실 공급원(System of Record)** 이다. 거대한 단일 매뉴얼 대신,
역할별로 분류된 마크다운 생태계로 지식을 보관한다. 루트 [CLAUDE.md](../CLAUDE.md) 는
이 생태계의 **목차(TOC)** 일 뿐이며, 실체는 여기에 있다.

> 원칙: 리포지토리에 적히지 않은 지식(사람 머릿속·외부 채팅)은 **존재하지 않는 것**으로 간주한다([core-beliefs.md](design-docs/core-beliefs.md) GP-10).

## 디렉터리 지도

| 경로 | 용도 | 누가 쓰나 |
|------|------|-----------|
| [`design-docs/`](design-docs/) | 아키텍처 설계·핵심 신념(불변 규칙) | 결정을 내리기 전에 읽는다 |
| [`exec-plans/`](exec-plans/) | 진행 중/완료 실행 계획 + 기술 부채 추적 | 작업을 시작·재개할 때 |
| [`generated/`](generated/) | AI 가 자동 생성(DB 스키마 등) — **손으로 고치지 말 것** | 현재 상태를 조회할 때 |
| [`product-specs/`](product-specs/) | 제품 명세·사용자 여정 | "무엇을/왜" 를 확인할 때 |
| [`references/`](references/) | 외부 프레임워크·도구 참조 + 운영 매뉴얼 | "어떻게" 를 확인할 때 |

## 진입 순서 (에이전트용)

1. 루트 [CLAUDE.md](../CLAUDE.md) — 행동 규칙(OVERRIDE) 요약 + 목차.
2. [design-docs/core-architecture.md](design-docs/core-architecture.md) — 시스템 전모.
3. [design-docs/core-beliefs.md](design-docs/core-beliefs.md) — 깨면 안 되는 황금 원칙(GP-1~10).
4. 작업 대상이 있으면 [exec-plans/](exec-plans/) 에서 관련 계획을 찾거나 새로 만든다([_TEMPLATE.md](exec-plans/_TEMPLATE.md)).

## 기존 문서 (이전 위치 유지)

아래는 코드 주석/README 가 경로로 인용하므로 **이동하지 않는다**:
- [DESIGN_policy_rag_chatbot.md](DESIGN_policy_rag_chatbot.md) — Policy RAG 상세 설계("설계 §N" 의 대상).
- [PRD_Phase2_Draft.md](PRD_Phase2_Draft.md) — Phase 2 제품 요구.
- [API_COMPARISON_bizplay-ai_vs_expense.md](API_COMPARISON_bizplay-ai_vs_expense.md) — API 비교.

## 정원 관리 (Doc-Gardening)

문서와 코드가 어긋나면 `scripts/gardening/doc-drift-check.ps1` 이 드리프트를 보고하고,
`.github/workflows/doc-gardening.yml` 이 주기적으로 재생성·동기화 PR 을 제안한다.
자세한 운영은 [references/observability-harness.md](references/observability-harness.md) 와
[scripts/gardening/README.md](../scripts/gardening/README.md) 참고.
