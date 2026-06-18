import { useCallback, useEffect, useState } from "react";
import { RefreshCw, Plus, Pencil, Loader2, Save, X } from "lucide-react";
import { api, errMessage } from "../api";
import type { RuleRequest, RuleResponse } from "../types";

const LIST_URL = "/api/v1/rules/";
const CREATE_URL = "/api/v1/rules/create";
const UPDATE_URL = (id: number) => `/api/v1/rules/update/${id}`;

const EMPTY: RuleRequest = {
  rule_name: "",
  condition_keyword: null,
  condition_min_amount: null,
  condition_max_amount: null,
  is_weekend: null,
  is_holiday: null,
  usage_time_band: null,
  card_company_code: null,
  merchant_sector_code: null,
  merchant_sector_name: null,
  category_code: "",
  result_category: "",
  priority: 0,
  is_active: true,
};

// 룰 조회 메뉴 — 활성 규칙 목록 조회 + 신규 등록 / 수정.
export default function RulesPage() {
  const [rules, setRules] = useState<RuleResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState<{ type: "ok" | "err"; text: string } | null>(null);
  const [editing, setEditing] = useState<{ id: number | null; form: RuleRequest } | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setMsg(null);
    try {
      const { data } = await api.get<RuleResponse[]>(LIST_URL);
      setRules(data);
    } catch (e) {
      setMsg({ type: "err", text: errMessage(e) });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const startCreate = () => setEditing({ id: null, form: { ...EMPTY } });
  const startEdit = (r: RuleResponse) =>
    setEditing({
      id: r.id,
      form: {
        rule_name: r.rule_name,
        condition_keyword: r.condition_keyword,
        condition_min_amount: r.condition_min_amount,
        condition_max_amount: r.condition_max_amount,
        is_weekend: r.is_weekend,
        is_holiday: r.is_holiday,
        usage_time_band: r.usage_time_band,
        card_company_code: r.card_company_code,
        merchant_sector_code: r.merchant_sector_code,
        merchant_sector_name: r.merchant_sector_name,
        category_code: r.category_code,
        result_category: r.result_category,
        priority: r.priority,
        is_active: r.is_active,
      },
    });

  const save = async () => {
    if (!editing) return;
    setMsg(null);
    try {
      if (editing.id === null) {
        await api.post(CREATE_URL, editing.form);
        setMsg({ type: "ok", text: "규칙이 등록되었습니다." });
      } else {
        await api.put(UPDATE_URL(editing.id), editing.form);
        setMsg({ type: "ok", text: `#${editing.id} 규칙이 수정되었습니다.` });
      }
      setEditing(null);
      await refresh();
    } catch (e) {
      setMsg({ type: "err", text: errMessage(e) });
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-800">룰 조회</h1>
          <p className="text-sm text-slate-500">테넌트의 활성 분류 규칙을 priority 오름차순으로 조회하고 등록/수정합니다.</p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={refresh}
            disabled={loading}
            className="inline-flex items-center gap-2 bg-slate-700 hover:bg-slate-800 disabled:opacity-50 text-white text-sm px-3 py-1.5 rounded-md"
          >
            {loading ? <Loader2 size={15} className="animate-spin" /> : <RefreshCw size={15} />}
            새로고침
          </button>
          <button
            onClick={startCreate}
            className="inline-flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white text-sm px-3 py-1.5 rounded-md"
          >
            <Plus size={15} /> 규칙 등록
          </button>
        </div>
      </div>

      {msg && (
        <div
          className={`text-sm rounded-md p-3 border ${
            msg.type === "ok"
              ? "bg-emerald-50 text-emerald-700 border-emerald-200"
              : "bg-red-50 text-red-700 border-red-200"
          }`}
        >
          {msg.text}
        </div>
      )}

      {editing && (
        <RuleForm
          editing={editing}
          onChange={(form) => setEditing((p) => (p ? { ...p, form } : p))}
          onSave={save}
          onCancel={() => setEditing(null)}
        />
      )}

      <div className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-slate-500 text-xs uppercase">
            <tr>
              {["ID", "규칙명", "키워드", "금액범위", "용도코드", "용도명", "우선순위", "활성", "수정"].map((h) => (
                <th key={h} className="text-left font-medium px-3 py-2 whitespace-nowrap">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {rules.length === 0 && (
              <tr>
                <td colSpan={9} className="text-center text-slate-400 py-8">
                  활성 규칙이 없습니다. "규칙 등록" 으로 추가하세요.
                </td>
              </tr>
            )}
            {rules.map((r) => (
              <tr key={r.id} className="hover:bg-slate-50">
                <td className="px-3 py-2 text-slate-500">{r.id}</td>
                <td className="px-3 py-2 font-medium text-slate-800">{r.rule_name}</td>
                <td className="px-3 py-2">{r.condition_keyword ?? "-"}</td>
                <td className="px-3 py-2 whitespace-nowrap">
                  {r.condition_min_amount ?? "0"} ~ {r.condition_max_amount ?? "∞"}
                </td>
                <td className="px-3 py-2 font-mono text-xs">{r.category_code}</td>
                <td className="px-3 py-2">{r.result_category}</td>
                <td className="px-3 py-2 text-center">{r.priority}</td>
                <td className="px-3 py-2">
                  <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${r.is_active ? "bg-emerald-100 text-emerald-700" : "bg-slate-100 text-slate-500"}`}>
                    {r.is_active ? "활성" : "비활성"}
                  </span>
                </td>
                <td className="px-3 py-2">
                  <button onClick={() => startEdit(r)} className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded-md bg-slate-100 text-slate-700 hover:bg-slate-200">
                    <Pencil size={13} /> 수정
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

function RuleForm({
  editing,
  onChange,
  onSave,
  onCancel,
}: {
  editing: { id: number | null; form: RuleRequest };
  onChange: (form: RuleRequest) => void;
  onSave: () => void;
  onCancel: () => void;
}) {
  const f = editing.form;
  const set = (patch: Partial<RuleRequest>) => onChange({ ...f, ...patch });
  const numOrNull = (v: string) => (v === "" ? null : Number(v));

  const Txt = (label: string, key: keyof RuleRequest, required = false) => (
    <label className="text-xs text-slate-500 flex flex-col gap-1">
      <span>{label}{required && <span className="text-red-500"> *</span>}</span>
      <input
        className="border border-slate-300 rounded-md px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
        value={(f[key] as string | null) ?? ""}
        onChange={(e) => set({ [key]: e.target.value || (required ? "" : null) } as Partial<RuleRequest>)}
      />
    </label>
  );

  return (
    <div className="bg-white border border-blue-200 rounded-xl p-5 shadow-sm">
      <div className="flex items-center justify-between mb-4">
        <h2 className="font-semibold text-slate-700">{editing.id === null ? "신규 규칙 등록" : `규칙 #${editing.id} 수정`}</h2>
        <button onClick={onCancel} className="text-slate-400 hover:text-slate-600"><X size={18} /></button>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
        {Txt("규칙명", "rule_name", true)}
        {Txt("조건 키워드", "condition_keyword")}
        {Txt("시간대(usage_time_band)", "usage_time_band")}
        <label className="text-xs text-slate-500 flex flex-col gap-1">
          최소 금액
          <input type="number" className="border border-slate-300 rounded-md px-2 py-1.5 text-sm" value={f.condition_min_amount ?? ""} onChange={(e) => set({ condition_min_amount: numOrNull(e.target.value) })} />
        </label>
        <label className="text-xs text-slate-500 flex flex-col gap-1">
          최대 금액
          <input type="number" className="border border-slate-300 rounded-md px-2 py-1.5 text-sm" value={f.condition_max_amount ?? ""} onChange={(e) => set({ condition_max_amount: numOrNull(e.target.value) })} />
        </label>
        <label className="text-xs text-slate-500 flex flex-col gap-1">
          우선순위(낮을수록 먼저)
          <input type="number" className="border border-slate-300 rounded-md px-2 py-1.5 text-sm" value={f.priority} onChange={(e) => set({ priority: Number(e.target.value) })} />
        </label>
        {Txt("업종코드", "merchant_sector_code")}
        {Txt("업종명", "merchant_sector_name")}
        {Txt("카드사코드", "card_company_code")}
        {Txt("용도코드(category_code)", "category_code", true)}
        {Txt("용도명(result_category)", "result_category", true)}
        <label className="text-xs text-slate-500 flex items-center gap-2 mt-5">
          <input type="checkbox" checked={f.is_active} onChange={(e) => set({ is_active: e.target.checked })} />
          활성
        </label>
      </div>
      <div className="flex gap-2 mt-4">
        <button onClick={onSave} className="inline-flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white text-sm px-4 py-2 rounded-md">
          <Save size={15} /> 저장
        </button>
        <button onClick={onCancel} className="text-sm px-4 py-2 rounded-md border border-slate-300 text-slate-600 hover:bg-slate-50">
          취소
        </button>
      </div>
    </div>
  );
}
