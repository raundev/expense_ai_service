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
export const api = axios.create({ timeout: 60000 });

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
