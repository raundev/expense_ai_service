# CLAUDE.md — 목차 (System-of-Record Index)

이 파일은 **거대한 매뉴얼이 아니라 목차**다. Claude Code(및 모든 에이전트)가 세션 시작 시 처음 읽는 거버넌스 파일이며,
상세 지식은 [`docs/`](docs/README.md) 생태계에 있다. 아키텍처 전모는 [docs/design-docs/core-architecture.md](docs/design-docs/core-architecture.md),
깨면 안 되는 규칙은 [docs/design-docs/core-beliefs.md](docs/design-docs/core-beliefs.md)(GP-1~10).

> 이 리포는 **에이전트 우선(Agent-First)** 으로 운영된다 — 사람은 프롬프트·피드백만 주고, 코드/문서는 에이전트가 쓴다.
> 리포에 적히지 않은 지식은 "없는 것"으로 간주한다. 운영 방법은 [docs/references/agent-operating-manual.md](docs/references/agent-operating-manual.md).

## 프로젝트 한 줄 요약
영수증 **용도 자동 추천**(RULE→HISTORY→LLM) + **RAG 기반 사내 규정 컴플라이언스 감사**를 제공하는 멀티테넌트 FastAPI 백엔드.

## 핵심 행동 규칙 (OVERRIDE — 반드시 준수)
아래는 *요약*이다. 근거·전문은 링크된 문서에 있다. 충돌 시 이 규칙이 기본 동작을 덮어쓴다.

1. **한국어 컨벤션** — 코드 주석·문서·API 응답 메시지는 한국어(식별자는 영문). (GP-7)
2. **멀티테넌트 격리는 제1원칙** — 모든 데이터 접근은 `(company_id, workplace_id)` 로 범위 강제. Qdrant 는 단일 컬렉션 + Payload Filter. (GP-1 · [core-architecture.md](docs/design-docs/core-architecture.md))
3. **Python 인터프리터 3종 주의** — 앱/pytest 는 **시스템 python**, alembic 은 **`.venv` 전용**, `venv` 는 레거시(미사용). 시스템 python 엔 진짜 `alembic.config` 없음.
4. **모델 변경 ⇒ 같은 PR 에 alembic 리비전** — `test_no_model_migration_drift` 가 diff==0 강제. 새 모델은 `app/models/__init__.py` 에 import 추가. (GP-5)
5. **`.env` 가 설정 단일 진실 공급원** — `load_dotenv(override=True)`. 시스템 env 로 덮으려 하지 말 것. (GP-4)
6. **requirements 규율** — 직접 import 패키지는 `requirements*.txt` 에 명시(로컬 통과해도 CI 클린설치 깨짐). (GP-6)
7. **Fail-Open / Soft-Delete / dev DB 파괴 금지** — 감사는 결제를 막지 않음(GP-2); 삭제는 상태 전이(GP-3); `./expense_ai.db` 에 파괴적 alembic 금지(GP-8).
8. **레이어 경계** — `endpoints`(얇게) → `services`(로직) → `models`·`schemas`. (GP-9)

## 빠른 명령어
```powershell
python -m pytest -q                 # 전체 테스트(루트에서). 외부 의존성 불필요(인메모리 SQLite/Qdrant/LLM 스텁)
./scripts/run-local.ps1             # alembic upgrade head(.venv) → uvicorn(시스템 python)
.venv\Scripts\alembic.exe revision --autogenerate -m "..."   # 마이그레이션 생성
docker compose up -d --build        # api:8000 · qdrant:6333 · postgres:5432
```
전체 명령·함정은 [core-architecture.md](docs/design-docs/core-architecture.md) §명령어.

## 지식 베이스 지도 ([docs/README.md](docs/README.md))
| 경로 | 용도 |
|------|------|
| [docs/design-docs/](docs/design-docs/) | 아키텍처 설계 + 핵심 신념(불변 규칙) |
| [docs/exec-plans/](docs/exec-plans/) | 실행 계획 + 기술 부채 추적 |
| [docs/generated/](docs/generated/) | AI 자동 생성(DB 스키마 등) — 손으로 수정 금지 |
| [docs/product-specs/](docs/product-specs/) | 제품 명세·사용자 여정 |
| [docs/references/](docs/references/) | 외부 도구 참조 + 운영 매뉴얼 + 관측 하네스 |

## 자율 하네스 (Self-Verification & Loops)
- **관측(눈)**: UI 스냅샷·로그/메트릭 자가 검증 — [scripts/observability/README.md](scripts/observability/README.md).
- **자율 PR 루프(Ralph)**: [scripts/agent/README.md](scripts/agent/README.md) · `.github/workflows/agent-pr-loop.yml`(안전 스켈레톤: 수동 트리거·자동머지 없음).
- **정원 관리(엔트로피)**: [scripts/gardening/README.md](scripts/gardening/README.md) · `.github/workflows/doc-gardening.yml` — 문서↔코드 드리프트 자동 동기화.
- **스캐폴딩 재생성(멱등)**: `scripts/scaffold-agent-repo.ps1`.
