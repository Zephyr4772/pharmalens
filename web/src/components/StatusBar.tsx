import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { ago, get, type Row } from "../lib/api";

export function StatusBar() {
  const health = useQuery({ queryKey: ["healthz"], queryFn: () => get("/healthz"), refetchInterval: 30_000 });
  const build = useQuery({ queryKey: ["build"], queryFn: () => get<Record<string, string>>("/meta/build"), staleTime: 600_000 });
  const feeds = useQuery({ queryKey: ["feeds"], queryFn: () => get<{ data: Row[] }>("/meta/feeds"), refetchInterval: 60_000 });
  const ok = health.data?.ok;
  const f = feeds.data?.data ?? [];
  const bad = f.filter((x) => x.last_status === "error").length;
  const fresh = f.filter((x) => x.last_ok).length;
  const lastRun = f.map((x) => x.last_run).filter(Boolean).sort().pop();
  return (
    <footer className="statusbar">
      <span><span className={"status-dot " + (ok ? "dot-live" : "dot-dead")} />API {ok ? "UP" : "DOWN"}{health.data ? ` ${health.data.probe_ms}ms` : ""}</span>
      <Link to="/feeds" className="sb-link">FEEDS {fresh}/{f.length} OK{bad ? <b style={{ color: "var(--down)" }}> · {bad} ERR</b> : ""} · last sync {ago(lastRun)} ago</Link>
      {build.data && (
        <span>CATALOG {Number(build.data.products).toLocaleString("en-IN")} SKUs · {Number(build.data.molecules).toLocaleString("en-IN")} molecules · {Number(build.data.companies).toLocaleString("en-IN")} companies</span>
      )}
      <span className="spacer" />
      <span><kbd>1-9</kbd> <kbd>0</kbd> <kbd>W</kbd> screens · <kbd>CTRL K</kbd> search</span>
    </footer>
  );
}
