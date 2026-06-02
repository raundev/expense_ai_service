import { useState, type ReactNode } from "react";
import { Receipt, LayoutDashboard } from "lucide-react";
import SettingsPanel from "./components/SettingsPanel";
import SingleRecommendTab from "./components/SingleRecommendTab";
import ComplianceTab from "./components/ComplianceTab";
import { loadSettings, saveSettings, type Settings } from "./api";

type Tab = "single" | "compliance";

export default function App() {
  const [settings, setSettings] = useState<Settings>(() => loadSettings());
  const [tab, setTab] = useState<Tab>("single");

  const update = (patch: Partial<Settings>) => {
    setSettings((prev) => {
      const next = { ...prev, ...patch };
      saveSettings(next);
      return next;
    });
  };

  return (
    <div className="min-h-full">
      <header className="bg-slate-900 text-white">
        <div className="max-w-6xl mx-auto px-4 py-4">
          <h1 className="text-lg font-bold">Bizplay AI · 컴플라이언스 테스트 콘솔</h1>
          <p className="text-slate-400 text-xs">
            영수증 추천 + RAG 컴플라이언스 감사 API 통합 테스트 (Phase 1)
          </p>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-4 py-6 space-y-6">
        <SettingsPanel settings={settings} onChange={update} />

        <div className="flex gap-1 border-b border-slate-200">
          <TabButton active={tab === "single"} onClick={() => setTab("single")} icon={<Receipt size={16} />}>
            단건 추천 &amp; 감사
          </TabButton>
          <TabButton active={tab === "compliance"} onClick={() => setTab("compliance")} icon={<LayoutDashboard size={16} />}>
            컴플라이언스 대시보드
          </TabButton>
        </div>

        {tab === "single" ? <SingleRecommendTab /> : <ComplianceTab />}
      </main>
    </div>
  );
}

function TabButton({
  active,
  onClick,
  icon,
  children,
}: {
  active: boolean;
  onClick: () => void;
  icon: ReactNode;
  children: ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={`inline-flex items-center gap-2 px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
        active
          ? "border-blue-600 text-blue-700"
          : "border-transparent text-slate-500 hover:text-slate-700"
      }`}
    >
      {icon}
      {children}
    </button>
  );
}
