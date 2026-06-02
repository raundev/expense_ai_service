// 백엔드 응답 타입 (Phase 1 기준, 일부 Phase 2 필드 포함)

export interface RecommendResponse {
  category_code: string;
  result_category: string;
  applied_rule_id: number | null;
  match_type: "RULE" | "HISTORY" | "LLM" | "NONE";
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
