# 외부 도구 참조 (리포 특화 요점 + 함정)

공식 문서가 진실. 여기엔 **이 리포에서 부딪히는 패턴/함정**만 적는다.

## LangGraph (app/ai/graph.py)
- `StateGraph` 다단 분류: `rule → history → llm → (성공 시) compliance → END`. 분류 NONE 이면 compliance 생략.
- **DI**: state 에 `db_session`/`llm_recommender`/`policy_service` 주입 → 테스트에서 fake 교체(conftest).
- LLM 구조화 출력은 `with_structured_output` 사용(Qwen2.5-14B 지원 확인됨).

## Qdrant (app/ai/vector_store.py)
- 전 테넌트·전 도메인 **단일 컬렉션 `tenant_documents`**. 격리 = Payload Filter(`company_id/workplace_id/domain/owner_id`).
- 필터 필드는 `_PAYLOAD_INDEXES` 에 인덱스 등록 필수(미등록 시 느리거나 필터 불가).
- 로컬 임베디드 모드: `QDRANT_URL=path:./qdrant_local` — **폴더 파일 락으로 한 번에 한 프로세스만** 연다(병렬 테스트/서버 동시 기동 충돌 주의).

## 임베딩 (분리 구성)
- RunPod LLM endpoint 는 **챗 전용** — `/embeddings` 없음. `EMBEDDING_PROVIDER` 로 분리: `openai`(별도 API) 또는 `fastembed`(로컬 ONNX, 네트워크 불필요).

## Alembic (.venv 전용)
- 시스템 python 엔 진짜 `alembic.config` 없음(루트 `alembic/` 가 namespace 패키지로 잡힘). 마이그레이션은 `.venv\Scripts\alembic.exe` 로만.
- `env.py` 가 `settings.sqlalchemy_database_uri` 로 URL 덮어씀 → 로컬은 `./expense_ai.db`. **downgrade 등 파괴 명령 dev DB 직접 금지**(GP-8).
- 모델 변경 → `revision --autogenerate` 필수. `test_no_model_migration_drift` 가 diff==0 강제.

## FastAPI
- 도메인 API 는 `X-Company-ID`/`X-Workplace-ID` 헤더 필수(누락 422). 소명류 `X-Admin-ID`, 직원용 `X-Employee-ID`.
- Form/File 엔드포인트는 `python-multipart` 가 import 시점 필수(requirements 규율 GP-6).
- 기동 lifespan 이 DB 리비전 vs 코드 head 점검(`app/db/version_check.py`). 비-local 환경은 불일치 시 부팅 실패.

## 설정/네트워크 함정
- `.env` 가 단일 진실(`load_dotenv(override=True)`) — 시스템 env 로 가리지 말 것(GP-4).
- 사내 SSL 인터셉션: `SSL_CERT_FILE` 은 **certifi(공개 CA)+사내 CA 결합 번들**이어야 공개 TLS(HuggingFace 등) 동작.
