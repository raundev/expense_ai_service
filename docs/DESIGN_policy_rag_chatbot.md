# 설계안 — Policy RAG Chatbot (chat · bots · recommend) + 공통 documents

> 참고 원본: `bizplay-ai/docs/PROJECT_OVERVIEW.md` (Spring AI→FastAPI 1:1 포팅 RAG 챗봇)
> 대상 서비스: `expense_ai_service` (Bizplay AI — Compliance & Recommendation API)
> 채택안: **(A) Bot = 테넌트 하위 엔티티** — 한 `(company_id, workplace_id)` 테넌트가 여러 봇을 보유
> 작성 기준일: 2026-06-04 · 상태: **설계 v3.1 — Critical Design Rules 명문화(아래) + 도메인/삭제 정책 확정(§12 참조)**

---

## 0. 한눈에 보기

| 참고문서 기능 | 우리 서비스에 녹이는 방식 | 신규/변경 |
|---|---|---|
| **chat** | Policy RAG API 확장: 세션·히스토리·sources·의도분류·재작성 | `policies.py` 확장 + 신규 서비스 |
| **bots** | 테넌트 하위 Bot 엔티티 신설 + CRUD/토글/통계/세션 | 신규 라우터·서비스·모델 |
| **recommend** | Bot 종속 추천 질문 | 신규 (bots 라우터 하위) |
| **documents** | **공통 서브시스템**으로 분리(중립 prefix) — policies·compliance·rules 공유 | 신규 라우터·서비스·모델 |

**핵심 원칙 (기존 코드 계승)**
- 멀티테넌시는 **헤더 `X-Company-ID`/`X-Workplace-ID`(`TenantContext`)** 가 단일 진실. 모든 신규 도메인 행은 `(company_id, workplace_id)` 를 직접 보유하고, 모든 조회는 이 키로 강제 격리한다.
- 벡터 격리는 **Qdrant 단일 컬렉션 + payload filter** 패턴을 그대로 확장한다 (컬렉션 분리 금지).
- LLM/임베딩은 기존 `OPENAI_API_BASE`(RunPod Qwen) + `SSL_CERT_FILE`(사내 CA) + `EMBEDDING_PROVIDER`(openai/fastembed) 정책을 재사용한다.
- RDB 는 동기 SQLAlchemy 2.0 + `get_db` 의존성, 마이그레이션은 alembic autogenerate(`Base.metadata`).

---

## ⚠️ Critical Design Rules (구현 절대 제약 — 위반 금지)

> 본 설계의 load-bearing 제약. 구현 주체(사람·AI 코딩 에이전트 공통)는 아래를 **절대 위반하지 않는다.** 각 규칙은 동기화된 구현 프롬프트의 "Critical Design Rules" 번호와 1:1 대응하며, 본문 해당 절과 연결된다.

1. **컴플라이언스 데이터 격리 — 도메인 + 메타데이터 이중 게이트.** 영수증 컴플라이언스 검증 RAG 는 반드시 **`domain="expense_rule" AND is_compliance_source=true`** 로만 검색한다. 챗봇 일반 규정(`domain="policy"`)을 컴플라이언스 컨텍스트에 **절대 섞지 않는다**(데이터 오염·환각 차단). → §2.2, §3, §8
2. **공통 Documents 모듈은 도메인 비종속.** Documents API·스키마·메타데이터는 **`owner_id` + `domain` 만** 사용하고, **`bot_id` 등 도메인 종속어를 표면에 노출하지 않는다.** 챗봇 외 주체(컴플라이언스 엔진 등)도 동일 API 로 문서를 소유·관리할 수 있어야 한다. → §2.2, §4.1
3. **의도분류 RAG Fallback — 환각 방지.** `HISTORY_ONLY` 로 분류되어도 **세션에 RAG 출처(sources) 컨텍스트가 없으면 강제로 `RETRIEVE`(벡터검색)로 폴백**한다. 검색 없이 LLM 이 규정을 지어내게 두지 않는다(첫 턴 '요약/단순화' 키워드 포함). → §5.3
4. **Soft Delete 강제 — Hard Delete 절대 금지.** 문서/봇 삭제는 **즉시 물리 삭제(Hard Delete)하지 않는다.** `status="DELETING"` 으로 전이(즉시 검색 제외)한 뒤, **백그라운드 워커만이** 벡터→파일→DB행 순으로 멱등 정리한다. AI 가 임의로 `DELETE FROM ...` 즉시 삭제 쿼리를 작성하는 것을 금한다. → §2.1, §2.2, §4.3
5. **모듈 분리 + 멀티테넌시 헤더 필수.** Policy RAG API(`/chat`·`/bots`·`/recommend`)와 Common Document API(`/documents`)를 **분리 유지**한다. 모든 도메인 API 는 `X-Company-ID`/`X-Workplace-ID` 헤더로 테넌트를 식별하고, **모든 조회·쓰기를 `(company_id, workplace_id)` 로 격리**한다(불일치 시 404). → §1, §7

