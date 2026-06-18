<!-- AUTO-GENERATED — 손으로 수정하지 말 것. 생성: python scripts/gardening/gen-db-schema.py -->
# DB 스키마 (자동 생성)

SQLAlchemy `Base.metadata` 에서 추출. ⚠ 는 멀티테넌트 컬럼(company_id/workplace_id) 누락 신호(GP-1).

## `approval_history`

| 컬럼 | 타입 | NULL | 키/비고 |
|------|------|------|---------|
| id | INTEGER | N | PK |
| company_id | VARCHAR(64) | N | idx |
| workplace_id | VARCHAR(64) | N | idx |
| user_id | VARCHAR(64) | N |  |
| receipt_amount | INTEGER | N |  |
| receipt_merchant | VARCHAR(255) | N |  |
| receipt_date | DATETIME | N |  |
| approved_category | VARCHAR(255) | N |  |
| rejection_reason | VARCHAR(512) | Y |  |
| status | VARCHAR(32) | N |  |

_인덱스_: ix_approval_history_company_id(company_id); ix_approval_history_workplace_id(workplace_id)

## `bots`

| 컬럼 | 타입 | NULL | 키/비고 |
|------|------|------|---------|
| id | VARCHAR(36) | N | PK |
| company_id | VARCHAR(64) | N | idx |
| workplace_id | VARCHAR(64) | N | idx |
| name | VARCHAR(255) | N |  |
| llm_model | VARCHAR(128) | N |  |
| llm_temperature | FLOAT | N |  |
| max_answer_length | INTEGER | N |  |
| history_turns | INTEGER | N |  |
| top_k | INTEGER | N |  |
| system_prompt | TEXT | Y |  |
| source_expose | BOOLEAN | N |  |
| disabled | BOOLEAN | N |  |
| status | VARCHAR(16) | N |  |
| created_at | DATETIME | N |  |
| updated_at | DATETIME | N |  |

_인덱스_: ix_bots_company_id(company_id); ix_bots_workplace_id(workplace_id)

## `company_receipt_rules`

| 컬럼 | 타입 | NULL | 키/비고 |
|------|------|------|---------|
| id | INTEGER | N | PK |
| company_id | VARCHAR(64) | N | idx |
| workplace_id | VARCHAR(64) | Y | idx |
| rule_name | VARCHAR(255) | N |  |
| condition_keyword | VARCHAR(255) | Y |  |
| condition_min_amount | INTEGER | Y |  |
| condition_max_amount | INTEGER | Y |  |
| is_weekend | BOOLEAN | Y |  |
| is_holiday | BOOLEAN | Y |  |
| usage_time_band | VARCHAR(32) | Y |  |
| card_company_code | VARCHAR(32) | Y |  |
| merchant_sector_code | VARCHAR(32) | Y |  |
| merchant_sector_name | VARCHAR(255) | Y |  |
| category_code | VARCHAR(32) | N |  |
| result_category | VARCHAR(255) | N |  |
| priority | INTEGER | N |  |
| is_active | BOOLEAN | N |  |

_인덱스_: ix_company_receipt_rules_company_id(company_id); ix_company_receipt_rules_workplace_id(workplace_id)

## `documents`

| 컬럼 | 타입 | NULL | 키/비고 |
|------|------|------|---------|
| id | VARCHAR(36) | N | PK |
| company_id | VARCHAR(64) | N | idx |
| workplace_id | VARCHAR(64) | N | idx |
| domain | VARCHAR(32) | N | idx |
| owner_id | VARCHAR(36) | Y | idx |
| is_compliance_source | BOOLEAN | N | idx |
| title | VARCHAR(255) | N |  |
| file_name | VARCHAR(255) | Y |  |
| file_path | VARCHAR(512) | Y |  |
| content_type | VARCHAR(128) | Y |  |
| byte_size | INTEGER | Y |  |
| source_name | VARCHAR(255) | N |  |
| embedding_status | VARCHAR(16) | N |  |
| error_message | VARCHAR(1024) | Y |  |
| chunk_count | INTEGER | N |  |
| created_at | DATETIME | N |  |
| updated_at | DATETIME | N |  |

_인덱스_: ix_documents_company_id(company_id); ix_documents_domain(domain); ix_documents_is_compliance_source(is_compliance_source); ix_documents_owner_id(owner_id); ix_documents_workplace_id(workplace_id)

## `receipt_files`

| 컬럼 | 타입 | NULL | 키/비고 |
|------|------|------|---------|
| id | INTEGER | N | PK |
| company_id | VARCHAR(64) | N | idx |
| workplace_id | VARCHAR(64) | N | idx |
| file_name | VARCHAR(255) | N |  |
| upload_time | DATETIME | N |  |
| total_count | INTEGER | N |  |

