# 핵심 신념 / 황금 원칙 (Core Beliefs / Golden Principles)

> 이 문서는 코드가 지켜야 하는 **불변 규칙**을 한 곳에 모은다. 에이전트가 PR 을 열 때
> 스스로 점검해야 하는 체크리스트이자, `scripts/gardening/golden-principles-check.ps1` 이
> 기계적으로 강제하려 시도하는 대상이다. 새 원칙을 추가하면 **체커도 함께 갱신**한다.

각 원칙은 `GP-N` 식별자를 가진다. 위반 의심 시 PR 설명에 `GP-N: <근거>` 로 명시한다.

## GP-1 — 멀티테넌트 격리는 제1원칙
모든 도메인 데이터 접근은 `(company_id, workplace_id)` 로 범위가 강제되어야 한다.
- RDB: 서비스 레이어 쿼리에 테넌트 필터 누락 금지.
- Qdrant: 단일 컬렉션 `tenant_documents` + Payload Filter(`company_id/workplace_id/domain/owner_id`). 필터 구성 책임은 서비스에 있다.
- 교차 오염 회귀 테스트(`HEADERS_A`/`HEADERS_B`)를 깨면 안 된다.
- 근거: [core-architecture.md](core-architecture.md) §멀티테넌트 격리.

## GP-2 — Fail-Open (감사가 결제를 막지 않는다)
Qdrant/LLM 장애 시에도 영수증 처리는 블로킹되지 않는다. 컴플라이언스 감사는 best-effort 부가 기능이며, 실패는 로깅 후 통과시킨다.

## GP-3 — Soft Delete + 멱등 물리 삭제
행을 즉시 지우지 않는다. `status`/`embedding_status="DELETING"` 전이로 조회에서 제외하고, 물리 삭제는 `cleanup_service` 가 **벡터→파일→행** 순서로 항목별 독립 트랜잭션·멱등으로 수행한다('좀비 벡터' 방지).

## GP-4 — `.env` 는 설정의 단일 진실 공급원
`load_dotenv(override=True)`. 시스템 환경변수로 `.env` 를 가리려 하지 말 것(env 드리프트로 LLM 호출이 깨졌던 이력). 새 설정은 `app/core/config.py` + `.env.example` 양쪽에 등록한다.

## GP-5 — 모델 변경 ⇒ 마이그레이션 (드리프트 0)
모델을 바꾸면 같은 PR 에 alembic 리비전을 포함한다. `test_no_model_migration_drift` 가 autogenerate diff==0 을 강제한다. 새 모델은 `app/models/__init__.py` 에 import 추가 필수.

## GP-6 — requirements.txt 규율
직접 import 하는 패키지는 `requirements.txt`(런타임)/`requirements-dev.txt`(테스트)에 명시한다. 로컬 잔여 패키지로 통과해도 CI 클린 설치는 깨진다. 의심되면 클린 venv 로 재현.

## GP-7 — 한국어 컨벤션
코드 주석·문서·API 응답 메시지는 한국어로 쓴다. 식별자(코드 심볼)는 영문 유지.

## GP-8 — dev DB 파괴 금지
`./expense_ai.db`(로컬 dev DB)에 downgrade 등 파괴적 alembic 명령을 직접 돌리지 않는다. 테스트는 scratch DB 로 monkeypatch 한다.

## GP-9 — 레이어 경계 준수
`endpoints/`(얇은 라우터) → `services/`(비즈니스 로직) → `models/`·`schemas/`. 라우터에 비즈니스 로직을 넣지 않는다. 공통 Documents 는 도메인 비종속(`owner_id`+`domain` 으로만 소유 표현, `bot_id` 직접 참조 금지).

## GP-10 — 단일 진실 공급원 / 에이전트 가독성
지식은 리포지토리에 존재해야 한다(사람 머릿속·외부 채팅의 지식은 "없는 것"으로 간주). 결정·계획·근거는 `docs/` 생태계에 마크다운으로 남긴다. 코드와 문서가 어긋나면 doc-gardening 이 문서를 코드에 맞춘다.
