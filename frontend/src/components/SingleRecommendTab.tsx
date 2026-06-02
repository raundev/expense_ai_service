import { useState } from "react";
import { PlayCircle, ShieldCheck, ShieldAlert, Loader2 } from "lucide-react";
import { api, errMessage } from "../api";
import type { RecommendResponse } from "../types";

const ENDPOINT = "/api/v1/transactions/test-single-transaction/create";

interface FormState {
  merchant_name: string;
  amount: number;
  receipt_date: string;
  receipt_time: string;
  department: string;
  employee_id: string;
}

export default function SingleRecommendTab() {
  const [form, setForm] = useState<FormState>({
    merchant_name: "맥도날드",
    amount: 20000,
    receipt_date: "2026-05-28",
    receipt_time: "19:30",
    department: "개발팀",
    employee_id: "emp_kim",
  });
  const [result, setResult] = useState<RecommendResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const set = (k: keyof FormState, v: string | number) =>
    setForm((p) => ({ ...p, [k]: v }));

  const run = async () => {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const { data } = await api.post<RecommendResponse>(ENDPOINT, {
        merchant_name: form.merchant_name,
        amount: Number(form.amount),
        receipt_date: form.receipt_date,
        receipt_time: form.receipt_time,
        department: form.department || null,
        employee_id: form.employee_id || null,
      });
      setResult(data);
    } catch (e) {
      setError(errMessage(e));
    } finally {
      setLoading(false);
    }
  };

  const Input = (label: string, key: keyof FormState, type = "text") => (
    <label className="text-xs text-slate-500 flex flex-col gap-1">
      {label}
      <input
        type={type}
        className="border border-slate-300 rounded-md px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
        value={form[key]}
        onChange={(e) => set(key, type === "number" ? Number(e.target.value) : e.target.value)}
      />
    </label>
  );

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      {/* 입력 폼 */}
      <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm">
        <h2 className="font-semibold text-slate-700 mb-4">영수증 단건 추천 &amp; 컴플라이언스 검사</h2>
        <div className="grid grid-cols-2 gap-3">
          {Input("가맹점명", "merchant_name")}
          {Input("결제금액(원)", "amount", "number")}
          {Input("사용일자", "receipt_date", "date")}
          {Input("사용시간(HH:MM)", "receipt_time")}
          {Input("부서명", "department")}
          {Input("직원 ID", "employee_id")}
        </div>
        <button
          onClick={run}
          disabled={loading}
          className="mt-4 inline-flex items-center gap-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-sm font-medium px-4 py-2 rounded-md"
        >
          {loading ? <Loader2 size={16} className="animate-spin" /> : <PlayCircle size={16} />}
          분류 및 검사 실행
        </button>
        <p className="text-xs text-slate-400 mt-2">
          POST <code>{ENDPOINT}</code>
        </p>
      </div>

      {/* 결과 */}
      <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm">
        <h2 className="font-semibold text-slate-700 mb-4">검사 결과</h2>
        {error && (
          <div className="bg-red-50 text-red-700 text-sm rounded-md p-3 border border-red-200">{error}</div>
        )}
        {!error && !result && <p className="text-sm text-slate-400">실행 버튼을 눌러 결과를 확인하세요.</p>}
        {result && (
          <div className="space-y-3">
            <div
              className={`flex items-center gap-2 rounded-lg p-3 text-sm font-semibold ${
                result.is_compliant
                  ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                  : "bg-red-50 text-red-700 border border-red-200"
              }`}
            >
              {result.is_compliant ? <ShieldCheck size={18} /> : <ShieldAlert size={18} />}
              {result.is_compliant ? "규정 준수 (Compliant)" : "규정 위반 (Violation)"}
            </div>
            <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
              <Field label="추천 용도" value={result.result_category} />
              <Field label="용도 코드" value={result.category_code} />
              <Field label="매칭 출처" value={result.match_type} />
              <Field label="소명 상태" value={result.explanation_status ?? "-"} />
              <Field label="부서" value={result.department ?? "-"} />
              <Field label="직원" value={result.employee_id ?? "-"} />
            </dl>
            {result.violation_reason && (
              <div className="text-sm">
                <span className="text-slate-500">위반 사유</span>
                <p className="text-red-700 bg-red-50 border border-red-200 rounded-md p-2 mt-1">
                  {result.violation_reason}
                </p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <>
      <dt className="text-slate-500">{label}</dt>
      <dd className="text-slate-800 font-medium text-right">{value}</dd>
    </>
  );
}