---

## 1. 멀티테넌시 모델 — Bot 의 위치 (A안)

```
(company_id, workplace_id)  ← 테넌트 (헤더로 식별, 별도 테이블 없음)
        └── Bot (N)          ← 테넌트가 보유하는 챗봇. 봇별 LLM 설정 오버라이드
              ├── Document (N)              (domain="policy", owner_id=bot_id)  ※ 공통 모듈
              ├── ChatSession (N) → ChatMessage (N)
              └── RecommendedQuestion (N)
```

- 참고문서의 `CorpGroup→Corporation→Bot` 3계층은 우리의 `(company_id, workplace_id)→Bot` 2계층으로 축약된다. 별도 법인/법인그룹 테이블은 만들지 않는다(헤더가 그 역할).
- 따라서 참고문서의 `GET /bots`(전체)·`GET /bots/by-corp/{corp_no}` 두 엔드포인트는 우리에선 **`GET /bots` 하나**로 합쳐진다 — 헤더 테넌트 범위가 곧 corp 필터다.
- **격리 불변식**: 모든 Bot/Document/Session/Message 접근은 행의 `(company_id, workplace_id)` 가 요청 헤더와 일치할 때만 허용. 불일치는 **404**(존재 누출 방지). 비활성 봇으로의 chat 은 **409**.

---

## 2. 데이터 모델 (신규 테이블 5개)

PK 는 외부 노출(URL)·참고문서 정합성을 위해 **`String(36)` UUID(uuid4, 앱 생성)** 로 통일한다(SQLite/PostgreSQL 양쪽 호환). 기존 영수증 계열 테이블(int PK)은 변경하지 않는다.

### 2.1 `bots`
| 컬럼 | 타입 | 제약 / 기본 |
|---|---|---|
| `id` | String(36) | PK (uuid4) |
| `company_id` / `workplace_id` | String(64) | index, not null (테넌트) |
| `name` | String(255) | not null |
| `llm_model` | String(128) | not null |
| `llm_temperature` | Float | default 0.0 (검증 0~1) |
| `max_answer_length` | Integer | default 2048 (검증 64~8192) |
| `history_turns` | Integer | default 5 (검증 0~20) |
| `top_k` | Integer | default 5 (검증 1~50) |
| `system_prompt` | Text | nullable (없으면 기본 시스템 프롬프트) |
| `source_expose` | Boolean | default true |
| `disabled` | Boolean | default **true** (생성 직후 비활성), server_default `text("true")` |
| `status` | String(16) | default `"ACTIVE"` — Soft Delete 시 `"DELETING"`(§4.3). 조회/chat 에서 즉시 제외 |
| `created_at` / `updated_at` | DateTime | utcnow |

- 유니크: `(company_id, workplace_id, name)` — 테넌트 내 봇 이름 중복 방지.

