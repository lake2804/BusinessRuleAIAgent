import { useEffect, useState } from "react";
import { AppShell, PageId } from "./components/AppShell";
import { RagKnowledgePage } from "./pages/RagKnowledgePage";
import { ReviewPage } from "./pages/ReviewPage";
import { SettingsPage } from "./pages/SettingsPage";

function readRoute() {
  const path = window.location.pathname;
  const page: PageId = path.startsWith("/review") ? "review" : path.startsWith("/settings") ? "settings" : "rag";
  const domainId = path.startsWith("/rag/") ? decodeURIComponent(path.slice("/rag/".length)) : "";
  return { page, domainId };
}

export function App() {
  const [route, setRoute] = useState(readRoute);

  useEffect(() => {
    const onPopState = () => setRoute(readRoute());
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  function navigate(path: string) {
    window.history.pushState({}, "", path);
    setRoute(readRoute());
  }

  function changePage(nextPage: PageId) {
    navigate(nextPage === "rag" ? "/rag" : `/${nextPage}`);
  }

  return (
    <AppShell page={route.page} onPageChange={changePage}>
      {route.page === "rag" && <RagKnowledgePage routeDomainId={route.domainId} navigate={navigate} />}
      {route.page === "review" && <ReviewPage />}
      {route.page === "settings" && <SettingsPage />}
    </AppShell>
  );
}
