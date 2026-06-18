# design-docs/ — 설계 문서 & 핵심 신념

시스템이 *어떻게/왜* 그렇게 생겼는지의 권위 있는 출처. 결정을 내리기 전에 여기를 읽는다.

| 문서 | 내용 |
|------|------|
| [core-architecture.md](core-architecture.md) | 아키텍처 전모 — Python 레이아웃, 멀티테넌트 격리, AI 파이프라인, 레이어, 설정. (구 루트 CLAUDE.md 전문) |
| [core-beliefs.md](core-beliefs.md) | 깨면 안 되는 황금 원칙 GP-1~10. `golden-principles-check.ps1` 의 강제 대상. |

관련(이동하지 않은 기존 설계):
- [../DESIGN_policy_rag_chatbot.md](../DESIGN_policy_rag_chatbot.md) — Policy RAG 상세 설계("설계 §N" 인용 대상).

## 작성 규칙
- "무엇을 만들지"(요구)는 [../product-specs/](../product-specs/), "지금 무슨 작업 중인지"는 [../exec-plans/](../exec-plans/) 로 분리한다. 여기엔 *지속되는 설계 결정과 불변식* 만 남긴다.
- 새 불변식을 만들면 [core-beliefs.md](core-beliefs.md) 에 `GP-N` 으로 추가하고 체커도 갱신한다(GP-10).
