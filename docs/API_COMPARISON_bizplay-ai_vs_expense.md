# 챗봇 API 비교 문서 — BizPlay AI Chatbot ↔ Expense AI Service

> 두 FastAPI 프로젝트의 **챗봇(Policy RAG) API**를 중심으로, URL 일치 여부·동일 URL의 기능 차이·그 외 설계 차이를 비교한다.
> 전체 엔드포인트 매핑은 동봉한 엑셀 [`API_endpoint_mapping_bizplay-ai_vs_expense.xlsx`](API_endpoint_mapping_bizplay-ai_vs_expense.xlsx) 참조.

- **비교 대상 A**: `bizplay-ai` — *BizPlay AI Chatbot API* (Spring AI → Python 포팅, 순수 RAG 챗봇). 출처: `bizplay-ai/docs/PROJECT_OVERVIEW.md`
- **비교 대상 B**: `expense_ai_service` — *Bizplay AI Compliance & Recommendation API* (영수증 용도추천 + 컴플라이언스 감사 **+** Policy RAG 챗봇). 출처: 소스 코드 정적 분석
- **작성 기준일**: 2026-06-05

---

## 1. 개요 — 두 API의 관계

`expense_ai_service`는 `bizplay-ai` 챗봇을 가져와 **세 가지를 바꾼 확장판**이다.

1. **멀티테넌시 방식 교체** — DB 엔티티(`CorpGroup → Corporation → Bot.corp_no`) → **HTTP 헤더**(`X-Company-ID` / `X-Workplace-ID`, 일부 `X-Admin-ID` / `X-Employee-ID`)
2. **문서 모듈 일반화** — 챗봇 종속(`bot_id`) → **도메인 비종속 공통 모듈**(`owner_id` + `domain`), 챗봇과 컴플라이언스 엔진이 공용
3. **신규 도메인 추가** — 영수증 용도추천(Transaction) · 분류 규칙(Rule) · 컴플라이언스 감사(Compliance) · 운영(Admin)

그 결과 **봇(bots) 관련 URL은 거의 1:1로 일치**하지만, **채팅(chat)·문서(documents)의 URL은 모두 불일치**한다.

---

## 2. 한눈에 보기

### 2.1 집계 (논리 엔드포인트 54종, 자동 문서 3종 포함)

| 분류 | 건수 | 구성 |
|------|:----:|------|
| 🟩 동일 (URL·동작) | 13 | 봇 관리 10 + 시스템 자동문서 3 |
| 🟨 URL 동일·동작 상이 | 2 | `DELETE /api/v1/bots/{bot_id}`, `GET /health` |
| 🟦 기능 동일·URL 상이 | 7 | 채팅 3 + 문서 4 |
| 🟧 expense 전용 | 21 | 영수증추천 5·규칙 3·컴플라이언스 9·운영 1·문서 2·규정적재 1 |
| ⬜ bizplay 전용 | 11 | 법인그룹 5·법인 5·법인별 봇 1 |
| **합계** | **54** | |

### 2.2 프로젝트별 총계

| 프로젝트 | 도메인 엔드포인트 | 자동문서 | 벡터 스토어 | 멀티테넌시 |
|----------|:----------------:|:--------:|------------|------------|
| BizPlay AI Chatbot (`bizplay-ai`) | 30 | 3 | pgvector | 법인(corp_no) DB |
| Expense AI Service (`expense_ai_service`) | 40 | 3 | Qdrant | HTTP 헤더 |

---

## 3. URL 주소 일치 여부

> 현재 프로젝트는 `API_PREFIX = /api` (`app/core/config.py`). 라우터 prefix는 `app/api/router.py` 기준.

### 3.1 ✅ 완전 일치 (URL · 메서드 동일)

| Method | URL | 비고 |
|--------|-----|------|
| POST | `/api/v1/bots` | 봇 생성 (검증 규칙 동일) |
| GET | `/api/v1/bots` | 봇 목록 |
| GET | `/api/v1/bots/{bot_id}` | 단건 조회 |
| PUT | `/api/v1/bots/{bot_id}` | 수정 (PATCH 시맨틱) |
| PATCH | `/api/v1/bots/{bot_id}/enable` · `/disable` | 활성 / 비활성 |
| GET | `/api/v1/bots/{bot_id}/statistics` · `/statistics/daily` | 통계 / 일별 통계 |
| GET | `/api/v1/bots/{bot_id}/sessions` | 세션 목록 |
| GET | `/api/v1/bots/{bot_id}/recommend` | 추천 질문 |
| GET | `/docs` · `/redoc` · `/openapi.json` | FastAPI 자동 생성 |