### 2.2 `documents` (공통 — 도메인 비종속)
| 컬럼 | 타입 | 제약 / 기본 |
|---|---|---|
| `id` | String(36) | PK (uuid4) → URL 의 `doc_id` |
| `company_id` / `workplace_id` | String(64) | index, not null |
| `domain` | String(32) | not null, index, default `"policy"` — 예: `policy`(챗봇 일반규정), `expense_rule`(경비/컴플라이언스) |
| `owner_id` | String(36) | nullable, index — policy 도메인에서는 **bot_id (soft ref)**, expense_rule 은 컴플라이언스 엔진 식별자 등 |
| `is_compliance_source` | Boolean | default false, index — 영수증 자동검증 RAG 의 근거 문서 표식. **벡터 payload 에도 동일 저장**(§8) |
| `title` | String(255) | not null |
| `file_name` | String(255) | nullable (텍스트 적재 시 null) |
| `file_path` | String(512) | nullable |
| `content_type` | String(128) | nullable |
| `byte_size` | Integer | nullable |
| `source_name` | String(255) | 출처 표기(검색 source) |
| `embedding_status` | String(16) | not null, default `"PROCESSING"` (`PROCESSING`/`COMPLETED`/`FAILED`/`DELETING`) |
| `error_message` | String(1024) | nullable (FAILED 사유) |
| `chunk_count` | Integer | default 0 |
| `created_at` / `updated_at` | DateTime | utcnow |

- `owner_id` 를 **하드 FK 가 아닌 soft reference** 로 둔 것이 "공통"의 핵심: bot 이 없는 미래 도메인(예: compliance 참고자료, rule 가이드)도 같은 테이블을 `domain`/`owner_id` 만 바꿔 재사용한다. (참고문서의 `Bot.corp_no` soft ref 와 동일한 발상)
- bot 삭제 시 documents 정리는 FK CASCADE 가 아니라 **서비스 레벨**에서 `(domain="policy", owner_id=bot_id)` 로 일괄 삭제(벡터·파일 포함). 삭제 순서/정합성은 §4.3 참조.

### 2.3 `chat_sessions`
| 컬럼 | 타입 | 제약 |
|---|---|---|
| `id` | String(36) | PK → `session_id` |
| `company_id` / `workplace_id` | String(64) | index, not null |
| `bot_id` | String(36) | FK→`bots.id` (ondelete CASCADE), index, not null |
| `channel` | String(16) | default `"web"` |
| `created_at` / `updated_at` | DateTime | utcnow |

### 2.4 `chat_messages`
| 컬럼 | 타입 | 제약 |
|---|---|---|
| `id` | String(36) | PK |
| `session_id` | String(36) | FK→`chat_sessions.id` (CASCADE), index, not null |
| `role` | String(16) | not null (`user`/`assistant`) |
| `content` | Text | not null |
| `input_tokens` / `output_tokens` | Integer | default 0 |
| `sources_json` | Text(JSON) | nullable — assistant 메시지의 sources 스냅샷(히스토리 재구성용) |
| `created_at` | DateTime | utcnow |

### 2.5 `bot_recommended_questions`
| 컬럼 | 타입 | 제약 |
|---|---|---|
| `id` | String(36) | PK |
| `bot_id` | String(36) | FK→`bots.id` (CASCADE), index, not null |
| `question` | String(512) | not null |
| `sort_order` | Integer | default 0 |
| `created_at` | DateTime | utcnow |

**Cascade 주의(SQLite)**: SQLite 는 기본적으로 FK 를 강제하지 않으므로, ORM relationship `cascade="all, delete-orphan"` 로 파이썬 레벨 삭제를 보장하거나 `PRAGMA foreign_keys=ON` 이벤트 리스너를 건다. PostgreSQL 은 DB FK CASCADE 가 동작. documents 는 soft ref 라 어느 쪽이든 서비스에서 명시 삭제.

---

## 3. 벡터 스토어 변경 (`app/ai/vector_store.py`)

