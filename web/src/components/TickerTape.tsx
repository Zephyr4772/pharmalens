import { useQuery } from "@tanstack/react-query";
import { api, inr } from "../lib/api";

function TapeContent() {
  const arb = useQuery({ queryKey: ["arb-tape"], queryFn: () => api.arbitrage(14), staleTime: 120_000 });
  const build = useQuery({ queryKey: ["build"], queryFn: api.build, staleTime: 300_000 });

  const items: React.ReactNode[] = [];
  if (build.data) {
    items.push(
      <span className="tape-item" key="b">
        <span className="tape-sym">BUILD</span>
        <span className="tape-val">{new Date(build.data.built_at_utc).toLocaleDateString("en-IN")}</span>
        <span className="tape-pos">{Number(build.data.drugs).toLocaleString("en-IN")} PRODUCTS</span>
      </span>,
      <span className="tape-item" key="a">
        <span className="tape-sym">CDSCO NSQ</span>
        <span className={Number(build.data.nsq_alerts) > 0 ? "tape-neg" : "tape-pos"}>
          {build.data.nsq_alerts} ALERTS
        </span>
      </span>
    );
  }
  for (const r of arb.data?.data ?? []) {
    items.push(
      <span className="tape-item" key={"m" + r.salt.id}>
        <span className="tape-sym">{r.salt.comp.slice(0, 26)}</span>
        <span className="tape-val">{inr(r.cheapest)}</span>
        <span className="tape-pos">▲{r.savings_pct.toFixed(0)}% SPREAD</span>
        <span className="tape-sym">{r.brands} BRANDS</span>
      </span>
    );
  }
  if (!items.length) items.push(<span key="w" className="tape-item tape-sym">connecting to feed…</span>);
  return <>{items}</>;
}

export function TickerTape() {
  return (
    <div className="tape-wrap">
      <span className="tape-label">LIVE·IN</span>
      <div className="tape-scroll">
        <TapeContent />
        <TapeContent />
      </div>
    </div>
  );
}
