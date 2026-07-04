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
import NotFound from "./pages/NotFound";
import { useGhostAuth } from "@/components/auth/ghost-auth/react/useGhostAuth";
import { useIsAdmin } from "@/hooks/useIsAdmin";
import { AccountModalProvider } from "@/components/auth/AccountModalProvider";
import { LoginModalProvider } from "@/components/auth/LoginModalProvider";
import { useLoginModal } from "@/components/auth/useLoginModal";

const queryClient = new QueryClient();

const routerBasename =
  import.meta.env.BASE_URL.replace(/\/$/, "") || undefined;

// Keeps path comparisons stable for `/app` and `/app/`.
const normalizePath = (path: string) => {
  const normalized = path.replace(/\/+$/, "");
  return normalized === "" ? "/" : normalized;
};

const initialPathname =
  typeof window !== "undefined" ? normalizePath(window.location.pathname) : "/";

const initialBasePath = normalizePath(routerBasename ?? "/");

const shouldCheckInitialRootRedirect = initialPathname === initialBasePath;

let hasHandledInitialRootRoute = false;

function shouldRunInitialRootRedirect(token: string | null) {
  return (
    !hasHandledInitialRootRoute &&
    shouldCheckInitialRootRedirect &&
    Boolean(token)
  );
}

function markInitialRootRouteAsHandled() {
  // Redirect should be evaluated only once, during the very first root render.
  hasHandledInitialRootRoute = true;
}

function RootRoute() {
  const token = useGhostAuth();
  const shouldRedirectNow = shouldRunInitialRootRedirect(token);
  markInitialRootRouteAsHandled();

  if (shouldRedirectNow) {
    return <Navigate to="/selecao" replace />;
  }

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
  // PREVIEW LOCAL (NÃO COMMITAR): libera acesso quando VITE_ADMIN_DEV_BYPASS=true.
  const bypass = import.meta.env.VITE_ADMIN_DEV_BYPASS === 'true';
  const token = useGhostAuth();
  const { isAdmin, isLoading } = useIsAdmin();

  if (bypass) {
    return children;
  }
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
