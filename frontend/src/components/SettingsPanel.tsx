import { Settings as SettingsIcon } from "lucide-react";
import type { Settings } from "../api";

interface Props {
  settings: Settings;
  onChange: (patch: Partial<Settings>) => void;
}

const FIELDS: { key: keyof Settings; label: string; placeholder: string }[] = [
  { key: "baseUrl", label: "API Base URL", placeholder: "http://localhost:8000" },
  { key: "companyId", label: "X-Company-ID", placeholder: "COMPANY_A" },
  { key: "workplaceId", label: "X-Workplace-ID", placeholder: "HQ" },
  { key: "adminId", label: "X-Admin-ID", placeholder: "admin_kim" },
  { key: "employeeId", label: "X-Employee-ID (선택)", placeholder: "emp_kim" },
];

export default function SettingsPanel({ settings, onChange }: Props) {
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-sm">
      <div className="flex items-center gap-2 mb-3 text-slate-700 font-semibold">
        <SettingsIcon size={18} />
        전역 설정 — Base URL &amp; 테넌트 헤더
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
        {FIELDS.map((f) => (
          <label key={f.key} className="text-xs text-slate-500 flex flex-col gap-1">
            {f.label}
            <input
              className="border border-slate-300 rounded-md px-2 py-1.5 text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-400"
              value={settings[f.key]}
              placeholder={f.placeholder}
              onChange={(e) => onChange({ [f.key]: e.target.value })}
            />
          </label>
        ))}
      </div>
      <p className="text-xs text-slate-400 mt-2">
        입력값은 브라우저에 자동 저장되며, 이후 모든 API 호출 헤더에 자동 포함됩니다.
      </p>
    </div>
  );
}
