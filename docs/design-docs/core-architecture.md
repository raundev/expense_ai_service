# 핵심 아키텍처 (Core Architecture)

> **출처/지위**: 이 문서는 과거 루트 `CLAUDE.md` 의 전문(全文)을 무손실 이전한 것이다.
> 루트 `CLAUDE.md` 는 이제 100줄 이내의 **목차(TOC)** 로만 동작하며, 본 문서가 아키텍처의 **단일 진실 공급원(System of Record)** 이다.
> 행동 규칙(OVERRIDE)의 *요약본* 은 루트 `CLAUDE.md` 에, *근거와 전문* 은 여기에 있다.
> 마지막 동기화: 2026-06-16 (doc-gardening 대상 — `scripts/gardening/doc-drift-check.ps1`).

## 프로젝트 개요

영수증 **용도 자동 추천**(RULE→HISTORY→LLM)과 **RAG 기반 사내 규정 컴플라이언스 감사**를 제공하는 멀티테넌트 FastAPI 백엔드. 코드 주석·문서·API 응답 메시지는 한국어가 컨벤션이다. 상세 설계는 [docs/DESIGN_policy_rag_chatbot.md](../DESIGN_policy_rag_chatbot.md) 참고 — 코드 주석의 "설계 §N" 인용이 이 문서를 가리킨다.

## Python 인터프리터 레이아웃 (중요)

세 환경이 공존하며 역할이 다르다:

- **시스템 python** (`python`, AppData...Python312): 앱 풀스택(langchain/langgraph/pytest 포함). **서버 구동·테스트용.** 단, 진짜 alembic 패키지는 없다 — 루트의 `alembic/` 디렉터리가 namespace 패키지로 잡혀 `import alembic` 은 성공하지만 `alembic.config` 는 없다(가용성 판정 시 주의).
- **`.venv`**: alembic 설치됨(**마이그레이션 전용**). pytest 없음.
- **`venv`**: 레거시. 사용하지 않는다.

## 명령어

### 테스트
```powershell
python -m pytest -q                                  # 전체 (프로젝트 루트에서)
python -m pytest tests/test_compliance.py -q         # 파일 단위
python -m pytest tests/test_transactions.py::test_name -q   # 단일 테스트
```
- 외부 의존성 불필요: 인메모리 SQLite(StaticPool) + `DeterministicFakeEmbedding` + in-memory Qdrant + LLM 결정론 스텁으로 동작한다(`tests/conftest.py`).
- `tests/test_migrations.py` 는 진짜 alembic 이 있는 인터프리터(CI 등)에서만 실행 — `importorskip("alembic.config")` 로 시스템 python 에서는 자동 skip 된다.
- CI(`.github/workflows/main.yml`): Python 3.12, `pip install -r requirements-dev.txt`, `ENVIRONMENT=ci pytest -q`.

### 서버 실행
```powershell
./scripts/run-local.ps1            # alembic upgrade head(.venv) → uvicorn(시스템 python). Dockerfile CMD 와 동일 순서
uvicorn app.main:app --reload      # 마이그레이션이 이미 적용된 경우
docker compose up -d --build       # api:8000, qdrant:6333, postgres:5432
```
- 기동 시 lifespan 이 DB 리비전 vs 코드 head 를 점검한다(`app/db/version_check.py` — alembic import 없이 파일 파싱). `ENVIRONMENT != local` 이면 불일치 시 부팅 실패, local 은 경고만.
- Docker/외부 서버 없이 RAG 포함 단일 프로세스 테스트: `.env` 에 `QDRANT_URL=path:./qdrant_local`(임베디드) + `EMBEDDING_PROVIDER=fastembed`(로컬 ONNX). 임베디드 Qdrant 는 폴더 파일 락으로 한 번에 한 프로세스만 연다.

### 마이그레이션 (alembic 은 .venv 에만 있음)
```powershell
.venv\Scripts\alembic.exe upgrade head
.venv\Scripts\alembic.exe revision --autogenerate -m "..."
```
- 모델 변경 시 마이그레이션 필수: `test_no_model_migration_drift` 가 autogenerate diff==0 을 강제한다(CI 에서 적발).
- 새 모델은 `app/models/__init__.py` 에 import 를 추가해야 autogenerate 와 테스트 `create_all` 에 잡힌다.
- `alembic/env.py` 는 `settings.sqlalchemy_database_uri` 로 URL 을 덮어쓴다 — 로컬 dev DB 는 `./expense_ai.db`. downgrade 등 파괴적 명령을 dev DB 에 직접 돌리지 말 것(테스트는 scratch DB 로 monkeypatch 함).

### Frontend (frontend/ — API 테스트 콘솔 SPA, Vite+React+TS)
```powershell
cd frontend; npm install; npm run dev    # http://localhost:5173
npm run build                            # dist/ 생성
```

## 아키텍처

