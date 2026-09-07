import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { RequireAuth } from "./auth";
import { Layout } from "./components/Layout";
import { AdminPage } from "./pages/Admin";
import { ClusterDetailPage, ClustersPage } from "./pages/Clusters";
import { DashboardPage } from "./pages/Dashboard";
import { LoginPage } from "./pages/Login";
import { ReportDetailPage } from "./pages/ReportDetail";
import { TriagePage } from "./pages/Triage";
import { IngestionPage } from "./pages/Ingestion";

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route element={<RequireAuth />}>
          <Route element={<Layout />}>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/triage" element={<TriagePage />} />
            <Route path="/reports/:id" element={<ReportDetailPage />} />
            <Route path="/clusters" element={<ClustersPage />} />
            <Route path="/clusters/:id" element={<ClusterDetailPage />} />
            <Route path="/ingestion" element={<IngestionPage />} />
            <Route element={<RequireAuth roles={["admin"]} />}>
              <Route path="/admin" element={<AdminPage />} />
            </Route>
          </Route>
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
