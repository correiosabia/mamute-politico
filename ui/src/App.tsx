import { useEffect } from "react";
import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import Index from "./pages/Index";
import SelecaoPage from "./pages/SelecaoPage";
import ParlamentarDashboard from "./pages/ParlamentarDashboard";
import DashboardPage from "./pages/DashboardPage";
import PesquisaIAPage from "./pages/PesquisaIAPage";
import AdminPage from "./pages/AdminPage";
import AdminTiersPage from "./pages/AdminTiersPage";
import AdminMetricsPage from "./pages/AdminMetricsPage";
import AdminMetricsUsersPage from "./pages/AdminMetricsUsersPage";
import AdminToolsPage from "./pages/AdminToolsPage";
import AdminParliamentariansPage from "./pages/AdminParliamentariansPage";
import AdminIaPage from "./pages/AdminIaPage";
import AdminEmailsPage from "./pages/AdminEmailsPage";
import AdminUserDetailPage from "./pages/AdminUserDetailPage";
import AdminCoveragePage from "./pages/AdminCoveragePage";
import NotFound from "./pages/NotFound";
import { useGhostAuth } from "@/components/auth/ghost-auth/react/useGhostAuth";
import { useIsAdmin } from "@/hooks/useIsAdmin";
import { PageViewBeacon } from "@/components/PageViewBeacon";
import { AccountModalProvider } from "@/components/auth/AccountModalProvider";
import { LoginModalProvider } from "@/components/auth/LoginModalProvider";
import { useLoginModal } from "@/components/auth/useLoginModal";

const queryClient = new QueryClient();

const routerBasename =
  import.meta.env.BASE_URL.replace(/\/$/, "") || undefined;

export function RootRoute() {
  // A raiz sempre mostra a tela de Início. (Antes, um usuário logado era
  // redirecionado para /selecao no primeiro carregamento da raiz.)
  return <Index />;
}

function RequireAuth({ children }: { children: JSX.Element }) {
  const token = useGhostAuth();
  const { openLogin } = useLoginModal();

  useEffect(() => {
    if (!token) {
      openLogin();
    }
  }, [token, openLogin]);

  if (!token) {
    return <Navigate to="/" replace />;
  }

  return children;
}

function RequireAdmin({ children }: { children: JSX.Element }) {
  const token = useGhostAuth();
  const { isAdmin, isLoading } = useIsAdmin();

  if (!token) {
    return <Navigate to="/" replace />;
  }
  if (isLoading) {
    return null;
  }
  if (!isAdmin) {
    return <Navigate to="/" replace />;
  }
  return children;
}

const App = () => (
  <QueryClientProvider client={queryClient}>
    <TooltipProvider>
      <Toaster />
      <Sonner />
      <LoginModalProvider>
        <AccountModalProvider>
          <BrowserRouter basename={routerBasename}>
            <PageViewBeacon />
            <Routes>
              <Route path="/" element={<RootRoute />} />
              <Route
                path="/selecao"
                element={
                  <RequireAuth>
                    <SelecaoPage />
                  </RequireAuth>
                }
              />
              <Route
                path="/parlamentar/:id"
                element={
                  <RequireAuth>
                    <ParlamentarDashboard />
                  </RequireAuth>
                }
              />
              <Route
                path="/dashboard"
                element={
                  <RequireAuth>
                    <DashboardPage />
                  </RequireAuth>
                }
              />
              <Route
                path="/pesquisa"
                element={
                  <RequireAuth>
                    <PesquisaIAPage />
                  </RequireAuth>
                }
              />
              <Route
                path="/admin"
                element={
                  <RequireAdmin>
                    <AdminPage />
                  </RequireAdmin>
                }
              />
              <Route
                path="/admin/tiers"
                element={
                  <RequireAdmin>
                    <AdminTiersPage />
                  </RequireAdmin>
                }
              />
              <Route
                path="/admin/metrics"
                element={
                  <RequireAdmin>
                    <AdminMetricsPage />
                  </RequireAdmin>
                }
              />
              <Route
                path="/admin/metrics/por-usuario"
                element={
                  <RequireAdmin>
                    <AdminMetricsUsersPage />
                  </RequireAdmin>
                }
              />
              <Route
                path="/admin/metrics/ferramentas"
                element={
                  <RequireAdmin>
                    <AdminToolsPage />
                  </RequireAdmin>
                }
              />
              <Route
                path="/admin/metrics/parlamentares"
                element={
                  <RequireAdmin>
                    <AdminParliamentariansPage />
                  </RequireAdmin>
                }
              />
              <Route
                path="/admin/metrics/ia"
                element={
                  <RequireAdmin>
                    <AdminIaPage />
                  </RequireAdmin>
                }
              />
              <Route
                path="/admin/metrics/emails"
                element={
                  <RequireAdmin>
                    <AdminEmailsPage />
                  </RequireAdmin>
                }
              />
              <Route
                path="/admin/metrics/users/:id"
                element={
                  <RequireAdmin>
                    <AdminUserDetailPage />
                  </RequireAdmin>
                }
              />
              <Route
                path="/admin/coverage"
                element={
                  <RequireAdmin>
                    <AdminCoveragePage />
                  </RequireAdmin>
                }
              />
              {/* ADD ALL CUSTOM ROUTES ABOVE THE CATCH-ALL "*" ROUTE */}
              <Route path="*" element={<NotFound />} />
            </Routes>
          </BrowserRouter>
        </AccountModalProvider>
      </LoginModalProvider>
    </TooltipProvider>
  </QueryClientProvider>
);

export default App;