- **단일 컬렉션 유지**, 다만 "공통 문서 저장소"로 의미가 확장되므로 컬렉션명을 `company_policies` → **`tenant_documents`** 로 변경 권장(테스트 단계라 재적재 허용). *(컬렉션명은 격리에 영향 없음 — 부담되면 기존명 유지 가능, §10 결정사항)*
- 청크 metadata 스키마 확장 (격리·필터·sources 표시에 사용):
  ```json
  {
    "company_id": "...", "workplace_id": "...",
    "domain": "policy | expense_rule", "owner_id": "<owner>",
    "is_compliance_source": false,
    "doc_id": "<document.id>", "source": "<source_name>",
    "title": "<document.title>", "chunk_index": 0
  }
  ```
- **doc_id 단위 삭제**: 문서 삭제 시 `client.delete(collection, points_selector=FilterSelector(filter=metadata.doc_id == doc_id))` 로 해당 청크만 제거(언더라잉 `QdrantVectorStore.client` 사용). 파일 락/싱글 프로세스(임베디드) 제약은 동일 프로세스라 무방.
- 임베딩 차원은 기존대로 probe 산출 — 참고문서의 `vector(768)` 차원 불일치 이슈는 우리에겐 비해당.

---

## 4. 공통 documents 모듈 (신규)

신규 파일: `app/models/documents.py`, `app/schemas/documents.py`, `app/services/document_service.py`, `app/api/endpoints/documents.py`.

### 4.1 엔드포인트 — `/api/v1/documents` [tag: Documents API]
| Method | Path | 설명 | 입력 |
|---|---|---|---|
| POST | `/documents/upload` | 파일 업로드(비동기 임베딩) `201` | multipart: `file`, `title`, `owner_id`, `domain`?(기본 policy), `is_compliance_source`?(기본 false) |
| POST | `/documents/ingest-text` | 텍스트 즉시 적재(동기) `201` | JSON: `{ text, source_name, owner_id, domain?, is_compliance_source? }` |
| GET | `/documents?domain={}&owner_id={}` | 테넌트+필터 문서 목록 | query |
| GET | `/documents/{doc_id}` | 단건 메타/상태 | path |
| GET | `/documents/{doc_id}/download` | 원본 파일 다운로드 | path |
| DELETE | `/documents/{doc_id}` | **Soft Delete**(status=DELETING) → 워커가 벡터+파일+행 정리(§4.3) | path |

> 공통 모듈의 API 표면에서는 도메인 종속어(`bot_id`)를 쓰지 않고 **범용 `owner_id`+`domain`** 으로 통일한다(리뷰 반영). policy 흐름에서는 `domain="policy"`, `owner_id=<bot_id>` 로 호출한다(OpenAPI 설명에 "policy 도메인의 owner_id=봇 UUID" 명시). 이것이 타 모듈(영수증 등) 재사용 시 의미 혼란을 막는다.

### 4.2 비동기 임베딩 라이프사이클 (FastAPI `BackgroundTasks`)
1. 파일을 `uploads/{company_id}/{workplace_id}/{doc_id}/{원본파일명}` 에 저장(테넌트 격리 경로).
2. `documents` 행 생성 `status=PROCESSING`, commit → **즉시 201 반환** `{doc_id, embedding_status}`.
3. 백그라운드: 파싱(PDF=`pypdf`, DOCX=`python-docx`, 그 외 텍스트) → 청킹(`RecursiveCharacterTextSplitter`, 기존 500/50) → metadata 부여 임베딩 → `add_texts` → `status=COMPLETED`+`chunk_count`. 예외 시 `status=FAILED`+`error_message`.
   - **백그라운드는 요청 세션이 닫힌 뒤 실행** → 태스크 내부에서 `SessionLocal()` 새로 열어 상태 갱신.
4. `ingest-text` 는 동기 처리(짧은 텍스트) → 생성 즉시 `COMPLETED`.

