// 백엔드 응답 타입 (Phase 1~D 기준).
// 주의: rules/transactions/compliance 라우터는 DTO 를 그대로 반환하고,
// bots/chat/documents/tenants 라우터는 ApiResponse envelope({ success, data, ... })로 감싼다.
// 후자는 api.ts 의 unwrap() 으로 .data 를 벗겨서 사용한다.

// ---------------------------------------------------------------------------- //
// 공통 envelope (bots/chat/documents/tenants)
// ---------------------------------------------------------------------------- //
export interface ApiResponse<T> {
  success: boolean;
  data: T | null;
  message: string | null;
  error: string | null;
}

// ---------------------------------------------------------------------------- //
// 영수증 추천 / 컴플라이언스
// ---------------------------------------------------------------------------- //
export interface RecommendResponse {
  category_code: string;
  result_category: string;
  applied_rule_id: number | null;
  match_type: "RULE" | "HISTORY" | "LLM" | "NONE";
  message: string | null;
  is_compliant: boolean;
  violation_reason: string | null;
  explanation_status: string | null;
  department: string | null;
  employee_id: string | null;
}

export interface DashboardKpi {
  total_detected: number;
  not_requested: number;
  requested: number;
  normal_processed: number;
  violation_confirmed: number;
}

export interface TransactionRow {
  id: number;
  file_id: number;
  receipt_date: string;
  receipt_time: string;
  merchant_name: string;
  amount: number;
  recommended_result_category: string;
  match_type: string;
  department: string | null;
  employee_id: string | null;
  is_compliant: boolean;
  violation_reason: string | null;
  explanation_status: string | null;
  explanation_requester: string | null;
  explanation_processor: string | null;
}

export type ProcessStatus = "정상처리" | "위반확정";

// ---------------------------------------------------------------------------- //
// 룰(Rule)
// ---------------------------------------------------------------------------- //
export interface RuleRequest {
  rule_name: string;
  condition_keyword: string | null;
  condition_min_amount: number | null;
  condition_max_amount: number | null;
  is_weekend: boolean | null;
  is_holiday: boolean | null;
  usage_time_band: string | null;
  card_company_code: string | null;
  merchant_sector_code: string | null;
  merchant_sector_name: string | null;
  category_code: string;
  result_category: string;
  priority: number;
  is_active: boolean;
}

export interface RuleResponse extends RuleRequest {
  id: number;
  company_id: string;
  workplace_id: string | null;
}

// 규칙 일괄 등록(온보딩/시드)
export interface RuleBulkCreateRequest {
  rules: RuleRequest[];
}

export interface RuleBulkCreateResponse {
  created_count: number;
  rules: RuleResponse[];
}

// ---------------------------------------------------------------------------- //
// 봇(Bot) + RAG 채팅
// ---------------------------------------------------------------------------- //
export interface RecommendedQuestion {
  id: string;
  question: string;
  sort_order: number;
}

export interface BotResponse {
  id: string;
  company_id: string;
  workplace_id: string;
  name: string;
  llm_model: string;
  llm_temperature: number;
  max_answer_length: number;
  history_turns: number;
  top_k: number;
  system_prompt: string | null;
  source_expose: boolean;
  disabled: boolean;
  status: string;
  created_at: string;
  updated_at: string;
  recommended_questions: RecommendedQuestion[];
}

export interface BotCreateRequest {
  name: string;
  llm_model?: string | null;
  llm_temperature?: number;
  max_answer_length?: number;
  history_turns?: number;
  top_k?: number;
  system_prompt?: string | null;
  source_expose?: boolean;
  recommended_questions?: string[];
}

export interface ChatSource {
  doc_id: string;
  title: string | null;
  file_name: string | null;
  snippet: string;
  score: number | null;
  chunk_index: number | null;
  document_url: string | null;
}

export interface PolicyChatResponse {
  answer: string;
  session_id: string;
  sources: ChatSource[];
}

export interface ChatModelsResponse {
  models: string[];
}

export interface ChatTranslateRequest {
  bot_id: string;
  text: string;
  reference_query: string;
}

export interface ChatTranslateResponse {
  translated: string;
}

// ---------------------------------------------------------------------------- //
// 문서(Document)
// ---------------------------------------------------------------------------- //
export interface DocumentResponse {
  id: string;
  company_id: string;
  workplace_id: string;
  domain: string;
  owner_id: string | null;
  is_compliance_source: boolean;
  title: string;
  file_name: string | null;
  content_type: string | null;
  byte_size: number | null;
  source_name: string;
  embedding_status: "PROCESSING" | "COMPLETED" | "FAILED" | "DELETING";
  error_message: string | null;
  chunk_count: number;
  created_at: string;
  updated_at: string;
}

// ---------------------------------------------------------------------------- //
// 테넌트(Tenant)
// ---------------------------------------------------------------------------- //
export interface TenantResponse {
  id: string;
  company_id: string;
  workplace_id: string;
  company_name: string | null;
  workplace_name: string | null;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface TenantCreateRequest {
  company_id: string;
  workplace_id: string;
  company_name?: string | null;
  workplace_name?: string | null;
}