> `DELETE /api/v1/bots/{bot_id}` 와 `GET /health` 는 URL은 같지만 **동작이 다르다** → §4 참조.

### 3.2 🟦 같은 기능, 다른 URL (핵심 불일치)

| 기능 | bizplay-ai | expense_ai_service | 차이 |
|------|-----------|--------------------|------|
| RAG 채팅 | `POST /api/v1/`**`rag`**`/chat` | `POST /api/v1/`**`policies`**`/chat` | 세그먼트 `rag` → `policies` |
| LLM 모델 목록 | `GET /api/v1/rag/chat/models` | `GET /api/v1/policies/chat/models` | 〃 |
| 세션 히스토리 | `GET /api/v1/rag/chat/history/{session_id}` | `GET /api/v1/policies/chat/history/{session_id}` | 〃 |
| 문서 업로드 | `POST /api/v1/`**`rag/documents`**`/upload` | `POST /api/v1/`**`documents`**`/upload` | `rag` 제거 + 파라미터 변경(§4.4) |
| 문서 목록 | `GET /api/v1/rag/documents?`**`bot_id=`** | `GET /api/v1/documents?`**`domain=&owner_id=`** | 필터 키 변경 |
| 문서 다운로드 | `GET /api/v1/rag/documents/{doc_id}/download` | `GET /api/v1/documents/{doc_id}/download` | 상위 prefix 상이 |
| 문서 삭제 | `DELETE /api/v1/rag/documents/{doc_id}` | `DELETE /api/v1/documents/{doc_id}` | prefix 상이 + 동작 상이(hard→soft) |

→ **챗봇의 두 핵심 리소스(chat·documents) URL이 전부 불일치.** 봇 관리만 호환되고, chat/documents 호출 클라이언트는 경로 수정이 필요하다.

### 3.3 🟧 expense_ai_service 에만 있는 URL

| 그룹 | 엔드포인트 |
|------|-----------|
| Transaction(영수증) | `POST /api/v1/transactions/test-single-transaction/create`, `POST .../transaction/batch`, `GET .../files/{file_id}/transactions`, `PUT .../files/{file_id}/rows`, `GET .../files/corp/{corp_no}/classify-summaries` |
| Rule(분류규칙) | `GET /api/v1/rules/`, `POST .../create`, `PUT .../update/{rule_id}` |
| Compliance(감사) | `GET /api/compliance/dashboard/kpi`·`/charts`, `GET .../transactions`·`/export`, `POST .../transactions/{request,process,cancel}-explanation`, `GET /api/compliance/my/transactions`, `POST .../transactions/{id}/submit-explanation` |
| Documents 추가 | `GET /api/v1/documents/{doc_id}`(메타 단건), `POST /api/v1/documents/ingest-text`(동기 적재) |
| Ingest alias | `POST /api/v1/policies/ingest` (전환기 alias) |
| Admin(운영) | `POST /api/admin/cleanup` (Soft Delete 물리 정리 워커) |

### 3.4 ⬜ bizplay-ai 에만 있는 URL

| 그룹 | 엔드포인트 | 제거 이유 |
|------|-----------|-----------|
| 법인그룹 | `/api/v1/corp-groups` (목록·단건·생성·수정·삭제, 5종) | 멀티테넌시를 **헤더 방식**으로 전환 → DB 관리 API 불필요 |
| 법인 | `/api/v1/corps` (목록·단건·생성·수정·삭제, 5종) | 〃 |
| 법인별 봇 | `GET /api/v1/bots/by-corp/{corp_no}` | `corp_no` 필터 대신 헤더 테넌트로 격리 |

---

## 4. 동일 URL의 기능 비교 (URL은 같으나 동작이 다른 것)

### 4.1 `DELETE /api/v1/bots/{bot_id}` — 가장 중요한 동작 차이

