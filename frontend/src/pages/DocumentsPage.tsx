import { useCallback, useEffect, useState } from "react";
import { RefreshCw, Upload, FileText, Trash2, Download, Loader2 } from "lucide-react";
import { api, errMessage, unwrap, loadSettings } from "../api";
import type { ApiResponse, DocumentResponse } from "../types";

const LIST_URL = "/api/v1/documents";
const UPLOAD_URL = "/api/v1/documents/upload";
const INGEST_TEXT_URL = "/api/v1/documents/ingest-text";
const DOC_URL = (id: string) => `/api/v1/documents/${id}`;

function statusBadge(s: DocumentResponse["embedding_status"]): string {
  switch (s) {
    case "COMPLETED": return "bg-emerald-100 text-emerald-700";
    case "PROCESSING": return "bg-blue-100 text-blue-700";
    case "FAILED": return "bg-red-100 text-red-700";
    default: return "bg-slate-100 text-slate-500"; // DELETING
  }
}

// Document 페이지 — 공통 문서 모듈(목록/파일 업로드/텍스트 적재/삭제).
export default function DocumentsPage() {
  const [docs, setDocs] = useState<DocumentResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState<{ type: "ok" | "err"; text: string } | null>(null);
  const [domainFilter, setDomainFilter] = useState("");

  const refresh = useCallback(async () => {
    setLoading(true);
    setMsg(null);
    try {
      const { data } = await api.get<ApiResponse<DocumentResponse[]>>(LIST_URL, {
        params: domainFilter ? { domain: domainFilter } : {},
      });
      setDocs(unwrap(data) ?? []);
    } catch (e) {
      setMsg({ type: "err", text: errMessage(e) });
    } finally {
      setLoading(false);
    }
  }, [domainFilter]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const remove = async (id: string) => {
    if (!window.confirm("이 문서를 삭제(Soft Delete)하시겠습니까?")) return;
    try {
      await api.delete(DOC_URL(id));
      setMsg({ type: "ok", text: "삭제 요청 완료(DELETING)." });
      await refresh();
    } catch (e) {
      setMsg({ type: "err", text: errMessage(e) });
    }
  };

  const download = (id: string) => {
    const s = loadSettings();
    window.open(`${s.baseUrl.replace(/\/+$/, "")}/api/v1/documents/${id}/download`, "_blank");
  };

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-800">Document</h1>
          <p className="text-sm text-slate-500">공통 문서 모듈: 파일 업로드(비동기 임베딩)·텍스트 즉시 적재·목록·다운로드·삭제.</p>
        </div>
        <div className="flex items-end gap-2">
          <label className="text-xs text-slate-500 flex flex-col gap-1">
            도메인 필터
            <input
              className="border border-slate-300 rounded-md px-2 py-1.5 text-sm w-36"
              placeholder="policy / expense_rule"
              value={domainFilter}
              onChange={(e) => setDomainFilter(e.target.value)}
            />
          </label>
          <button
            onClick={refresh}
            disabled={loading}
            className="inline-flex items-center gap-2 bg-slate-700 hover:bg-slate-800 disabled:opacity-50 text-white text-sm px-3 py-1.5 rounded-md"
          >
            {loading ? <Loader2 size={15} className="animate-spin" /> : <RefreshCw size={15} />}
            새로고침
          </button>
        </div>
      </div>

      {msg && (
        <div className={`text-sm rounded-md p-3 border ${msg.type === "ok" ? "bg-emerald-50 text-emerald-700 border-emerald-200" : "bg-red-50 text-red-700 border-red-200"}`}>
          {msg.text}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <UploadForm onDone={(t) => { setMsg({ type: "ok", text: t }); refresh(); }} onError={(t) => setMsg({ type: "err", text: t })} />
        <IngestTextForm onDone={(t) => { setMsg({ type: "ok", text: t }); refresh(); }} onError={(t) => setMsg({ type: "err", text: t })} />
      </div>

      <div className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-slate-500 text-xs uppercase">
            <tr>
              {["제목", "도메인", "owner", "출처", "상태", "청크", "컴플라이언스", "액션"].map((h) => (
                <th key={h} className="text-left font-medium px-3 py-2 whitespace-nowrap">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {docs.length === 0 && (
              <tr><td colSpan={8} className="text-center text-slate-400 py-8">문서가 없습니다. 업로드 또는 텍스트 적재로 추가하세요.</td></tr>
            )}
            {docs.map((d) => (
              <tr key={d.id} className="hover:bg-slate-50">
                <td className="px-3 py-2 font-medium text-slate-800 max-w-[200px] truncate" title={d.title}>{d.title}</td>
                <td className="px-3 py-2"><span className="font-mono text-xs">{d.domain}</span></td>
                <td className="px-3 py-2 font-mono text-xs max-w-[120px] truncate" title={d.owner_id ?? ""}>{d.owner_id ?? "-"}</td>
                <td className="px-3 py-2 max-w-[140px] truncate" title={d.source_name}>{d.source_name}</td>
                <td className="px-3 py-2">
                  <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${statusBadge(d.embedding_status)}`} title={d.error_message ?? ""}>
                    {d.embedding_status}
                  </span>
                </td>
                <td className="px-3 py-2 text-center">{d.chunk_count}</td>
                <td className="px-3 py-2 text-center">{d.is_compliance_source ? "✓" : "-"}</td>
                <td className="px-3 py-2">
                  <div className="flex gap-1.5">
                    {d.file_name && (
                      <button onClick={() => download(d.id)} className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded-md bg-slate-100 text-slate-700 hover:bg-slate-200">
                        <Download size={13} /> 다운
                      </button>
                    )}
                    <button onClick={() => remove(d.id)} className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded-md bg-red-100 text-red-700 hover:bg-red-200">
                      <Trash2 size={13} /> 삭제
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function UploadForm({ onDone, onError }: { onDone: (t: string) => void; onError: (t: string) => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [domain, setDomain] = useState("policy");
  const [ownerId, setOwnerId] = useState("");
  const [isCompliance, setIsCompliance] = useState(false);
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    if (!file) return onError("파일을 선택하세요.");
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("title", title || file.name);
      fd.append("domain", domain);
      if (ownerId) fd.append("owner_id", ownerId);
      fd.append("is_compliance_source", String(isCompliance));
      await api.post(UPLOAD_URL, fd);
      onDone(`'${title || file.name}' 업로드 완료(PROCESSING).`);
      setFile(null); setTitle("");
    } catch (e) {
      onError(errMessage(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm">
      <h2 className="font-semibold text-slate-700 mb-3 flex items-center gap-2"><Upload size={16} /> 파일 업로드</h2>
      <div className="space-y-3">
        <input type="file" onChange={(e) => setFile(e.target.files?.[0] ?? null)} className="block w-full text-sm text-slate-600" />
        <div className="grid grid-cols-2 gap-3">
          <input className="border border-slate-300 rounded-md px-2 py-1.5 text-sm" placeholder="제목(미입력 시 파일명)" value={title} onChange={(e) => setTitle(e.target.value)} />
          <input className="border border-slate-300 rounded-md px-2 py-1.5 text-sm" placeholder="domain (policy)" value={domain} onChange={(e) => setDomain(e.target.value)} />
          <input className="border border-slate-300 rounded-md px-2 py-1.5 text-sm" placeholder="owner_id (봇 UUID 등, 선택)" value={ownerId} onChange={(e) => setOwnerId(e.target.value)} />
          <label className="text-xs text-slate-500 flex items-center gap-2">
            <input type="checkbox" checked={isCompliance} onChange={(e) => setIsCompliance(e.target.checked)} /> 컴플라이언스 근거 문서
          </label>
        </div>
        <button onClick={submit} disabled={busy} className="inline-flex items-center gap-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-sm px-4 py-2 rounded-md">
          {busy ? <Loader2 size={15} className="animate-spin" /> : <Upload size={15} />} 업로드
        </button>
      </div>
    </div>
  );
}

function IngestTextForm({ onDone, onError }: { onDone: (t: string) => void; onError: (t: string) => void }) {
  const [text, setText] = useState("");
  const [sourceName, setSourceName] = useState("");
  const [domain, setDomain] = useState("policy");
  const [ownerId, setOwnerId] = useState("");
  const [isCompliance, setIsCompliance] = useState(false);
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    if (!text.trim() || !sourceName.trim()) return onError("본문과 출처명을 입력하세요.");
    setBusy(true);
    try {
      await api.post(INGEST_TEXT_URL, {
        text,
        source_name: sourceName,
        domain,
        owner_id: ownerId || null,
        is_compliance_source: isCompliance,
      });
      onDone(`'${sourceName}' 텍스트 적재 완료.`);
      setText("");
    } catch (e) {
      onError(errMessage(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm">
      <h2 className="font-semibold text-slate-700 mb-3 flex items-center gap-2"><FileText size={16} /> 텍스트 즉시 적재</h2>
      <div className="space-y-3">
        <textarea className="border border-slate-300 rounded-md px-2 py-1.5 text-sm w-full h-24 resize-none" placeholder="적재할 규정 원문 텍스트" value={text} onChange={(e) => setText(e.target.value)} />
        <div className="grid grid-cols-2 gap-3">
          <input className="border border-slate-300 rounded-md px-2 py-1.5 text-sm" placeholder="출처명(source_name)" value={sourceName} onChange={(e) => setSourceName(e.target.value)} />
          <input className="border border-slate-300 rounded-md px-2 py-1.5 text-sm" placeholder="domain (policy)" value={domain} onChange={(e) => setDomain(e.target.value)} />
          <input className="border border-slate-300 rounded-md px-2 py-1.5 text-sm" placeholder="owner_id (선택)" value={ownerId} onChange={(e) => setOwnerId(e.target.value)} />
          <label className="text-xs text-slate-500 flex items-center gap-2">
            <input type="checkbox" checked={isCompliance} onChange={(e) => setIsCompliance(e.target.checked)} /> 컴플라이언스 근거 문서
          </label>
        </div>
        <button onClick={submit} disabled={busy} className="inline-flex items-center gap-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-sm px-4 py-2 rounded-md">
          {busy ? <Loader2 size={15} className="animate-spin" /> : <FileText size={15} />} 적재
        </button>
      </div>
    </div>
  );
}
