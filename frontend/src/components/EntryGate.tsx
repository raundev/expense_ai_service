import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Building2, LogIn } from "lucide-react";
import { loadSettings, saveSettings, type Settings } from "../api";

// 진입 페이지 — 테넌트 정보(회사/사업장)를 기준으로 콘솔에 진입한다.
// 입력값은 localStorage 에 저장되어 이후 모든 API 요청 헤더에 자동 주입된다.
const FIELDS: {
  key: keyof Settings;
  label: string;
  placeholder: string;
  required?: boolean;
  hint?: string;
}[] = [
  { key: "baseUrl", label: "API Base URL", placeholder: "http://localhost:8000", required: true },
  { key: "companyId", label: "회사 (X-Company-ID)", placeholder: "COMPANY_A", required: true },
  { key: "workplaceId", label: "사업장 (X-Workplace-ID)", placeholder: "HQ", required: true },
  { key: "adminId", label: "관리자 ID (X-Admin-ID)", placeholder: "admin_kim", hint: "소명 요청/처리 시 필요" },
  { key: "employeeId", label: "직원 ID (X-Employee-ID)", placeholder: "emp_kim", hint: "선택" },
];

export default function EntryGate() {
  const navigate = useNavigate();
  const [form, setForm] = useState<Settings>(() => loadSettings());

  const set = (k: keyof Settings, v: string) => setForm((p) => ({ ...p, [k]: v }));

  const canEnter = Boolean(form.baseUrl && form.companyId && form.workplaceId);

  const enter = () => {
    if (!canEnter) return;
    saveSettings(form);
    navigate("/console/receipts");
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-100 px-4">
      <div className="w-full max-w-lg bg-white border border-slate-200 rounded-2xl shadow-sm p-8">
        <div className="flex items-center gap-3 mb-1">
          <span className="inline-flex items-center justify-center w-10 h-10 rounded-xl bg-blue-600 text-white">
            <Building2 size={20} />
          </span>
          <div>
            <h1 className="text-lg font-bold text-slate-800">Bizplay AI · 테스트 콘솔</h1>
            <p className="text-xs text-slate-400">테넌트(회사/사업장) 정보로 진입하세요</p>
          </div>
        </div>

        <div className="mt-6 space-y-3">
          {FIELDS.map((f) => (
            <label key={f.key} className="block text-xs text-slate-500">
              <span className="flex items-center gap-1">
                {f.label}
                {f.required && <span className="text-red-500">*</span>}
                {f.hint && <span className="text-slate-400">— {f.hint}</span>}
              </span>
              <input
                className="mt-1 w-full border border-slate-300 rounded-md px-3 py-2 text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-400"
                value={form[f.key]}
                placeholder={f.placeholder}
                onChange={(e) => set(f.key, e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && enter()}
              />
            </label>
          ))}
        </div>

        <button
          onClick={enter}
          disabled={!canEnter}
          className="mt-6 w-full inline-flex items-center justify-center gap-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-40 text-white text-sm font-semibold px-4 py-2.5 rounded-md"
        >
          <LogIn size={16} />
          콘솔 진입
        </button>
        <p className="text-xs text-slate-400 mt-3 text-center">
          회사 · 사업장 · API 주소는 필수입니다. 입력값은 브라우저에 저장됩니다.
        </p>
      </div>
    </div>
  );
}