### 멀티테넌트 격리 — 제1원칙
- 모든 도메인 API 는 `X-Company-ID`/`X-Workplace-ID` 헤더 필수 → `get_tenant_info`(`app/core/dependencies.py`)가 `TenantContext` 로 주입, 누락 시 422. 소명 처리류는 `X-Admin-ID`, 직원용 API 는 `X-Employee-ID` 추가.
- **RDB**: 서비스 레이어의 모든 쿼리가 `(company_id, workplace_id)` 로 범위를 강제한다.
- **Qdrant**: 전 테넌트·전 도메인 공용 **단일 컬렉션 `tenant_documents`**. 격리는 컬렉션 분리가 아니라 `metadata.company_id/workplace_id/domain/owner_id` Payload Filter 로 수행하며, 그 책임은 전적으로 서비스(`policy_service` 등)의 필터 구성에 있다. 필터 필드는 `app/ai/vector_store.py` 의 `_PAYLOAD_INDEXES` 에 인덱스로 등록한다.
- **테넌트 화이트리스트 게이트**: `require_registered_tenant` 를 라우터 레벨 dependency 로 적용(`app/api/router.py`). `TENANT_ENFORCEMENT_MODE` = `off`(기본)/`log`/`enforce`(403). admin·tenants 라우터는 게이트 비적용(등록 자체가 막히는 닭-달걀 방지).
- 격리 회귀 테스트 패턴: conftest 의 `HEADERS_A`/`HEADERS_B` 로 교차 오염 검증(`tests/test_cross_contamination.py`).

### AI 파이프라인 (app/ai/graph.py — LangGraph StateGraph)
- `rule`(DB 규칙, priority ASC) → miss → `history`(과거 승인 이력) → miss → `llm`(후보 번호 선택) 다단 분류. **분류 성공 시 반드시 `compliance` 노드 경유**, 실패(NONE) 시 compliance 생략 후 END.
- compliance 노드는 `PolicyService.check_compliance` — RAG 검색 + `with_structured_output` 위반 판정. 위반 시 소명 워크플로우(`미요청 → 요청완료 → 정상처리/위반확정`) 시작.
- **Fail-Open**: Qdrant/LLM 장애 시에도 영수증 처리는 블로킹되지 않는다.
- DI 패턴: 그래프 state 에 `db_session`/`llm_recommender`/`policy_service` 를 주입 — 테스트에서 fake 로 교체한다(conftest 의 `FakeRecommender`/`MockPolicyService`).

### 레이어와 도메인 모듈
- `app/api/endpoints/`(얇은 라우터) → `app/services/`(비즈니스 로직) → `app/models/`(SQLAlchemy)·`app/schemas/`(Pydantic). 전역 prefix `/api`, 도메인별 `/v1/...`·`/compliance`·`/admin`.
- **공통 Documents 모듈**: 도메인 비종속 — 소유는 범용 `owner_id`+`domain` 으로만 표현(bot_id 직접 참조 금지). 컴플라이언스 근거 문서는 `domain="expense_rule" AND is_compliance_source=true` 로 일반 규정(`domain="policy"`)과 검색 단계에서 분리.
- **Soft Delete**: 행을 지우지 않고 `status`/`embedding_status="DELETING"` 전이만 한다(조회에서 즉시 제외). 물리 삭제는 `cleanup_service` 워커가 **벡터→파일→행** 순으로, 항목별 독립 트랜잭션·멱등으로 수행한다(실패 시 rollback 후 다음 주기 재시도 — '좀비 벡터' 방지).

### 설정 (app/core/config.py)
- `load_dotenv(override=True)`: **`.env` 가 단일 진실 공급원** — 시스템 환경변수를 의도적으로 덮어쓴다(시스템 env 드리프트로 LLM 호출이 깨졌던 이력). 환경변수로 `.env` 를 가리려 하지 말 것.
- DB: `DATABASE_URL`(운영 PostgreSQL) 이 `DB_URL`(로컬 SQLite 기본) 보다 우선.
- LLM 은 OpenAI 호환 endpoint(RunPod vLLM Qwen2.5-14B). **RunPod 은 챗 전용 — `/embeddings` 라우트 없음.** 임베딩은 `EMBEDDING_PROVIDER=openai`(별도 API) 또는 `fastembed`(로컬 ONNX, 네트워크 불필요)로 분리 구성한다. `LLM_MODEL` 이 `Qwen*` 이면 HTTP 타임아웃 150초 적용.
- 사내 SSL 인터셉션 환경: `SSL_CERT_FILE` 은 사내 CA 단독이 아니라 **공개 CA(certifi)+사내 CA 결합 번들**이어야 HuggingFace 다운로드 등 공개 TLS 가 동작한다(README 절차 참고).

### requirements.txt 규율
직접 import 하는 패키지는 반드시 `requirements.txt` 에 명시한다 — 로컬은 잔여 패키지로 통과해도 CI 클린 설치가 깨진다(예: langchain v1 은 `langchain-text-splitters` 를 자동 설치하지 않음; FastAPI Form/File 은 `python-multipart` 가 import 시점 필수). 의심되면 클린 venv 로 재현 검증.
