import { Navigate, Route, Routes } from "react-router-dom";
import { hasTenant } from "./api";
import EntryGate from "./components/EntryGate";
import ConsoleLayout from "./components/ConsoleLayout";
import ReceiptsPage from "./pages/ReceiptsPage";
import RulesPage from "./pages/RulesPage";
import RagPage from "./pages/RagPage";
import DocumentsPage from "./pages/DocumentsPage";
import ComplianceAdminPage from "./pages/ComplianceAdminPage";
import AdminPage from "./pages/AdminPage";

// 테넌트(회사/사업장) 미설정 시 진입 게이트로 돌려보내는 가드.
function RequireTenant({ children }: { children: JSX.Element }) {
  return hasTenant() ? children : <Navigate to="/" replace />;
}

export default function App() {
  return (
    <Routes>
      {/* 진입 페이지: 테넌트 정보(회사/사업장) 기준으로 콘솔에 진입 */}
      <Route path="/" element={<EntryGate />} />

      {/* 콘솔: 6개 메뉴. 테넌트 미설정이면 진입 게이트로 리다이렉트 */}
      <Route
        path="/console"
        element={
          <RequireTenant>
            <ConsoleLayout />
          </RequireTenant>
        }
      >
        <Route index element={<Navigate to="receipts" replace />} />
        <Route path="receipts" element={<ReceiptsPage />} />
        <Route path="rules" element={<RulesPage />} />
        <Route path="rag" element={<RagPage />} />
        <Route path="documents" element={<DocumentsPage />} />
        <Route path="compliance" element={<ComplianceAdminPage />} />
        <Route path="admin" element={<AdminPage />} />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
