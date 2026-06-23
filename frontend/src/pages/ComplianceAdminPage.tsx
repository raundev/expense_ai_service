import ComplianceTab from "../components/ComplianceTab";

// Compliance Admin 메뉴 — KPI 대시보드 + 위반 그리드 + 소명 워크플로우(기존 컴포넌트 재사용).
export default function ComplianceAdminPage() {
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-bold text-slate-800">Compliance Admin</h1>
        <p className="text-sm text-slate-500">위반 탐지 KPI와 그리드를 조회하고 소명(미요청→요청완료→정상처리/위반확정) 상태를 전이합니다.</p>
      </div>
      <ComplianceTab />
    </div>
  );
}
