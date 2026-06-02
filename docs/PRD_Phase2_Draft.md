# PRD Phase 2 (Draft) — 직원 소명 제출 + 기한 에스컬레이션 워크플로우

> 상태: **Draft (설계안)** · 대상: 백엔드 · 선행: Phase 1(11~16단계) 완료
> 목적: Phase 1 의 **관리자 주도** 소명 워크플로우를, **직원이 Bizplay 앱에서 직접 소명을 입력·제출**하고
> **소명 기한(due date)을 두어 미제출 건을 자동 에스컬레이션**하는 양방향 워크플로우로 확장한다.

---

## 1. 개요 / 목표

Phase 1 의 소명 상태(`explanation_status`)는 관리자만 전이시켰다(`미요청 → 요청완료 → 정상처리/위반확정`, 취소 시 `요청완료 → 미요청`).
Phase 2 는 다음을 추가한다.

1. **직원 소명 제출**: 위반(요청완료) 건에 대해 직원이 앱에서 해명 텍스트를 직접 입력·제출 → 신규 상태 `소명제출`.
2. **소명 기한(에스컬레이션)**: 관리자가 소명 요청 시 `due_date` 를 지정. 기한 내 미제출 시 스케줄러가 `기한초과` 로 자동 전이하고 관리자에게 알림.
3. **검토**: 관리자는 제출된 소명 내용을 보고 `정상처리`/`위반확정` 으로 종결.

> **선행 과제**: 현재 `ReceiptTransaction` 에는 개인 사용자(직원) 식별 필드가 없다(부서 `department` 만 존재).
> 직원 소명의 "본인 건" 격리를 위해 `employee_id`(사번/사용자 식별자) 컬럼 도입이 선행되어야 한다.

---

## 2. 데이터 모델 확장 (`ReceiptTransaction`)

| 컬럼 | 타입 | Nullable | 설명 |
|------|------|----------|------|
| `employee_id` | String(64) (index) | ✅ | **(선행)** 영수증 사용 직원 식별자. 직원 본인 건 조회/제출 격리 키 |
| `explanation_content` | Text | ✅ | 직원이 입력한 소명(해명) 본문 |
| `explanation_submit_dt` | DateTime | ✅ | 직원이 소명을 제출한 일시 |
| `explanation_submitter` | String(64) | ✅ | 소명 제출자(직원) 식별자 (감사용, 보통 `employee_id` 와 동일) |
| `due_date` | DateTime | ✅ | 소명 기한. 관리자가 요청 시 설정 |
| `is_escalated` | Boolean (default False, `server_default=text("true/false")`) | ❌ | 기한 초과 에스컬레이션 발생 여부 |

- `explanation_status` enum 값 확장: 기존 4개 + **`소명제출`**, **`기한초과`** 추가 (총 6개).
- 마이그레이션: `alembic revision --autogenerate -m "Add phase2 employee explanation fields"`.
  Boolean `server_default` 는 Phase 1 의 교훈대로 **`text("true"/"false")`** 로 작성(PostgreSQL 호환).

---

## 3. 상태 전이 (State Transition)

```
                         ┌────────────────────────── 관리자 cancel ───────────────────────────┐
                         ▼                                                                     │
   [위반탐지] ──auto──► 미요청 ──관리자 request(+due_date)──► 요청완료 ───────────────────────────┘
                                                              │
                          ┌───────── 직원 submit-explanation ─┤
                          ▼                                   │ due_date 경과 & 미제출 (스케줄러)
                       소명제출 ──────관리자 process───────┐    ▼
                          │                              │  기한초과 ──관리자 process──┐
                          │                              │                            │
                          ▼                              ▼                            ▼
                      정상처리                       정상처리 / 위반확정            위반확정(통상)
                      위반확정
```

**전이 표**

| 현재 상태 | 액션 | 주체 | 다음 상태 | 비고 |
|-----------|------|------|-----------|------|
| (위반탐지) | 자동 | 시스템 | `미요청` | Phase 1 compliance_node |
| `미요청` | request-explanation (+`due_date`) | 관리자 | `요청완료` | due_date 설정 |
| `요청완료` | submit-explanation | **직원** | `소명제출` | content/submit_dt 기록 |
| `요청완료` | cancel-explanation | 관리자 | `미요청` | 요청메타 초기화(Phase 1) |
| `요청완료` | (due_date 경과 & 미제출) | 스케줄러 | `기한초과` | `is_escalated=True` + 알림 |
| `소명제출` | process-explanation | 관리자 | `정상처리`/`위반확정` | 제출 내용 검토 후 종결 |
| `기한초과` | process-explanation | 관리자 | `위반확정`(통상)/`정상처리` | 소명 미제출 건 처리 |