### 4.3 삭제 (Soft Delete + 백그라운드 워커) — 확정
'좀비 벡터'(DB 는 지워졌는데 벡터가 남아 **삭제된 규정이 답변·컴플라이언스에 재노출**되는 정합성 사고)를 막기 위해 **하드 딜리트 대신 Soft Delete** 로 처리한다:
1. **즉시 격리**: 삭제 요청 시 `documents.embedding_status="DELETING"`(봇은 `bots.status="DELETING"`) 로 표시하고 응답 반환. **모든 검색·목록(chat·compliance·documents 조회)은 DELETING 을 즉시 제외** → 삭제 콘텐츠 재노출 차단(정확성 *즉시* 확보).
2. **백그라운드 워커**: DELETING 항목을 집어 ① Qdrant 벡터(doc_id 필터, **멱등** delete) → ② 디스크 파일 → ③ DB 행(마지막) 순으로 안전하게 제거하고 최종 완료 처리. 실패 항목은 DELETING 으로 남아 다음 주기에 멱등 재시도 → 물리적 최종 정합(eventual consistency) 보장.
3. **봇 삭제 연쇄**: 봇이 DELETING 이 되면 소속 documents 를 모두 DELETING 으로 전이 → 워커가 각 문서의 벡터/파일 정리 후, 잔여 문서가 없으면 봇 행 + DB 종속(sessions/messages/recommended) 까지 제거.
> 워커는 주기적 스케줄러(또는 큐 소비자)로 구동. 즉시 격리(1)가 정확성을, 워커(2)가 물리적 정합을 보장하는 2단 구조다.

---

## 5. Policy RAG — chat 확장 (`app/api/endpoints/policies.py`)

### 5.1 엔드포인트 [tag: Policy RAG API]
| Method | Path | 설명 |
|---|---|---|
| POST | `/policies/chat` | RAG 채팅(메인) — 계약 변경 |
| GET | `/policies/chat/history/{session_id}` | 세션 히스토리 |
| GET | `/policies/chat/models` | 사용 가능 LLM 모델 목록 |

**요청** `{ bot_id, query, session_id?, channel? }` → **응답** `{ answer, session_id, sources[] }`
`sources[]`: `{ doc_id, title, file_name, snippet(≤300), score, chunk_index, document_url }`
`document_url` = `/api/v1/documents/{doc_id}/download`.

### 5.2 8단계 파이프라인 (참고문서 → 우리 환경 적응)
1. **봇 검증** — 테넌트 내 존재 확인, `disabled` 면 `409`.
2. **세션 조회/생성** — `session_id` 없으면 신규(채널 기본 `web`). 있으면 bot+테넌트 소속 검증(불일치 404).
3. **히스토리 로드** — 최근 `bot.history_turns` 턴, 메시지당 최대 4000자 절단.
4. **의도 분류** — `RETRIEVE` vs `HISTORY_ONLY`(번역·요약·형식변환 등 순수 변환). → 신규 `app/services/query_reformulation.py`.
5. **검색어 재작성** — 지시대명사("그거","위 항목","that") 후속질문을 히스토리로 독립 검색어 재작성.
6. **벡터 검색** — `company_id+workplace_id+domain="policy"+owner_id(bot_id)` 필터, `k=bot.top_k`.
7. **(선택) 리랭킹** — 현 단계 stub(미적용), 추후 vLLM reranker 훅. *(참고문서도 stub)*
8. **LLM 생성 → 메시지 저장 → sources 첨부** — `bot.system_prompt`/`temperature`/`max_answer_length` 적용. usage 토큰을 assistant 메시지에 기록.

**sources 노출 규칙**: `bot.source_expose=false` 이거나 답변이 `_NO_CONTEXT_ANSWER`("관련된 사내 규정을 찾을 수 없습니다.") 류이면 sources 숨김(기존 상수 재사용).

