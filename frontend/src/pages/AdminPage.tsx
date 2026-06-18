import { useCallback, useEffect, useState } from "react";
import { RefreshCw, Plus, Loader2, Power, Trash2 } from "lucide-react";
import { api, errMessage, unwrap } from "../api";
import type { ApiResponse, TenantResponse } from "../types";

const TENANTS_URL = "/api/admin/tenants";
const TENANT_URL = (id: string) => `/api/admin/tenants/${id}`;
const CLEANUP_URL = "/api/admin/cleanup";

// Admin 페이지 — 테넌트 화이트리스트 관리(등록/조회/상태전환) + Soft Delete 정리 워커 트리거.
export default function AdminPage() {
  const [tenants, setTenants] = useState<TenantResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState<{ type: "ok" | "err"; text: string } | null>(null);
  const [form, setForm] = useState({ company_id: "", workplace_id: "", company_name: "", workplace_name: "" });
  const [cleaning, setCleaning] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    setMsg(null);
    try {
      const { data } = await api.get<ApiResponse<TenantResponse[]>>(TENANTS_URL);
      setTenants(unwrap(data) ?? []);
    } catch (e) {
      setMsg({ type: "err", text: errMessage(e) });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const register = async () => {
    if (!form.company_id || !form.workplace_id) return setMsg({ type: "err", text: "회사/사업장 ID는 필수입니다." });
    try {
      await api.post(TENANTS_URL, {
        company_id: form.company_id,
        workplace_id: form.workplace_id,
        company_name: form.company_name || null,
        workplace_name: form.workplace_name || null,
      });
      setMsg({ type: "ok", text: `테넌트 ${form.company_id}/${form.workplace_id} 등록 완료.` });
      setForm({ company_id: "", workplace_id: "", company_name: "", workplace_name: "" });
      await refresh();
    } catch (e) {
      setMsg({ type: "err", text: errMessage(e) });
    }
  };

  const toggleStatus = async (t: TenantResponse) => {
    const next = t.status === "ACTIVE" ? "SUSPENDED" : "ACTIVE";
    try {
      await api.patch(TENANT_URL(t.id), { status: next });
      setMsg({ type: "ok", text: `${t.company_id}/${t.workplace_id} → ${next}` });
      await refresh();
    } catch (e) {
      setMsg({ type: "err", text: errMessage(e) });
    }
  };

  const cleanup = async () => {
    if (!window.confirm("Soft Delete(DELETING) 봇·문서를 물리 정리하시겠습니까?")) return;
    setCleaning(true);
    try {
      const { data } = await api.post<ApiResponse<Record<string, unknown>>>(CLEANUP_URL);
      setMsg({ type: "ok", text: `cleanup 완료: ${JSON.stringify(unwrap(data))}` });
    } catch (e) {
      setMsg({ type: "err", text: errMessage(e) });
    } finally {
      setCleaning(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-800">Admin</h1>
          <p className="text-sm text-slate-500">테넌트 화이트리스트(회사/사업장) 등록·상태 관리와 Soft Delete 물리 정리 워커.</p>
        </div>
        <div className="flex gap-2">
          <button onClick={refresh} disabled={loading} className="inline-flex items-center gap-2 bg-slate-700 hover:bg-slate-800 disabled:opacity-50 text-white text-sm px-3 py-1.5 rounded-md">
            {loading ? <Loader2 size={15} className="animate-spin" /> : <RefreshCw size={15} />} 새로고침
          </button>
          <button onClick={cleanup} disabled={cleaning} className="inline-flex items-center gap-2 bg-red-600 hover:bg-red-700 disabled:opacity-50 text-white text-sm px-3 py-1.5 rounded-md">
            {cleaning ? <Loader2 size={15} className="animate-spin" /> : <Trash2 size={15} />} Cleanup 실행
          </button>
        </div>
      </div>

      {msg && (
        <div className={`text-sm rounded-md p-3 border ${msg.type === "ok" ? "bg-emerald-50 text-emerald-700 border-emerald-200" : "bg-red-50 text-red-700 border-red-200"}`}>
          {msg.text}
        </div>
      )}

      {/* 등록 폼 */}
      <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm">
        <h2 className="font-semibold text-slate-700 mb-3">테넌트 등록</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <input className="border border-slate-300 rounded-md px-2 py-1.5 text-sm" placeholder="company_id *" value={form.company_id} onChange={(e) => setForm({ ...form, company_id: e.target.value })} />
          <input className="border border-slate-300 rounded-md px-2 py-1.5 text-sm" placeholder="workplace_id *" value={form.workplace_id} onChange={(e) => setForm({ ...form, workplace_id: e.target.value })} />
          <input className="border border-slate-300 rounded-md px-2 py-1.5 text-sm" placeholder="회사명(선택)" value={form.company_name} onChange={(e) => setForm({ ...form, company_name: e.target.value })} />
          <input className="border border-slate-300 rounded-md px-2 py-1.5 text-sm" placeholder="사업장명(선택)" value={form.workplace_name} onChange={(e) => setForm({ ...form, workplace_name: e.target.value })} />
        </div>
        <button onClick={register} className="mt-3 inline-flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white text-sm px-4 py-2 rounded-md">
          <Plus size={15} /> 등록
        </button>
      </div>

      {/* 목록 */}
      <div className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-slate-500 text-xs uppercase">
            <tr>
              {["회사", "사업장", "회사명", "사업장명", "상태", "액션"].map((h) => (
                <th key={h} className="text-left font-medium px-3 py-2 whitespace-nowrap">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {tenants.length === 0 && (
              <tr><td colSpan={6} className="text-center text-slate-400 py-8">등록된 테넌트가 없습니다.</td></tr>
            )}
            {tenants.map((t) => (
              <tr key={t.id} className="hover:bg-slate-50">
                <td className="px-3 py-2 font-mono text-xs">{t.company_id}</td>
                <td className="px-3 py-2 font-mono text-xs">{t.workplace_id}</td>
                <td className="px-3 py-2">{t.company_name ?? "-"}</td>
                <td className="px-3 py-2">{t.workplace_name ?? "-"}</td>
                <td className="px-3 py-2">
                  <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${t.status === "ACTIVE" ? "bg-emerald-100 text-emerald-700" : "bg-red-100 text-red-700"}`}>
                    {t.status}
                  </span>
                </td>
                <td className="px-3 py-2">
                  <button onClick={() => toggleStatus(t)} className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded-md bg-slate-100 text-slate-700 hover:bg-slate-200">
                    <Power size={13} /> {t.status === "ACTIVE" ? "정지(SUSPEND)" : "복구(ACTIVE)"}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
