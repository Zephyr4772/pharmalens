import { useQuery } from "@tanstack/react-query";
import { get, type Row } from "../lib/api";
import { useLive } from "../state/live";

function Items() {
  const quotes = useQuery({ queryKey: ["quotes"], queryFn: () => get<{ data: Row[] }>("/quotes"), refetchInterval: 120_000 });
  const ev = useQuery({ queryKey: ["events", "tape"], queryFn: () => get("/events", { limit: 12, severity: "critical,high" }) });
  const live = useLive((s) => s.events);
  const items: React.ReactNode[] = [];
  for (const q of quotes.data?.data ?? []) {
    if (q.price == null) continue;
    const sym = q.ticker.replace(".NS", "").replace("^CNXPHARMA", "NIFTY PHARMA").replace("^NSEI", "NIFTY 50");
    items.push(
      <span className="tape-item" key={q.ticker}>
        <span className="tape-sym">{sym}</span>
        <span className="tape-val">{q.price.toLocaleString("en-IN", { maximumFractionDigits: 1 })}</span>
        {q.change_pct != null && <span className={q.change_pct >= 0 ? "tape-pos" : "tape-neg"}>{q.change_pct >= 0 ? "▲" : "▼"}{Math.abs(q.change_pct).toFixed(2)}%</span>}
      </span>
    );
  }
  const evs = [...live.filter((e) => ["critical", "high"].includes(e.severity)), ...(ev.data?.data ?? [])].slice(0, 12);
  evs.forEach((e: Row, i) => {
    items.splice(Math.min(items.length, (i + 1) * 4), 0,
      <span className="tape-item" key={"e" + e.id}>
        <span className={e.severity === "critical" ? "tape-neg" : "tape-warn"}>■ {String(e.kind).toUpperCase()}</span>
        <span className="tape-val">{String(e.title).slice(0, 90)}</span>
      </span>);
  });
  if (!items.length) items.push(<span key="w" className="tape-item tape-sym">connecting to feeds…</span>);
  return <>{items}</>;
}

export function TickerTape() {
  return (
    <div className="tape-wrap">
      <span className="tape-label">LIVE·IN</span>
      <div className="tape-scroll"><Items /><Items /></div>
    </div>
  );
}