| | bizplay-ai | expense_ai_service |
|---|---|---|
| 방식 | **Hard delete** (cascade 즉시 삭제) | **Soft delete** — `status=DELETING` 전이만 |
| 실제 정리 | 요청 시점에 벡터+파일+행 즉시 제거 | 별도 워커(`POST /api/admin/cleanup`)가 비동기로 벡터→파일→행 정리 |
| 응답 | 삭제 완료 | `"삭제 예약됨(DELETING). 물리 정리는 워커가 수행합니다."` |

> 문서 삭제(`DELETE .../documents/{doc_id}`)도 동일하게 expense는 Soft Delete다.

### 4.2 `GET /health`

| | bizplay-ai | expense_ai_service |
|---|---|---|
| 헤더 | 불필요 | **`X-Company-ID` / `X-Workplace-ID` 필수** (누락 시 422) |
| 응답 | `{ "status": "ok" }` | `{ status, app, environment, tenant{company_id, workplace_id} }` |

### 4.3 `POST /api/v1/bots` (봇 생성)

URL·검증 규칙(temperature 0~1, max_answer_length 64~8192, history_turns 0~20, top_k 1~50)·"생성 직후 `disabled=true`"는 **동일**. 단 **테넌트 식별 방식**이 다르다 — bizplay는 Body `corp_no`, expense는 헤더 + `BotResponse` 에 `company_id`/`workplace_id` 포함.

### 4.4 문서 업로드 multipart 파라미터

| | bizplay-ai | expense_ai_service |
|---|---|---|
| 식별 | `bot_id` | `owner_id` + `domain`(기본 `"policy"`) |
| 추가 | — | `is_compliance_source` (컴플라이언스 근거 여부) |
| 임베딩 | 비동기(PROCESSING→COMPLETED/FAILED) | 비동기(동일) |

> 챗봇은 `domain="policy", owner_id=bot_id` 로 매핑되어 동작하고, 같은 문서 API를 컴플라이언스 엔진도 재사용한다.

---

## 5. 그 외 비교 포인트

| 항목 | bizplay-ai | expense_ai_service |
|------|-----------|--------------------|
| **서비스 정체성** | "BizPlay AI Chatbot API" — 순수 RAG 챗봇 | "Bizplay AI Compliance & Recommendation API" — 영수증추천 + 감사 **+** 챗봇 |
| **멀티테넌시** | DB 엔티티 `CorpGroup→Corp→Bot(corp_no soft ref)` | HTTP 헤더 `X-Company-ID`/`X-Workplace-ID` (+`X-Admin-ID`/`X-Employee-ID`) |
| **벡터 스토어** | pgvector (PostgreSQL 확장, HNSW, 코사인) | **Qdrant** (`QDRANT_URL`, Payload Filter 로 테넌트/봇 격리) |
| **문서 모듈 성격** | 챗봇 종속 (`bot_id` FK) | 도메인 비종속 공통 (`owner_id`+`domain`), 챗봇·컴플라이언스 공용 |
| **삭제 패턴** | 즉시 cascade hard delete | Soft Delete(`status=DELETING`) + cleanup 워커(`/api/admin/cleanup`) |
| **ApiResponse 래퍼** | 전 엔드포인트 통일 `{success,data,message,error}` | **부분 적용** — bots·chat·documents·admin 만 래핑. transactions·rules·compliance·policies(ingest)는 **bare DTO** |
| **에러 포맷** | ApiResponse `error` 필드 | 전역 핸들러가 `{ error_code, message }` 반환 (ApiResponse 와 별도) |
| **URL 버전 prefix** | 전부 `/api/v1/...` | 도메인은 `/api/v1/...`, 그러나 **compliance·admin 은 `/api/compliance`·`/api/admin`** (`/v1` 미적용) |
| **추가 헤더** | — | `X-Admin-ID`(소명 요청/처리/취소), `X-Employee-ID`(직원 소명) |
| **LLM Provider** | ollama/openai/anthropic/gemini 4종 추상화 | OpenAI 호환(RunPod vLLM, 예: Qwen) 중심, fastembed 로컬 임베딩 옵션 |

---

## 6. 마이그레이션 영향 & 권고

