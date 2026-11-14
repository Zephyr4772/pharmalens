import { useMemo, useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate, useSearchParams } from "react-router-dom";
import { crore, csvUrl, day, get, pct, signed, type Row } from "../lib/api";
import { useWatchlist } from "../state/watchlist";
import { ErrorBox, Kpi, Loading, Panel, Star, useSort, Csv } from "../components/ui";

// Public-record red flags (same thresholds as Specs' /sanity); hover a badge for the reason.
export function Flags({ f }: { f: Row[] }) {
  if (!f.length) return <span className="faint">—</span>;
  return <>{f.map((x) => <span key={x.label} title={x.why} className={`badge ${x.level === "red" ? "b-down" : "b-warn"}`} style={{ marginRight: 3 }}>{x.label}</span>)}</>;
}

const FILTERS: [string, string, (r: Row, watched: Set<string>) => boolean][] = [
  ["all", "All", () => true],
  ["watched", "Watched", (r, w) => w.has(`g:${r.slug}`)],
  ["week", "Reporting ≤7d", (r) => !!r.next_results && (new Date(r.next_results).getTime() - Date.now()) / 864e5 <= 7],
  ["growth", "Revenue & profit up YoY", (r) => r.rev_yoy > 0 && r.profit_yoy > 0],
  ["red", "Red flags", (r) => r.flags.some((f: Row) => f.level === "red")],
  ["clean", "No flags", (r) => !r.flags.length],
];

const yoy = (n: number | null | undefined) => <span className={n == null ? "faint" : n >= 0 ? "pos" : "neg"}>{signed(n, 0)}</span>;
const TREND: Record<string, ReactNode> = { rising: <span className="neg">▲</span>, falling: <span className="pos">▼</span>, flat: <span className="faint">·</span> };

