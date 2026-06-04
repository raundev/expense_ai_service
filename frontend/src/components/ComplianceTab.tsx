import { useEffect, useState, useCallback } from "react";
import { RefreshCw, Send, Undo2, CheckCircle2, XCircle, Loader2 } from "lucide-react";
import { api, errMessage } from "../api";
import type { DashboardKpi, TransactionRow, ProcessStatus } from "../types";

const KPI_URL = "/api/compliance/dashboard/kpi";
const LIST_URL = "/api/compliance/transactions";
const REQUEST_URL = "/api/compliance/transactions/request-explanation";
const CANCEL_URL = "/api/compliance/transactions/cancel-explanation";
const PROCESS_URL = "/api/compliance/transactions/process-explanation";

const KPI_CARDS: { key: keyof DashboardKpi; label: string; color: string }[] = [
  { key: "total_detected", label: "전체 탐지", color: "bg-slate-700" },
  { key: "not_requested", label: "미요청", color: "bg-amber-500" },
  { key: "requested", label: "요청완료", color: "bg-blue-500" },
  { key: "normal_processed", label: "정상처리", color: "bg-emerald-500" },
  { key: "violation_confirmed", label: "위반확정", color: "bg-red-500" },
];

function statusBadge(status: string | null): string {
  switch (status) {
    case "요청완료":
      return "bg-blue-100 text-blue-700";
    case "소명제출":
      return "bg-indigo-100 text-indigo-700";
    case "기한초과":
      return "bg-orange-100 text-orange-700";
    case "정상처리":
      return "bg-emerald-100 text-emerald-700";
    case "위반확정":
      return "bg-red-100 text-red-700";
    default:
      return "bg-amber-100 text-amber-700"; // 미요청
  }
}

