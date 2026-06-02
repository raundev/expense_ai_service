# Bizplay AI — Compliance & Recommendation API

영수증 **용도 자동 추천**과 **RAG 기반 사내 규정 컴플라이언스 감사**를 제공하는 멀티테넌트 백엔드 서비스입니다.
모든 회사/사업장(테넌트)이 하나의 시스템에서 독립적으로 영수증 정산 · 사칙 챗봇 · 규정 위반 감사를 수행합니다. **(Phase 1 완성, v1.0.0)**

---

## ✨ 주요 기능

| # | 기능 | 핵심 구현 |
|---|------|-----------|
| 1 | **영수증 용도 자동 추천** | `RULE → HISTORY → LLM` 다단 분류를 LangGraph StateGraph 로 오케스트레이션 |
| 2 | **사내 규정 RAG 챗봇** | Qdrant 단일 컬렉션 + **Payload Filter**(`company_id`/`workplace_id`)로 테넌트 격리 |
| 3 | **컴플라이언스 자동 감사** | 분류 성공 영수증을 RAG 로 사칙 위배 판정(`with_structured_output`), 위반 시 소명 워크플로우 자동 시작 |
| 4 | **관리자 감사 콘솔** | 대시보드 KPI/차트, 위반 그리드 조회·엑셀(CSV) 다운로드, 소명 요청·처리·취소 |

- **멀티테넌트 격리**: 모든 도메인 접근은 `(company_id, workplace_id)` 로 범위가 강제됩니다.
- **Fail-Open**: 컴플라이언스 인프라(Qdrant/LLM) 장애 시에도 영수증 처리는 블로킹되지 않습니다.

---

## 🧱 기술 스택

- **API**: FastAPI, Uvicorn, Pydantic v2
- **AI 오케스트레이션**: LangGraph, LangChain
- **LLM**: vLLM(Qwen2.5-14B-Instruct) OpenAI 호환 엔드포인트 — 구조화 출력(`with_structured_output`)
- **RAG / 벡터 검색**: Qdrant + `langchain-qdrant`, `OpenAIEmbeddings`
- **RDB / 마이그레이션**: SQLAlchemy 2.0, Alembic (로컬 SQLite / 운영 PostgreSQL 옵션)
- **컨테이너**: Docker, docker-compose

---

## 🔐 멀티테넌트 인증 헤더 (모든 도메인 API 필수)

| 헤더 | 필수 | 설명 |
|------|------|------|
| `X-Company-ID` | ✅ | 회사 식별자 |
| `X-Workplace-ID` | ✅ | 사업장 식별자 |
| `X-Admin-ID` | 소명 요청/처리/취소 시 | 관리자 식별자(감사 추적) |

> 헤더 누락 시 `422` 가 반환됩니다.

---

## 📚 주요 API 엔드포인트

> 전역 prefix: 추천/규칙/RAG = `/api/v1/...`, 컴플라이언스 = `/api/compliance/...`
> 전체 명세는 Swagger UI(`/docs`) 참고.

### 추천 (Transaction API)
| Method | Path | 설명 |
|--------|------|------|
| POST | `/api/v1/transactions/test-single-transaction/create` | 단건 추천 + 컴플라이언스 검증 (DB 미저장) |
| POST | `/api/v1/transactions/transaction/batch` | 다건 업로드 + 자동 분류·검증 적재 |
| GET  | `/api/v1/transactions/files/{file_id}/transactions` | 파일별 분류 결과 조회 |
| PUT  | `/api/v1/transactions/files/{file_id}/rows` | 자동 분류 결과 수동 교정 |

### 규칙 / RAG (Rule API · Policy RAG API)
| Method | Path | 설명 |
|--------|------|------|
| GET/POST/PUT | `/api/v1/rules/...` | 테넌트별 용도 분류 규칙 CRUD |
| POST | `/api/v1/policies/ingest` | 사내 규정 문서 적재 |
| POST | `/api/v1/policies/chat` | 사내 규정 RAG 질의응답 |

### 컴플라이언스 관리자 (Compliance Admin API)
| Method | Path | 설명 |
|--------|------|------|
| GET  | `/api/compliance/dashboard/kpi` | 위반 탐지/소명 상태별 KPI 집계 |
| GET  | `/api/compliance/dashboard/charts` | 시각화(일별 추이/항목별/부서별) |
| GET  | `/api/compliance/transactions` | 위반 영수증 그리드(필터/페이지네이션) |
| GET  | `/api/compliance/transactions/export` | 위반 그리드 엑셀(CSV) 다운로드 |
| POST | `/api/compliance/transactions/request-explanation` | 소명 요청 (→ `요청완료`) |
| POST | `/api/compliance/transactions/process-explanation` | 소명 처리 (→ `정상처리`/`위반확정`) |
| POST | `/api/compliance/transactions/cancel-explanation` | 소명 요청 취소 (→ `미요청` 롤백) |

---

## 🚀 로컬 실행 (docker-compose)

```bash
# 1) 환경 변수 준비 (.env.example 참고). 최소 OPENAI_API_KEY / LLM_MODEL 설정.
cp .env.example .env

# 2) 빌드 + 기동  (api:8000, qdrant:6333, postgres:5432)
docker compose up -d --build
#    → api 컨테이너는 기동 시 `alembic upgrade head` 로 스키마를 자동 적용합니다.

# 3) Swagger UI 확인
#    http://localhost:8000/docs

# 4) 호출 예시 — 멀티테넌트 헤더 필수
curl -X POST http://localhost:8000/api/v1/policies/ingest \
  -H "X-Company-ID: COMP_A" -H "X-Workplace-ID: HQ" \
  -H "Content-Type: application/json" \
  -d '{"text":"우리 회사의 야근 식대 한도는 15,000원입니다.","source_name":"취업규칙"}'
```