// One screen of every listed Indian pharma group: price, growth, margins, quality and governance signals.
export default function Companies() {
  const nav = useNavigate();
  const [sp, setSp] = useSearchParams();
  const f = sp.get("f") ?? "all";
  const [text, setText] = useState("");
  const q = useQuery({ queryKey: ["invest-companies"], queryFn: () => get<{ data: Row[] }>("/invest/companies"), refetchInterval: 300_000 });
  const items = useWatchlist((s) => s.items);
  const watched = useMemo(() => new Set(items.map((i) => i.key)), [items]);
  const pred = (FILTERS.find((x) => x[0] === f) ?? FILTERS[0])[2];
  const rows = useMemo(() => (q.data?.data ?? []).filter((r) => pred(r, watched)
    && (!text || `${r.name} ${r.ticker}`.toLowerCase().includes(text.toLowerCase()))), [q.data, f, text, watched]); // eslint-disable-line react-hooks/exhaustive-deps
  const { sorted, th } = useSort(rows, "market_cap");

  if (q.isLoading) return <Loading what="loading companies" />;
  if (q.error) return <ErrorBox e={q.error} />;
  const all = q.data!.data;
  const withQ = all.filter((r) => r.rev_yoy != null);
  const med = (xs: number[]) => { const s = [...xs].sort((a, b) => a - b); return s.length ? s[Math.floor(s.length / 2)] : null; };

  return (
    <div className="stack">
      <div className="kpis">
        <Kpi label="Listed groups" value={all.length} sub={`${withQ.length} with comparable results`} />
        <Kpi label="Median revenue YoY" value={signed(med(withQ.map((r) => r.rev_yoy)), 1)} sub="latest quarter, consolidated" tone="amber" />
        <Kpi label="Median profit YoY" value={signed(med(all.filter((r) => r.profit_yoy != null).map((r) => r.profit_yoy)), 1)} />
        <Kpi label="Growing both" value={all.filter((r) => r.rev_yoy > 0 && r.profit_yoy > 0).length} sub="revenue and profit up YoY" tone="up" />
        <Kpi label="With red flags" value={all.filter((r) => r.flags.some((x: Row) => x.level === "red")).length} sub="quality · USFDA · orders · mgmt · losses" tone="down" />
        <Kpi label="Reporting ≤7 days" value={all.filter(FILTERS[2][2] as (r: Row) => boolean).length} />
      </div>
      <Panel title="Companies" sub="listed Indian pharma groups · click a row for the dossier · hover a flag for the reason"
        right={<Csv href={csvUrl("/invest/companies")} label="CSV ↓" />}>
        <div className="chips" style={{ marginBottom: 8, alignItems: "center" }}>
          <input placeholder="filter by name or ticker" value={text} onChange={(e) => setText(e.target.value)} style={{ marginRight: 8, minWidth: 200 }} />
          {FILTERS.map(([k, label]) => (
            <button key={k} className={`chip ${f === k ? "chip-on" : ""}`} onClick={() => setSp(k === "all" ? {} : { f: k })}>{label}</button>
          ))}
          <span className="faint" style={{ marginLeft: "auto" }}>{sorted.length} shown</span>
        </div>
        <div style={{ overflowX: "auto" }}>
          <table className="tt">
            <thead><tr><th />{th("ticker", "Ticker")}{th("name", "Group")}{th("price", "Last", "num")}{th("change_pct", "Chg", "num")}{th("chg_1y", "1Y", "num")}
              {th("market_cap", "Mkt cap", "num")}{th("pe", "P/E", "num")}{th("period_end", "Qtr")}{th("revenue", "Revenue ₹cr", "num")}
              {th("rev_yoy", "Rev YoY", "num")}{th("profit_yoy", "Profit YoY", "num")}{th("margin", "Net margin", "num")}
              {th("nsq_12m", "NSQ 12m", "num")}{th("fda_alerts_2y", "FDA IA 2y", "num")}{th("dpco_share", "DPCO %", "num")}
              {th("risk", "Flags")}{th("next_results", "Next results")}</tr></thead>
            <tbody>{sorted.map((r) => {
              const dm = r.margin != null && r.margin_prev != null ? r.margin - r.margin_prev : null;
              return (
                <tr key={r.slug} onClick={() => nav(`/g/${r.slug}`)}>
                  <td><Star k={`g:${r.slug}`} label={r.name} href={`/g/${r.slug}`} /></td>
                  <td className="amb">{r.ticker}</td>
                  <td>{r.name}</td>
                  <td className="num">{r.price?.toLocaleString("en-IN", { maximumFractionDigits: 1 }) ?? "—"}</td>
                  <td className={`num ${r.change_pct >= 0 ? "pos" : "neg"}`}>{signed(r.change_pct)}</td>
                  <td className="num">{yoy(r.chg_1y)}</td>
                  <td className="num">{crore(r.market_cap)}</td>
                  <td className="num mut">{r.pe ? r.pe.toFixed(1) : "—"}</td>
                  <td className="mut" title={r.filed_at ? `filed ${day(r.filed_at)}` : ""}>{r.quarter ?? "—"}</td>
                  <td className="num">{r.revenue != null ? r.revenue.toLocaleString("en-IN", { maximumFractionDigits: 0 }) : "—"}</td>
                  <td className="num">{yoy(r.rev_yoy)}</td>
                  <td className="num">{(r.net_profit ?? 0) < 0 ? <span className="neg">loss</span> : yoy(r.profit_yoy)}</td>
                  <td className="num" title={dm != null ? `${dm >= 0 ? "+" : ""}${dm.toFixed(1)} pts vs a year earlier` : ""}>
                    {pct(r.margin)}{dm != null && <span className={dm >= 0 ? "pos" : "neg"}> {dm >= 0 ? "▲" : "▼"}</span>}
                  </td>
                  <td className="num" title={`${r.nsq_prev} the year before`}>{r.nsq_12m} {TREND[r.quality_trend]}</td>
                  <td className={`num ${r.fda_alerts_2y ? "neg" : "faint"}`}>{r.fda_alerts_2y}</td>
                  <td className="num mut">{r.dpco_share != null ? `${r.dpco_share.toFixed(0)}%` : "—"}</td>
                  <td><Flags f={r.flags} /></td>
                  <td className="mut">{r.next_results ? day(r.next_results) : ""}</td>
                </tr>
              );
            })}</tbody>
          </table>
        </div>
        <div className="faint" style={{ marginTop: 6 }}>
          YoY compares with the same quarter a year earlier. NSQ: failed-quality batches in CDSCO/state lists (▲ more than the year before).
          FDA IA: US FDA import alerts. DPCO %: share of active SKUs with an NPPA ceiling-priced molecule. Flags come from public records only;
          no flag is not a clean bill of health.
        </div>
      </Panel>
    </div>
  );
}