### 5.3 의도분류/재작성 (경량 구현)
- Tier-1 정규식: 번역/요약/단순화/형식변환 키워드 → `HISTORY_ONLY` **후보**(검색 생략, 히스토리만으로 응답 → 비용 절감).
- **첫 턴 폴백(필수 안전장치, 리뷰 반영)**: `HISTORY_ONLY` 는 *이미 검색된 출처 컨텍스트를 가공하는 후속질문*일 때만 유효하다. **세션에 source 가 실린 직전 컨텍스트가 없으면**(첫 질문이거나 이력에 sources 없음) 키워드와 무관하게 **강제로 `RETRIEVE` 로 폴백**한다. (예: 첫 질문 "사내 식대 규정 요약해줘" → '요약' 키워드여도 검색 수행, 환각 방지.) 폴백 시 재작성 단계에서 변환 동사를 제거하고 핵심 주제어를 추출해 검색 품질을 높인다.
- 그 외 기본 `RETRIEVE`. (참고문서의 임베딩 코사인 Tier-2 는 추후 고도화 — 우선 정규식+기본값.)
- 재작성은 히스토리가 있고 지시어가 있을 때만 LLM 1콜.

### 5.4 `/chat/models`
- 우리 환경은 단일 Qwen 중심 → `settings.LLM_MODEL` + 설정상 대체 모델 목록 반환(`{ models: [...] }`).

---

## 6. Policy RAG — bots (신규 `app/api/endpoints/bots.py`, `app/services/bot_service.py`)

### 6.1 엔드포인트 — `/api/v1/bots` [tag: Policy RAG API]
| Method | Path | 설명 |
|---|---|---|
| POST | `/bots` | 생성(`201`, 생성 시 비활성) |
| GET | `/bots` | 테넌트 봇 목록 (name ASC) |
| GET | `/bots/{bot_id}` | 단건 조회 |
| PUT | `/bots/{bot_id}` | 설정 수정(PATCH 시맨틱) |
| PATCH | `/bots/{bot_id}/enable` | 활성화 |
| PATCH | `/bots/{bot_id}/disable` | 비활성화 |
| DELETE | `/bots/{bot_id}` | **Soft Delete**(status=DELETING) → 워커가 문서 벡터/파일 정리 후 봇·세션·메시지·추천질문 제거(§4.3) |
| GET | `/bots/{bot_id}/statistics` | 통계 |
| GET | `/bots/{bot_id}/statistics/daily?window_days=7` | 일별 통계(1~90) |
| GET | `/bots/{bot_id}/sessions` | 봇 세션 목록 |
| GET | `/bots/{bot_id}/recommend` | 추천 질문 목록 |

- `BotCreateRequest`/`BotUpdateRequest` 는 참고문서 검증 규칙 계승(§2.1 제약). `recommended_questions: list[str]` 를 create/update 에서 함께 받아 `bot_recommended_questions` 동기화 → recommend 는 조회 전용.
- **라우트 등록 순서**: `/bots/{bot_id}/statistics/daily` 등 하위 정적 세그먼트는 `/{bot_id}` 와 충돌하지 않음(완전 경로 매칭). 단 동일 라우터 내 정적 경로를 파라미터 경로보다 먼저 등록하는 관례는 유지.

### 6.2 통계 산출
- `statistics`: 문서 수(domain=policy, owner_id=bot) / 세션 수 / 메시지 수 / `sum(input_tokens)` / `sum(output_tokens)` — 전부 bot+테넌트 필터.
- `statistics/daily`: 최근 N일 세션 수. **DB 비종속**을 위해 `created_at >= cutoff` 행을 가져와 파이썬에서 날짜 버킷팅(SQLite/PG 의 date 함수 차이 회피).

### 6.3 recommend
- `GET /bots/{bot_id}/recommend` → `sort_order ASC` 질문 목록. UI 초기화면용.

---

## 7. 라우팅 & OpenAPI 태그 (`app/api/router.py`, `app/main.py`)

```python
api_router.include_router(bots.router,      prefix="/v1/bots",      tags=["Policy RAG API"])
api_router.include_router(policies.router,  prefix="/v1/policies",  tags=["Policy RAG API"])  # chat 확장
api_router.include_router(documents.router, prefix="/v1/documents", tags=["Documents API"])
# 기존: rules, transactions, compliance 유지
```
- bots/chat/recommend 은 **Policy RAG API 태그로 묶어** "Policy RAG API 내 구현" 요구를 충족(경로는 REST 청결성을 위해 `/v1/bots`). documents 는 공통이므로 별도 **Documents API** 태그.
- `OPENAPI_TAGS` 에 `Documents API` 설명 추가.