_인덱스_: ix_receipt_files_company_id(company_id); ix_receipt_files_workplace_id(workplace_id)

## `tenants`

| 컬럼 | 타입 | NULL | 키/비고 |
|------|------|------|---------|
| id | VARCHAR(36) | N | PK |
| company_id | VARCHAR(64) | N | idx |
| workplace_id | VARCHAR(64) | N | idx |
| company_name | VARCHAR(255) | Y |  |
| workplace_name | VARCHAR(255) | Y |  |
| status | VARCHAR(16) | N |  |
| created_at | DATETIME | N |  |
| updated_at | DATETIME | N |  |

_인덱스_: ix_tenants_company_id(company_id); ix_tenants_workplace_id(workplace_id)

## `bot_recommended_questions`  ⚠ 테넌트 컬럼 없음

| 컬럼 | 타입 | NULL | 키/비고 |
|------|------|------|---------|
| id | VARCHAR(36) | N | PK |
| bot_id | VARCHAR(36) | N | FK→bots.id, idx |
| question | VARCHAR(512) | N |  |
| sort_order | INTEGER | N |  |
| created_at | DATETIME | N |  |

_인덱스_: ix_bot_recommended_questions_bot_id(bot_id)

## `chat_sessions`

| 컬럼 | 타입 | NULL | 키/비고 |
|------|------|------|---------|
| id | VARCHAR(36) | N | PK |
| company_id | VARCHAR(64) | N | idx |
| workplace_id | VARCHAR(64) | N | idx |
| bot_id | VARCHAR(36) | N | FK→bots.id, idx |
| channel | VARCHAR(16) | N |  |
| created_at | DATETIME | N |  |
| updated_at | DATETIME | N |  |

_인덱스_: ix_chat_sessions_bot_id(bot_id); ix_chat_sessions_company_id(company_id); ix_chat_sessions_workplace_id(workplace_id)

## `receipt_transactions`

| 컬럼 | 타입 | NULL | 키/비고 |
|------|------|------|---------|
| id | INTEGER | N | PK |
| file_id | INTEGER | N | FK→receipt_files.id, idx |
| company_id | VARCHAR(64) | N | idx |
| workplace_id | VARCHAR(64) | N | idx |
| department | VARCHAR(255) | Y | idx |
| employee_id | VARCHAR(64) | Y | idx |
| receipt_date | DATE | N |  |
| receipt_time | VARCHAR(8) | N |  |
| merchant_name | VARCHAR(255) | N |  |
| merchant_sector_code | VARCHAR(32) | Y |  |
| amount | INTEGER | N |  |
| recommended_category_code | VARCHAR(64) | N |  |
| recommended_result_category | VARCHAR(255) | N |  |
| applied_rule_id | INTEGER | Y |  |
| match_type | VARCHAR(16) | N |  |
| llm_suggested_code | VARCHAR(64) | Y |  |
| llm_suggested_name | VARCHAR(255) | Y |  |
| is_manually_modified | BOOLEAN | N |  |
| is_compliant | BOOLEAN | N |  |
| violation_reason | VARCHAR(1024) | Y |  |
| explanation_status | VARCHAR(16) | Y |  |
| explanation_request_dt | DATETIME | Y |  |
| explanation_requester | VARCHAR(64) | Y |  |
| explanation_process_dt | DATETIME | Y |  |
| explanation_processor | VARCHAR(64) | Y |  |
| explanation_request_msg | VARCHAR(2048) | Y |  |
| explanation_process_comment | VARCHAR(2048) | Y |  |
| due_date | DATETIME | Y |  |
| explanation_submit_dt | DATETIME | Y |  |
| explanation_content | VARCHAR(4000) | Y |  |
| is_escalated | BOOLEAN | N |  |

_인덱스_: ix_receipt_transactions_company_id(company_id); ix_receipt_transactions_department(department); ix_receipt_transactions_employee_id(employee_id); ix_receipt_transactions_file_id(file_id); ix_receipt_transactions_workplace_id(workplace_id)

## `chat_messages`  ⚠ 테넌트 컬럼 없음

| 컬럼 | 타입 | NULL | 키/비고 |
|------|------|------|---------|
| id | VARCHAR(36) | N | PK |
| session_id | VARCHAR(36) | N | FK→chat_sessions.id, idx |
| seq | INTEGER | N | idx |
| role | VARCHAR(16) | N |  |
| content | TEXT | N |  |
| input_tokens | INTEGER | N |  |
| output_tokens | INTEGER | N |  |
| sources_json | TEXT | Y |  |
| created_at | DATETIME | N |  |

_인덱스_: ix_chat_messages_seq(seq); ix_chat_messages_session_id(session_id)
