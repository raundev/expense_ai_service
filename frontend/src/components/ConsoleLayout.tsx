import { NavLink, Outlet, useNavigate } from "react-router-dom";
import {
  Receipt,
  ListChecks,
  MessagesSquare,
  FileText,
  ShieldCheck,
  Settings2,
  Building2,
  LogOut,
  type LucideIcon,
} from "lucide-react";
import { loadSettings } from "../api";

// 콘솔 좌측 사이드바 메뉴 — 요구된 6개 메뉴 순서대로.
const MENUS: { to: string; label: string; icon: LucideIcon }[] = [
  { to: "/console/receipts", label: "영수증", icon: Receipt },
  { to: "/console/rules", label: "룰 조회", icon: ListChecks },
  { to: "/console/rag", label: "RAG", icon: MessagesSquare },
  { to: "/console/documents", label: "Document", icon: FileText },
  { to: "/console/compliance", label: "Compliance Admin", icon: ShieldCheck },
  { to: "/console/admin", label: "Admin", icon: Settings2 },
];

export default function ConsoleLayout() {
  const navigate = useNavigate();
  const s = loadSettings();

  return (
    <div className="min-h-screen flex bg-slate-100">
      {/* 사이드바 */}
      <aside className="w-56 shrink-0 bg-slate-900 text-slate-300 flex flex-col">
        <div className="px-4 py-4 border-b border-slate-800">
          <div className="flex items-center gap-2 text-white font-bold text-sm">
            <Building2 size={18} /> Bizplay AI 콘솔
          </div>
          <p className="text-[11px] text-slate-500 mt-0.5">API 통합 테스트</p>
        </div>

        <nav className="flex-1 p-2 space-y-1">
          {MENUS.map((m) => (
            <NavLink
              key={m.to}
              to={m.to}
              className={({ isActive }) =>
                `flex items-center gap-2.5 px-3 py-2 rounded-md text-sm transition-colors ${
                  isActive
                    ? "bg-blue-600 text-white"
                    : "text-slate-300 hover:bg-slate-800 hover:text-white"
                }`
              }
            >
              <m.icon size={16} />
              {m.label}
            </NavLink>
          ))}
        </nav>

        <div className="p-3 border-t border-slate-800 text-[11px] text-slate-500">
          <div className="truncate">회사: <span className="text-slate-300">{s.companyId}</span></div>
          <div className="truncate">사업장: <span className="text-slate-300">{s.workplaceId}</span></div>
        </div>
      </aside>

      {/* 본문 */}
      <div className="flex-1 flex flex-col min-w-0">
        <header className="bg-white border-b border-slate-200 px-6 py-3 flex items-center justify-between">
          <div className="text-sm text-slate-500">
            <span className="font-mono text-slate-700">{s.baseUrl}</span>
            <span className="mx-2 text-slate-300">·</span>
            테넌트 <span className="font-semibold text-slate-700">{s.companyId} / {s.workplaceId}</span>
          </div>
          <button
            onClick={() => navigate("/")}
            className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-800 border border-slate-300 hover:border-slate-400 rounded-md px-3 py-1.5"
          >
            <LogOut size={15} /> 테넌트 변경
          </button>
        </header>

        <main className="flex-1 p-6 overflow-x-hidden">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
