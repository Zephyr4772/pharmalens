import { useQuery } from "@tanstack/react-query";
import { api, ageDays } from "../lib/api";

export function StatusBar() {
  const health = useQuery({ queryKey: ["healthz"], queryFn: api.healthz, refetchInterval: 30_000 });
  const build = useQuery({ queryKey: ["build"], queryFn: api.build, staleTime: 300_000 });

  const ok = health.data?.ok;
  return (
    <footer className="statusbar">
      <span>
        <span className={"status-dot " + (ok ? "dot-live" : "dot-dead")} />
        FEED {ok ? "LIVE" : "DOWN"}
        {health.data ? ` · ${health.data.probe_ms.toFixed(1)}ms` : ""}
      </span>
      {build.data && (
        <>
          <span>DB v{build.data.schema_version}</span>
          <span>
            {Number(build.data.drugs).toLocaleString("en-IN")} PRODUCTS ·{" "}
            {Number(build.data.companies).toLocaleString("en-IN")} COMPANIES ·{" "}
            {Number(build.data.molecules).toLocaleString("en-IN")} MOLECULES
          </span>
          <span>
            BUILD AGE <b style={{ color: ageDays(build.data.built_at_utc) > 14 ? "var(--warn)" : "var(--up)" }}>
              {ageDays(build.data.built_at_utc)}d
            </b>
          </span>
          <span>SRC {build.data.source_file} (−{Number(build.data.duplicates_removed).toLocaleString("en-IN")} DUPES)</span>
        </>
      )}
      <span className="spacer" />
      <span>
        <kbd>1-6</kbd> screens · <kbd>/</kbd> screener · <kbd>CTRL K</kbd> palette
      </span>
    </footer>
  );
}