서비스 구성(`docker-compose.yml`):
- **api** — 본 저장소 `Dockerfile` 빌드, 포트 `8000`, 비루트 실행, 기본 SQLite(볼륨) 사용
- **qdrant** — `qdrant/qdrant` 공식 이미지, 포트 `6333`(REST)/`6334`(gRPC)
- **postgres** — 운영 RDB 옵션(기본은 SQLite 사용, 전환은 compose 주석 참고)

> 사내 SSL 인터셉션 환경에서는 CA 인증서를 컨테이너에 마운트하고 `SSL_CERT_FILE`/`REQUESTS_CA_BUNDLE` 를 컨테이너 내 경로로 지정하세요(compose 주석 참고).

### 로컬(비컨테이너) 실행
```bash
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload
```

---

## ⚙️ 환경 변수 (`.env`)

| 변수 | 예시 / 기본값 | 설명 |
|------|---------------|------|
| `OPENAI_API_KEY` | `rpa_...` | LLM/임베딩 API 키 |
| `OPENAI_API_BASE` | RunPod vLLM 엔드포인트 | OpenAI 호환 base URL |
| `LLM_MODEL` | `Qwen/Qwen2.5-14B-Instruct-AWQ` | 채팅/구조화 출력 모델 |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | 임베딩 모델 |
| `QDRANT_URL` | `http://localhost:6333` | Qdrant 주소(컨테이너에선 `http://qdrant:6333`) |
| `DB_URL` | `sqlite:///./expense_ai.db` | RDB 연결 문자열 |
| `SSL_CERT_FILE` | (옵션) | 사내 CA 경로(SSL 인터셉션 통과용) |

> `config.py` 는 `load_dotenv(override=True)` 로 **`.env` 를 단일 진실 공급원으로 강제**합니다(시스템 환경변수가 `.env` 를 가리는 드리프트 방지).

---

## 🧭 API 문서
- Swagger UI: `GET /docs`
- ReDoc: `GET /redoc`
- OpenAPI JSON: `GET /openapi.json`

---

## 📁 프로젝트 구조 (요약)
```
app/
├─ api/endpoints/    # transactions, rules, policies, compliance 라우터
├─ ai/               # graph.py(LangGraph), vector_store.py, llm_recommender.py
├─ services/         # transaction/rule/policy/compliance 서비스
├─ models/ schemas/  # SQLAlchemy ORM / Pydantic DTO
├─ core/             # config(설정), dependencies(테넌트 컨텍스트)
└─ main.py           # FastAPI 부트스트랩 + OpenAPI 메타 + 전역 예외 처리기
alembic/             # DB 마이그레이션
Dockerfile · docker-compose.yml
```

---

<details>
<summary><b>📎 부록: 초기 설계안 (PRD)</b></summary>

## 🎯 서비스 핵심 목표 (멀티테넌트 기반)
- **통합 정산 파이프라인**: 다수의 회사와 산하 사업장이 하나의 시스템에서 각자의 독립적인 영수증 정산, 사칙 챗봇, 컴플라이언스 검증을 수행하는 멀티테넌트 솔루션.
- **공통 도메인 기반 지능화**: 모든 기능이 동일한 핵심 도메인(용도/사칙/영수증 내역)을 참조하여 AI 판단의 일관성(환각 방지)을 보장.
- **최종 목표**: 영수증 입력부터 규정 검토, 환각 수정, 최종 결의서 파일 생성까지 자동화.

## 🏗️ 멀티테넌트 아키텍처 / 공통 도메인
- **용도 도메인(정형)**: RDB `company_receipt_rules` — 테넌트별 우선순위·조건(직책/금액/시간/키워드)과 결과(식대/접대비 등).
- **규정·사칙 도메인(벡터)**: Qdrant — 테넌트별 사규/지침/경조사 기준 등 문서. 메타데이터에 `company_id`/`workplace_id` 부여 후 Payload Filtering 으로 격리.
- **승인 내역 도메인(하이브리드)**: 과거 승인 이력을 RDB + 벡터로 보관(유사 사례 매칭).

## ⚙️ 기능별 구현 방향
- **기능 1 — 용도 자동 추천**: `Rule_Engine_Tool`(DB 규칙) → 실패 시 `History_Lookup_Tool`(과거 승인 Few-shot).
- **기능 2 — 사칙 RAG 챗봇**: 사용자 테넌트의 사칙에서만 검색. 적재 시 메타데이터 부여, 검색 시 Payload Filter 로 타사 유출 방지.
- **기능 3 — 컴플라이언스 검증 루프**: `Compliance_Check_Tool`(기능 2 RAG 활용)로 사칙 위배 검증. 위반 시 LangGraph 엣지로 반려 사유와 함께 재추천 요구.
- **최종 — 정산서/결의서 생성**: 검증을 통과한 데이터로 테넌트별 Excel/PDF 템플릿에 매핑하여 파일 생성.

## 🚀 다음 단계 (Next Steps)
- 벡터 DB 멀티테넌시: 컬렉션 분리 vs 메타데이터 필터링(확장 잦으면 필터링 유리) → **본 구현은 단일 컬렉션 + Payload Filter 채택**.
- 공통 도메인 동기화: 관리자의 규칙/사칙 변경이 DB·벡터 인덱스에 즉시 반영되는 Ingestion 파이프라인.

</details>
