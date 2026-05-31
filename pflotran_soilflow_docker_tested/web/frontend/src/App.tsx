import { useEffect, useState } from "react";
import { AuthPanel } from "./components/AuthPanel";
import { Layout } from "./components/Layout";
import { clearApiToken } from "./api/client";
import { DashboardPage } from "./pages/DashboardPage";
import { InputsPage } from "./pages/InputsPage";
import { JobsPage } from "./pages/JobsPage";
import { ResultsPage } from "./pages/ResultsPage";
import { SystemPage } from "./pages/SystemPage";
import { TestsPage } from "./pages/TestsPage";
import { VisualizationPage } from "./pages/VisualizationPage";
import { ROUTES, normalizeRoute } from "./routes";

export default function App() {
  const [path, setPath] = useState(normalizeRoute(window.location.pathname));
  const [, setJobSignal] = useState(0);
  const [authRequired, setAuthRequired] = useState(false);
  const [authSignal, setAuthSignal] = useState(0);

  function navigate(nextPath: string) {
    const nextUrl = new URL(nextPath, window.location.origin);
    const normalized = normalizeRoute(nextUrl.pathname);
    window.history.pushState({}, "", `${normalized}${nextUrl.search}`);
    setPath(normalized);
  }

  useEffect(() => {
    const normalized = normalizeRoute(window.location.pathname);
    if (normalized !== window.location.pathname) {
      window.history.replaceState({}, "", normalized);
    }
    const onPop = () => setPath(normalizeRoute(window.location.pathname));
    window.addEventListener("popstate", onPop);
    const onAuthRequired = () => setAuthRequired(true);
    window.addEventListener("soilflow-auth-required", onAuthRequired);
    return () => {
      window.removeEventListener("popstate", onPop);
      window.removeEventListener("soilflow-auth-required", onAuthRequired);
    };
  }, []);

  function logout() {
    clearApiToken();
    setAuthRequired(true);
  }

  function handleAuthVerified() {
    setAuthRequired(false);
    setAuthSignal((value) => value + 1);
  }

  let page = <DashboardPage onNavigate={navigate} onJobCreated={() => setJobSignal((value) => value + 1)} />;
  if (path === ROUTES.inputs) {
    page = <InputsPage />;
  } else if (path === ROUTES.jobs) {
    page = <JobsPage />;
  } else if (path === ROUTES.tests) {
    page = <TestsPage onNavigate={navigate} />;
  } else if (path === ROUTES.results) {
    page = <ResultsPage onNavigate={navigate} />;
  } else if (path === ROUTES.visualization) {
    page = <VisualizationPage />;
  } else if (path === ROUTES.system) {
    page = <SystemPage />;
  }

  return (
    <>
      <Layout key={authSignal} path={path} onNavigate={navigate} onLogout={logout}>
        {page}
      </Layout>
      <AuthPanel visible={authRequired} onVerified={handleAuthVerified} />
    </>
  );
}