> **불변식**: 직원 제출은 `요청완료`(또는 `기한초과`) 상태에서만 허용. 그 외 상태에서의 제출은 `409 Conflict`.

---

## 4. 신규 / 변경 API

### 직원용 (앱) — 신규
| Method | Path | 설명 |
|--------|------|------|
| `GET`  | `/api/compliance/my/transactions` | 로그인 직원 본인의 소명 대상(요청완료/기한초과) 목록 |
| `GET`  | `/api/compliance/my/transactions/{id}` | 본인 건 상세(요청 메시지/기한 포함) |
| `POST` | `/api/compliance/transactions/{id}/submit-explanation` | 소명 내용 제출 (`요청완료`→`소명제출`) |

- 직원 식별 헤더 신설: `X-Employee-ID` (또는 추후 사용자 인증 토큰). 본인 `employee_id` 와 일치하는 건만 접근(타인 건 404).
- 제출 payload: `{ "content": str }` → `explanation_content`/`explanation_submit_dt`/`explanation_submitter` 기록.

### 관리자용 — 변경/신규
| Method | Path | 변경 |
|--------|------|------|
| `POST` | `/api/compliance/transactions/request-explanation` | payload 에 **`due_date`** 추가 |
| `GET`  | `/api/compliance/transactions?status=소명제출` | 제출된 소명 검토 큐 (기존 그리드에 status 필터 재사용) |
| `GET`  | `/api/compliance/transactions/{id}` | 제출 내용(`explanation_content`) 포함 상세 |
| (배치) | — | 에스컬레이션 잡(스케줄러) — 아래 5절 |

> `process-explanation`/`cancel-explanation` 는 Phase 1 그대로 재사용(상태 전이 가드만 `소명제출`/`기한초과` 허용하도록 확장).

---

## 5. 에스컬레이션(기한) 처리 설계

- **트리거**: 주기적 스케줄러(예: APScheduler / Celery beat / 외부 cron + 내부 엔드포인트).
- **조건**: `explanation_status == '요청완료' AND due_date < now() AND explanation_submit_dt IS NULL`.
- **동작**: 해당 건을 `기한초과` 로 전이, `is_escalated=True`, 관리자 알림(이메일/푸시/웹훅) 발송.
- **멱등성**: 이미 `is_escalated=True` 인 건은 스킵. 테넌트별로 안전하게 배치 처리(트랜잭션 단위 커밋).
- **서비스 메서드**(신규): `ComplianceService.escalate_overdue(tenant | all) -> int` (전이 건수 반환).

---

## 6. 권한 / 보안

- **직원 API**: `(company_id, workplace_id, employee_id)` 3중 격리 — 본인 영수증만. 타인/타테넌트 건은 `404`(존재 비노출).
- **관리자 API**: Phase 1 의 `(company_id, workplace_id)` 격리 + `X-Admin-ID` 감사 추적 유지.
- 상태 전이는 **서버에서 강제**(클라이언트 신뢰 금지): 허용되지 않는 전이는 `409`.

---

## 7. 마이그레이션 / 하위호환

- 신규 컬럼은 전부 nullable(또는 안전한 `server_default`) → 기존 데이터 무중단 마이그레이션.
- `explanation_status` 는 String 컬럼이므로 enum 값 추가에 스키마 변경 불필요(애플리케이션 상수만 확장).
- Phase 1 의 관리자 워크플로우 동작은 그대로 유지(직원 제출은 선택적 경로로 삽입).

---

## 8. 작업 분해 (제안)

1. `employee_id` 컬럼 + 마이그레이션(선행)
2. Phase 2 컬럼 6종 + enum 값 2종 추가 + 마이그레이션
3. `submit-explanation` / 직원 조회 API + `ExplanationSubmitPayload` 스키마
4. `request-explanation` 에 `due_date` 확장
5. 에스컬레이션 스케줄러/배치 + `escalate_overdue` 서비스
6. pytest: 직원 제출/상태전이/기한초과/권한격리 테스트 추가 (Phase 1 conftest 재사용)