- **봇 관리 클라이언트**: 경로 그대로 재사용 가능. 단, 모든 요청에 `X-Company-ID`/`X-Workplace-ID` 헤더를 추가하고, body `corp_no` 의존 코드를 제거해야 한다.
- **채팅/문서 클라이언트**: `/rag/chat` → `/policies/chat`, `/rag/documents` → `/documents` 로 **경로 전면 수정** + 문서 파라미터(`bot_id` → `owner_id`+`domain`) 변경 필요.
- **삭제 로직**: 즉시 삭제를 가정한 코드가 있다면 Soft Delete(지연 정리)로 전제가 바뀐다. 삭제 직후 목록/검색에서 빠지지만 물리 정리는 워커 호출(`/api/admin/cleanup`) 후 완료된다.
- **응답 파싱**: expense 는 모듈별로 `ApiResponse` 래핑 여부가 갈린다(챗봇 계열만 래핑). 프론트엔드에서 응답 파싱 분기 필요.
- **운영 전 점검 권고**: ① `compliance`·`admin` 의 `/v1` 누락(버전 일관성), ② `admin/cleanup` 무인증(내부망/관리자 인증 보호), ③ ApiResponse 래핑 정책 통일 여부.

---

## 부록 A. expense_ai_service 전수 엔드포인트 (도메인 40 + 자동 3)

| # | Method | URL | 그룹 | ApiResponse |
|--:|--------|-----|------|:-----------:|
| 1 | GET | `/api/v1/rules/` | Rule | ✗ (bare) |
| 2 | POST | `/api/v1/rules/create` | Rule | ✗ |
| 3 | PUT | `/api/v1/rules/update/{rule_id}` | Rule | ✗ |
| 4 | POST | `/api/v1/transactions/test-single-transaction/create` | Transaction | ✗ |
| 5 | POST | `/api/v1/transactions/transaction/batch` | Transaction | ✗ |
| 6 | GET | `/api/v1/transactions/files/{file_id}/transactions` | Transaction | ✗ |
| 7 | PUT | `/api/v1/transactions/files/{file_id}/rows` | Transaction | ✗ |
| 8 | GET | `/api/v1/transactions/files/corp/{corp_no}/classify-summaries` | Transaction | ✗ |
| 9 | POST | `/api/v1/bots` | Bots | ✓ |
| 10 | GET | `/api/v1/bots` | Bots | ✓ |
| 11 | GET | `/api/v1/bots/{bot_id}` | Bots | ✓ |
| 12 | PUT | `/api/v1/bots/{bot_id}` | Bots | ✓ |
| 13 | PATCH | `/api/v1/bots/{bot_id}/enable` | Bots | ✓ |
| 14 | PATCH | `/api/v1/bots/{bot_id}/disable` | Bots | ✓ |
| 15 | DELETE | `/api/v1/bots/{bot_id}` | Bots | ✓ |
| 16 | GET | `/api/v1/bots/{bot_id}/statistics` | Bots | ✓ |
| 17 | GET | `/api/v1/bots/{bot_id}/statistics/daily` | Bots | ✓ |
| 18 | GET | `/api/v1/bots/{bot_id}/sessions` | Bots | ✓ |
| 19 | GET | `/api/v1/bots/{bot_id}/recommend` | Bots | ✓ |
| 20 | POST | `/api/v1/policies/chat` | Chat | ✓ |
| 21 | GET | `/api/v1/policies/chat/history/{session_id}` | Chat | ✓ |
| 22 | GET | `/api/v1/policies/chat/models` | Chat | ✓ |
| 23 | POST | `/api/v1/policies/ingest` | Ingest(alias) | ✗ |
| 24 | GET | `/api/v1/documents` | Documents | ✓ |
| 25 | POST | `/api/v1/documents/upload` | Documents | ✓ |
| 26 | POST | `/api/v1/documents/ingest-text` | Documents | ✓ |
| 27 | GET | `/api/v1/documents/{doc_id}` | Documents | ✓ |
| 28 | GET | `/api/v1/documents/{doc_id}/download` | Documents | ✗ (FileResponse) |
| 29 | DELETE | `/api/v1/documents/{doc_id}` | Documents | ✓ |
| 30 | GET | `/api/compliance/dashboard/kpi` | Compliance | ✗ |
| 31 | GET | `/api/compliance/dashboard/charts` | Compliance | ✗ |
| 32 | GET | `/api/compliance/transactions` | Compliance | ✗ |
| 33 | GET | `/api/compliance/transactions/export` | Compliance | ✗ (CSV) |
| 34 | POST | `/api/compliance/transactions/request-explanation` | Compliance | ✗ |
| 35 | POST | `/api/compliance/transactions/process-explanation` | Compliance | ✗ |
| 36 | POST | `/api/compliance/transactions/cancel-explanation` | Compliance | ✗ |
| 37 | GET | `/api/compliance/my/transactions` | Compliance | ✗ |
| 38 | POST | `/api/compliance/transactions/{transaction_id}/submit-explanation` | Compliance | ✗ |
| 39 | POST | `/api/admin/cleanup` | Admin | ✓ |
| 40 | GET | `/health` | System | ✗ |
| — | GET | `/docs` · `/redoc` · `/openapi.json` | System(자동) | — |