---

## 8. 컴플라이언스와의 관계 (`app/services/policy_service.py`)

- **도메인 분리 + 메타데이터 플래그를 함께 적용(확정).** 컴플라이언스 기준 문서는 일반 챗봇 문서(`domain="policy"`)와 분리된 **전용 도메인 `domain="expense_rule"`** 로 적재하고, 동시에 문서·청크에 **`is_compliance_source=true`** 표식을 부여한다(벡터 payload 저장).
- `check_compliance` 벡터 필터: **`company_id + workplace_id + domain=="expense_rule" + is_compliance_source==true`**. 인사/IT/복지(`domain="policy"`) 규정이 영수증 검증 컨텍스트에 딸려오는 것을 **원천 차단**(이중 게이트: 도메인=주제 격리, 플래그=근거 문서 지정).
- 컴플라이언스는 **bot/owner 에 종속되지 않는다** — `expense_rule`+플래그만으로 식별하므로, 기준 문서의 `owner_id` 는 챗봇이 아니라 컴플라이언스 엔진 식별자(또는 미지정)여도 된다(공통 documents 모듈의 `owner_id` 범용성 활용).
- chat 검색은 종전대로 `domain="policy" + owner_id(bot_id)` 로 격리 → 두 경로가 같은 저장소를 공유하되 필터로 완전 분리.
- **마이그레이션 영향(알아둘 것)**: 기존 `/policies/ingest` 로 적재된 `policy` 문서는 더 이상 컴플라이언스 검색 대상이 아니다. 컴플라이언스가 동작하려면 경비/지출 사칙을 `domain="expense_rule"`, `is_compliance_source=true` 로 (재)적재해야 하며, 적재 전에는 기준 문서 0건 → 기존 **fail-open** 으로 통과한다.
- 기존 `ask_policy` 의 `_tenant_filter` 는 chat 경로이므로 `domain="policy"` 로 일관화.

---

## 9. 마이그레이션 · 의존성 · 호환성

### 9.1 alembic
1. 신규 모델 5개를 `app/models/__init__.py` 에 import/`__all__` 등록(autogenerate 인식).
2. `alembic revision --autogenerate -m "add rag chatbot tables (bots, documents, sessions, messages, recommended_questions)"`.
3. `alembic upgrade head` (api 컨테이너 기동 시 자동 적용 경로 동일).

### 9.2 requirements 추가
```
pypdf          # PDF 파싱
python-docx    # DOCX 파싱
```
> 로컬 통과·CI 실패 함정 회피: 신규 직접 import 패키지는 반드시 requirements 에 추가하고 클린 venv 로 검증.

### 9.3 변경 영향 (Breaking) — 테스트 단계라 수용
- **`/policies/chat` 계약 변경**: `bot_id` 필수 추가. 프론트 테스트 콘솔에 **봇 선택 + 봇 CRUD UI** 필요. → 완충책으로 테넌트별 **기본 봇 시드 헬퍼**(`ensure_default_bot`) 제공 고려(§10). *(컴플라이언스는 봇이 아니라 `expense_rule`+`is_compliance_source` 문서로 동작 — 시드 봇과 무관, §8 마이그레이션 영향 참조.)*
- **`/policies/ingest`**: 공통 `documents/ingest-text` 로 이관. 기존 경로는 한시적 alias(내부적으로 `domain=policy`, `owner_id=bot_id` 위임) 후 제거.
- **벡터 컬렉션 rename(선택)**: 테스트 환경 재적재 1회.

---

## 10. 미해결 결정 사항 (착수 전 확인)

