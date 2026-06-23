import axios from "axios";

// ---------------------------------------------------------------------------- //
// 전역 설정 (Base URL + 멀티테넌트 헤더). localStorage 에 영속.
// axios 인터셉터가 매 요청 시 localStorage 에서 읽으므로 항상 최신값을 사용한다.
// ---------------------------------------------------------------------------- //
const LS_KEY = "bizplay_test_settings";

export interface Settings {
  baseUrl: string;
  companyId: string;
  workplaceId: string;
  adminId: string;
  employeeId: string;
}

export const DEFAULT_SETTINGS: Settings = {
  baseUrl: "http://localhost:8000",
  companyId: "COMPANY_A",
  workplaceId: "HQ",
  adminId: "admin_kim",
  employeeId: "",
};

export function loadSettings(): Settings {
  try {
    const raw = localStorage.getItem(LS_KEY);
    return raw ? { ...DEFAULT_SETTINGS, ...JSON.parse(raw) } : { ...DEFAULT_SETTINGS };
  } catch {
    return { ...DEFAULT_SETTINGS };
  }
}

export function saveSettings(s: Settings): void {
  localStorage.setItem(LS_KEY, JSON.stringify(s));
}

// 단일 axios 인스턴스 — baseURL/헤더는 인터셉터에서 동적으로 주입.
// 전역 기본 타임아웃은 일반 CRUD 기준 60초. LLM(RunPod) 호출처럼 느린 요청은
// 호출부에서 per-request 로 { timeout: LLM_TIMEOUT_MS } 를 넘겨 개별 연장한다.
export const api = axios.create({ timeout: 60000 });

// LLM(RunPod GPU 프록시) 을 경유하는 요청 전용 타임아웃(ms).
// 백엔드는 RunPod endpoint 감지 시 LLM HTTP 호출을 150초까지 대기한다(app/core/config.py
// llm_http_timeout). 프론트가 그보다 먼저 끊으면 'timeout of 60000ms exceeded' 가 나므로,
// 백엔드 상한(150초)에 여유를 더한 160초로 둔다. 챗(RAG)·용도 추천 호출에만 적용.
export const LLM_TIMEOUT_MS = 160000;

api.interceptors.request.use((config) => {
  const s = loadSettings();
  config.baseURL = (s.baseUrl || "").replace(/\/+$/, "");
  config.headers = config.headers ?? {};
  if (s.companyId) config.headers["X-Company-ID"] = s.companyId;
  if (s.workplaceId) config.headers["X-Workplace-ID"] = s.workplaceId;
  if (s.adminId) config.headers["X-Admin-ID"] = s.adminId;
  if (s.employeeId) config.headers["X-Employee-ID"] = s.employeeId;
  return config;
});

// ApiResponse envelope({ success, data, ... })를 벗겨 data 만 돌려준다.
// bots/chat/documents/tenants 라우터 응답에 사용(rules/transactions/compliance 는 raw 라 불필요).
export function unwrap<T>(body: { success?: boolean; data?: T | null; error?: string | null }): T {
  if (body && body.success === false) {
    throw new Error(body.error || "요청이 실패했습니다.");
  }
  return (body?.data as T);
}

// 테넌트(회사/사업장)가 설정되어 있는지 — 진입 게이트/라우트 가드에서 사용.
export function hasTenant(): boolean {
  const s = loadSettings();
  return Boolean(s.companyId && s.workplaceId && s.baseUrl);
}

// 에러 메시지를 사람이 읽기 쉽게 추출.
export function errMessage(e: unknown): string {
  if (axios.isAxiosError(e)) {
    const detail = (e.response?.data as { detail?: unknown } | undefined)?.detail;
    if (typeof detail === "string") return `${e.response?.status}: ${detail}`;
    if (detail) return `${e.response?.status}: ${JSON.stringify(detail)}`;
    if (e.response) return `${e.response.status}: ${e.response.statusText}`;
    return e.message || "네트워크 오류 (CORS/Base URL 확인)";
  }
  return String(e);
}