export default function ComplianceTab() {
  const [kpi, setKpi] = useState<DashboardKpi | null>(null);
  const [rows, setRows] = useState<TransactionRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [msg, setMsg] = useState<{ type: "ok" | "err"; text: string } | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setMsg(null);
    try {
      const [k, l] = await Promise.all([
        api.get<DashboardKpi>(KPI_URL),
        api.get<TransactionRow[]>(LIST_URL, { params: { limit: 100 } }),
      ]);
      setKpi(k.data);
      setRows(l.data);
    } catch (e) {
      setMsg({ type: "err", text: errMessage(e) });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const action = async (id: number, fn: () => Promise<unknown>, okText: string) => {
    setBusyId(id);
    setMsg(null);
    try {
      await fn();
      setMsg({ type: "ok", text: okText });
      await refresh();
    } catch (e) {
      setMsg({ type: "err", text: errMessage(e) });
    } finally {
      setBusyId(null);
    }
  };

  const requestExp = (id: number) => {
    const message = window.prompt("소명 요청 메시지", "해당 결제 건에 대해 소명 바랍니다.");
    if (message === null) return;
    return action(
      id,
      () => api.post(REQUEST_URL, { transaction_ids: [id], request_message: message }),
      `#${id} 소명 요청 발송`
    );
  };

  const cancelExp = (id: number) =>
    action(
      id,
      () => api.post(CANCEL_URL, { transaction_ids: [id], cancel_reason: "관리자 취소(테스트)" }),
      `#${id} 소명 요청 취소`
    );

  const processExp = (id: number, status: ProcessStatus) =>
    action(
      id,
      () =>
        api.post(PROCESS_URL, {
          transaction_ids: [id],
          status,
          process_comment: `${status}(테스트)`,
        }),
      `#${id} → ${status}`
    );

  return (
    <div className="space-y-6">
      {/* 헤더 + 새로고침 */}
      <div className="flex items-center justify-between">
        <h2 className="font-semibold text-slate-700">컴플라이언스 관리자 대시보드</h2>
        <button
          onClick={refresh}
          disabled={loading}
          className="inline-flex items-center gap-2 bg-slate-700 hover:bg-slate-800 disabled:opacity-50 text-white text-sm px-3 py-1.5 rounded-md"
        >
          {loading ? <Loader2 size={15} className="animate-spin" /> : <RefreshCw size={15} />}
          새로고침
        </button>
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

      {/* KPI 카드 */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        {KPI_CARDS.map((c) => (
          <div key={c.key} className="bg-white border border-slate-200 rounded-xl p-4 shadow-sm">
            <div className="flex items-center gap-2">
              <span className={`inline-block w-2.5 h-2.5 rounded-full ${c.color}`} />
              <span className="text-xs text-slate-500">{c.label}</span>
            </div>
            <div className="text-2xl font-bold text-slate-800 mt-1">{kpi ? kpi[c.key] : "-"}</div>
          </div>
        ))}
      </div>

      {/* 위반 그리드 */}
      <div className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-slate-500 text-xs uppercase">
            <tr>
              {["ID", "일자", "가맹점", "금액", "용도", "부서", "상태", "위반사유", "액션"].map((h) => (
                <th key={h} className="text-left font-medium px-3 py-2 whitespace-nowrap">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {rows.length === 0 && (
              <tr>
                <td colSpan={9} className="text-center text-slate-400 py-8">
                  위반 내역이 없습니다. (배치 업로드 또는 단건 위반 생성 후 새로고침)
                </td>
              </tr>
            )}
            {rows.map((r) => (
              <tr key={r.id} className="hover:bg-slate-50">
                <td className="px-3 py-2 text-slate-500">{r.id}</td>
                <td className="px-3 py-2 whitespace-nowrap">{r.receipt_date}</td>
                <td className="px-3 py-2">{r.merchant_name}</td>
                <td className="px-3 py-2 whitespace-nowrap">{r.amount.toLocaleString()}원</td>
                <td className="px-3 py-2">{r.recommended_result_category}</td>
                <td className="px-3 py-2">{r.department ?? "-"}</td>
                <td className="px-3 py-2">
                  <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${statusBadge(r.explanation_status)}`}>
                    {r.explanation_status ?? "미요청"}
                  </span>
                </td>
                <td className="px-3 py-2 max-w-[220px] truncate text-slate-600" title={r.violation_reason ?? ""}>
                  {r.violation_reason ?? "-"}
                </td>
                <td className="px-3 py-2">
                  <RowActions
                    row={r}
                    busy={busyId === r.id}
                    onRequest={() => requestExp(r.id)}
                    onCancel={() => cancelExp(r.id)}
                    onProcess={(s) => processExp(r.id, s)}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function RowActions({
  row,
  busy,
  onRequest,
  onCancel,
  onProcess,
}: {
  row: TransactionRow;
  busy: boolean;
  onRequest: () => void;
  onCancel: () => void;
  onProcess: (s: ProcessStatus) => void;
}) {
  const status = row.explanation_status ?? "미요청";
  const btn = "inline-flex items-center gap-1 text-xs px-2 py-1 rounded-md font-medium disabled:opacity-40";

  if (busy) {
    return <Loader2 size={15} className="animate-spin text-slate-400" />;
  }

  if (status === "정상처리" || status === "위반확정") {
    return <span className="text-xs text-slate-400">종결됨</span>;
  }

  const canProcess = status === "요청완료" || status === "소명제출" || status === "기한초과";
  return (
    <div className="flex flex-wrap gap-1.5">
      {status === "미요청" && (
        <button onClick={onRequest} className={`${btn} bg-blue-100 text-blue-700 hover:bg-blue-200`}>
          <Send size={13} /> 소명요청
        </button>
      )}
      {status === "요청완료" && (
        <button onClick={onCancel} className={`${btn} bg-amber-100 text-amber-700 hover:bg-amber-200`}>
          <Undo2 size={13} /> 요청취소
        </button>
      )}
      {canProcess && (
        <>
          <button onClick={() => onProcess("정상처리")} className={`${btn} bg-emerald-100 text-emerald-700 hover:bg-emerald-200`}>
            <CheckCircle2 size={13} /> 정상처리
          </button>
          <button onClick={() => onProcess("위반확정")} className={`${btn} bg-red-100 text-red-700 hover:bg-red-200`}>
            <XCircle size={13} /> 위반확정
          </button>
        </>
      )}
    </div>
  );
}