| # | 결정 | 권장안 |
|---|---|---|
| D1 | bots 경로: `/v1/bots`(참고 parity) vs `/v1/policies/bots`(엄격 중첩) | **`/v1/bots`** + Policy RAG API 태그 |
| D2 | 벡터 컬렉션 rename `company_policies`→`tenant_documents` | **rename**(테스트 재적재) — 부담 시 기존명 유지 가능 |
| D3 | 컴플라이언스 검색 범위 (**확정**) | `domain="expense_rule"` + `is_compliance_source=true` **둘 다** 적용(§8) |
| D4 | 신규 PK 타입 | **String(36) UUID** 통일 |
| D5 | 기본 봇 시드(`ensure_default_bot`)로 chat 마이그레이션 완충 | **제공**(프론트 봇선택 UI 와 병행) |

---

## 11. 구현 단계 (제안)

- **Phase A — 도메인/스키마 기반**: 모델 5개 + alembic 마이그레이션 + Bot CRUD/enable/disable + recommend(+ 테스트).
- **Phase B — 공통 documents**: document_service/router + 파일 파싱 + 비동기 임베딩 + 벡터 metadata 확장 + doc_id 삭제. `ingest-text` 이관.
- **Phase C — chat**: 세션/메시지 영속 + bot 필터 검색 + sources + source_expose + `/chat/history` + `/chat/models`.
- **Phase D — 지능화/운영**: 의도분류·재작성 + statistics/daily + 컴플라이언스 도메인 필터 + 프론트 테스트 콘솔(봇 관리/문서 업로드/소스 표시) 갱신.

---

## 12. 설계 리뷰 반영 (2026-06-04, v3 — 최종 확정)

| 지적 | 처리 | 반영 위치 |
|---|---|---|
| ① 공통 Documents API 에 `bot_id` 종속어 노출 | **수용** — 전 파라미터 `owner_id`+`domain` 으로 통일 | §4.1 |
| ② 컴플라이언스 검색 범위 과대 | **수용·확정** — `domain="expense_rule"`(도메인 분리) **AND** `is_compliance_source=true`(문서·payload 플래그) 이중 게이트. 플래그는 봇이 아니라 **문서** 속성으로 확정 | §8, §2.2, §3, §10 D3 |
| ③ HISTORY_ONLY 첫 턴 맹점(검색 생략→환각) | **수용** — source 컨텍스트 없으면 강제 `RETRIEVE` 폴백 | §5.3 |
| ④ 삭제 실패 시 좀비 벡터 | **수용·확정** — **Soft Delete(`status="DELETING"`) + 백그라운드 워커** 채택. 즉시 격리로 정확성, 워커로 물리적 최종 정합 | §4.3, §2.1, §2.2 |

> 4개 지적 모두 최종 설계 원칙으로 확정(사용자 결정). ②는 도메인+플래그 이중 적용, ④는 Soft Delete+워커 구조.

---

## 부록. 신규/변경 파일 맵
```
app/
├─ models/
│   ├─ bots.py                 (신규) Bot, BotRecommendedQuestion
│   ├─ documents.py            (신규) Document  ※ 공통
│   ├─ chat.py                 (신규) ChatSession, ChatMessage
│   └─ __init__.py             (변경) 신규 모델 등록(autogenerate)
├─ schemas/
│   ├─ bots.py / documents.py / chat.py   (신규)
│   └─ policies.py             (변경) ChatRequest/Response 에 bot_id·session_id·sources
├─ services/
│   ├─ bot_service.py          (신규)
│   ├─ document_service.py     (신규) ※ 공통
│   ├─ chat_service.py         (신규) 8단계 파이프라인
│   ├─ query_reformulation.py  (신규) 의도분류·재작성
│   └─ policy_service.py       (변경) domain="policy" 필터, chat 로직은 chat_service 로 이관
├─ api/endpoints/
│   ├─ bots.py / documents.py  (신규)
│   └─ policies.py             (변경) chat/history/models
├─ ai/vector_store.py          (변경) 컬렉션명·metadata 확장·doc_id 삭제 헬퍼
└─ api/router.py               (변경) bots/documents 라우터 등록
alembic/versions/xxxx_*.py     (신규) 테이블 5개
requirements.txt               (변경) pypdf, python-docx
```