## 부록 B. bizplay-ai 전수 엔드포인트 (도메인 30 + 자동 3)

| # | Method | URL | 그룹 |
|--:|--------|-----|------|
| 1 | POST | `/api/v1/rag/chat` | Chat |
| 2 | GET | `/api/v1/rag/chat/models` | Chat |
| 3 | GET | `/api/v1/rag/chat/history/{session_id}` | Chat |
| 4 | POST | `/api/v1/rag/documents/upload` | Documents |
| 5 | GET | `/api/v1/rag/documents?bot_id={uuid}` | Documents |
| 6 | GET | `/api/v1/rag/documents/{doc_id}/download` | Documents |
| 7 | DELETE | `/api/v1/rag/documents/{doc_id}` | Documents |
| 8 | POST | `/api/v1/bots` | Bots |
| 9 | GET | `/api/v1/bots` | Bots |
| 10 | GET | `/api/v1/bots/by-corp/{corp_no}` | Bots |
| 11 | GET | `/api/v1/bots/{bot_id}` | Bots |
| 12 | PUT | `/api/v1/bots/{bot_id}` | Bots |
| 13 | PATCH | `/api/v1/bots/{bot_id}/enable` | Bots |
| 14 | PATCH | `/api/v1/bots/{bot_id}/disable` | Bots |
| 15 | DELETE | `/api/v1/bots/{bot_id}` | Bots |
| 16 | GET | `/api/v1/bots/{bot_id}/statistics` | Bots |
| 17 | GET | `/api/v1/bots/{bot_id}/statistics/daily` | Bots |
| 18 | GET | `/api/v1/bots/{bot_id}/sessions` | Bots |
| 19 | GET | `/api/v1/bots/{bot_id}/recommend` | Recommend |
| 20 | GET | `/api/v1/corp-groups` | CorpGroup |
| 21 | GET | `/api/v1/corp-groups/{group_id}` | CorpGroup |
| 22 | POST | `/api/v1/corp-groups` | CorpGroup |
| 23 | PUT | `/api/v1/corp-groups/{group_id}` | CorpGroup |
| 24 | DELETE | `/api/v1/corp-groups/{group_id}` | CorpGroup |
| 25 | GET | `/api/v1/corps?corp_group_id={id}` | Corp |
| 26 | GET | `/api/v1/corps/{corp_no}` | Corp |
| 27 | POST | `/api/v1/corps` | Corp |
| 28 | PUT | `/api/v1/corps/{corp_no}` | Corp |
| 29 | DELETE | `/api/v1/corps/{corp_no}` | Corp |
| 30 | GET | `/health` | System |
| — | GET | `/docs` · `/redoc` · `/openapi.json` | System(자동) |

> 참고: `bizplay-ai/docs/PROJECT_OVERVIEW.md` 본문은 합계를 "26개"로 표기하나, §3 엔드포인트 표를 그대로 집계하면 도메인 30종이다(by-corp·enable·disable 등 포함). 본 문서는 표 기준(30)을 사용한다.

---

*소스 코드 정적 분석 기반. expense_ai_service 라우팅은 `app/api/router.py`·`app/main.py`, bizplay-ai 는 `PROJECT_OVERVIEW.md` 기준.*
