import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { ago, crore, get, signed, type Row } from "../lib/api";
import { Kpi, Loading, Panel, Spark, useSort } from "../components/ui";

export default function Equities() {
  const nav = useNavigate();
  const q = useQuery({ queryKey: ["quotes"], queryFn: () => get<{ data: Row[] }>("/quotes"), refetchInterval: 60_000 });
  const all = q.data?.data ?? [];
  const isIdx = (t: string) => t.startsWith("^") || t.startsWith("NIFTY");
  const rows = all.filter((r) => !isIdx(r.ticker));
  const idx = all.filter((r) => isIdx(r.ticker));
  const { sorted, th } = useSort(rows, "market_cap");
  if (q.isLoading) return <Loading />;
  const adv = rows.filter((r) => r.change_pct > 0).length;
  const cap = rows.reduce((a, r) => a + (r.market_cap ?? 0), 0);
  return (
    <div className="stack">
      <div className="kpis">
        {idx.map((i) => (
          <Kpi key={i.ticker} label={i.name} value={i.price?.toLocaleString("en-IN", { maximumFractionDigits: 0 }) ?? "—"}
            sub={<span className={i.change_pct >= 0 ? "pos" : "neg"}>{signed(i.change_pct)}</span>} tone="amber" />
        ))}
        <Kpi label="Breadth" value={`${adv} ▲ / ${rows.length - adv} ▼`} />
        <Kpi label="Tracked market cap" value={crore(cap)} />
        <Kpi label="Quote age" value={ago(rows[0]?.quoted_at)} sub="NSE via Yahoo, ~15 min delay" />
      </div>
      <Panel title="Listed Indian pharma groups" sub="click a row for the group dossier: portfolio, market share, quality record, news">
        <table className="tt">
          <thead><tr>{th("ticker", "Ticker")}{th("name", "Group")}{th("price", "Last", "num")}{th("change_pct", "Chg", "num")}<th>35d</th>
            {th("market_cap", "Mkt cap", "num")}{th("week52_low", "52w low", "num")}{th("week52_high", "52w high", "num")}{th("volume", "Volume", "num")}</tr></thead>
          <tbody>{sorted.map((r) => (
            <tr key={r.ticker} onClick={() => r.slug && nav(`/g/${r.slug}`)}>
              <td className="amb">{r.ticker.replace(".NS", "")}</td>
              <td>{r.group_name ?? r.name}</td>
              <td className="num">{r.price?.toLocaleString("en-IN", { maximumFractionDigits: 2 })}</td>
              <td className={`num ${r.change_pct >= 0 ? "pos" : "neg"}`}>{signed(r.change_pct)}</td>
              <td><Spark data={r.spark} /></td>
              <td className="num">{crore(r.market_cap)}</td>
              <td className="num mut">{r.week52_low?.toFixed(0) ?? "—"}</td>
              <td className="num mut">{r.week52_high?.toFixed(0) ?? "—"}</td>
              <td className="num mut">{r.volume ? (r.volume / 1e5).toFixed(1) + " L" : "—"}</td>
            </tr>
          ))}</tbody>
        </table>
      </Panel>
    </div>
  );
}
