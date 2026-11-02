import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { ago, day, get, pct, signed, type Row } from "../lib/api";
import { useLive } from "../state/live";
import { useWatchlist } from "../state/watchlist";
import { Empty, ErrorBox, Kpi, Loading, Panel, Star } from "../components/ui";
import { Flags } from "./Companies";

const yoy = (n: number | null | undefined) => <span className={n == null ? "faint" : n >= 0 ? "pos" : "neg"}>{signed(n, 0)}</span>;
const price = (n: number | null | undefined) => (n == null ? "—" : n.toLocaleString("en-IN", { maximumFractionDigits: n < 1000 ? 1 : 0 }));

// Investor home: what you follow, what moved, who reports this week, and the day's signals ranked by importance.
export default function Today() {
  const nav = useNavigate();
  const keys = useWatchlist((s) => s.items.map((i) => i.key).join("|"));
  const q = useQuery({ queryKey: ["today", keys], queryFn: () => get("/invest/today"), refetchInterval: 120_000 });
  const live = useLive();
  useEffect(() => { live.markSeen(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  if (q.isLoading) return <Loading what="loading today" />;
  if (q.error) return <ErrorBox e={q.error} />;
  const t = q.data;
  const m = t.market;
  const idx = (tk: string) => m.indexes.find((x: Row) => x.ticker === tk);
  const np = idx("^CNXPHARMA"), n50 = idx("^NSEI");
  const byDay: [string, Row[]][] = [];
  for (const r of t.results_week) {
    const last = byDay[byDay.length - 1];
    last && last[0] === r.meeting_date ? last[1].push(r) : byDay.push([r.meeting_date, [r]]);
  }
  const watchedSignals = t.signals.filter((s: Row) => s.watched).length;

  return (
    <div className="stack">
      <div className="kpis">
        <Kpi label="Nifty Pharma" value={price(np?.price)} sub={<span className={np?.change_pct >= 0 ? "pos" : "neg"}>{signed(np?.change_pct)}</span>} tone="amber" />
        <Kpi label="Nifty 50" value={price(n50?.price)} sub={<span className={n50?.change_pct >= 0 ? "pos" : "neg"}>{signed(n50?.change_pct)}</span>} />
        <Kpi label="Pharma breadth" value={`${m.breadth[0]} ▲ / ${m.breadth[1]} ▼`} sub={`quotes ${ago(m.asof)} old`} />
        <Kpi label="Reporting this week" value={t.results_week.length} sub={`${t.results_week.filter((r: Row) => r.watched).length} on your watchlist`} />
        <Kpi label="Signals (7d)" value={t.signals.length} sub={`${watchedSignals} about names you watch`} tone={watchedSignals ? "amber" : undefined} />
      </div>

      <div className="grid cols-3">
        <Panel title="Your watchlist" sub="star (☆) any company to follow it here, in Specs and in Telegram alerts" className="span-2"
          right={<Link to="/companies">screen companies ›</Link>}>
          {!t.signed_in ? <Empty>Open the terminal through Tailscale to keep a watchlist.</Empty>
            : !t.watch.length ? <Empty>Nothing watched yet. Star companies on the <Link to="/companies">Companies</Link> screen, or send <b>/watch cipla</b> to Specs.</Empty>
            : (
              <table className="tt">
                <thead><tr><th /><th>Name</th><th className="num">Last</th><th className="num">Chg</th><th>Qtr</th><th className="num">Rev YoY</th>
                  <th className="num">Profit YoY</th><th>Flags</th><th>Results</th><th>Latest</th></tr></thead>
                <tbody>{t.watch.map((w: Row) => (
                  <tr key={w.key} onClick={() => w.href && nav(w.href)}>
                    <td><Star k={w.key} label={w.label} href={w.href} /></td>
                    <td>{w.label}{w.ticker && <span className="faint"> {w.ticker}</span>}</td>
                    <td className="num">{price(w.price)}</td>
                    <td className={`num ${w.change_pct >= 0 ? "pos" : "neg"}`}>{w.change_pct == null ? "" : signed(w.change_pct)}</td>
                    <td className="mut">{w.quarter ?? ""}</td>
                    <td className="num">{w.ticker ? yoy(w.rev_yoy) : ""}</td>
                    <td className="num">{w.ticker ? yoy(w.profit_yoy) : ""}</td>
                    <td>{w.flags && <Flags f={w.flags} />}</td>
                    <td className="mut">{w.next_results ? day(w.next_results) : ""}</td>
                    <td className="mut" title={w.last_event?.title} style={{ maxWidth: 260, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {w.last_event ? <><span className="faint">{ago(w.last_event.ts)}</span> {w.last_event.title}</> : <span className="faint">—</span>}
                    </td>
                  </tr>
                ))}</tbody>
              </table>
            )}
        </Panel>
        <Panel title="Results this week" sub="board meetings announced to NSE" right={<Link to="/companies?f=week">all ›</Link>}>
          {byDay.length ? byDay.map(([d, rs]) => (
            <div key={d} style={{ marginBottom: 6 }}>
              <div className="faint">{new Date(d).toLocaleDateString("en-IN", { weekday: "short", day: "2-digit", month: "short" })}</div>
              <div className="chips">{rs.map((r) => (
                <Link key={r.slug} to={`/g/${r.slug}`} className={`chip ${r.watched ? "chip-on" : ""}`}>{r.name}</Link>
              ))}</div>
            </div>
          )) : <Empty>no results meetings announced for the next 7 days</Empty>}
        </Panel>
      </div>

      <div className="grid cols-3">
        <Panel title="Signals" sub="last 7 days, ranked: severity, kind, listed names, your watchlist" className="span-2 tall">
          {t.signals.map((e: Row) => (
            <div key={e.id} className={`ev ev-${e.severity}`}>
              <span className="ev-time" title={e.ts}>{ago(e.detected_at)}</span>
              <span className="ev-kind">{String(e.kind).toUpperCase()}</span>
              {e.watched && <span className="badge b-flag">WATCHED</span>}
              {e.group_slug && <Link to={`/g/${e.group_slug}`} className="amb" style={{ whiteSpace: "nowrap" }}>{e.ticker ?? e.group_name}</Link>}
              {e.url ? <a href={e.url} target="_blank" rel="noreferrer" className="ev-title">{e.title}</a> : <span className="ev-title">{e.title}</span>}
              <span className="ev-src">{e.source}</span>
            </div>
          ))}
        </Panel>
        <Panel title="Just reported" sub="consolidated, latest quarter, ₹ cr" className="tall">
          {t.reported.length ? (
            <table className="tt">
              <thead><tr><th>Group</th><th className="num">Revenue</th><th className="num">YoY</th><th className="num">Profit YoY</th><th className="num">Margin</th></tr></thead>
              <tbody>{t.reported.map((r: Row) => (
                <tr key={r.slug} onClick={() => nav(`/g/${r.slug}`)} title={`${r.quarter}, filed ${day(r.filed_at)}`}>
                  <td>{r.name}</td>
                  <td className="num">{r.revenue?.toLocaleString("en-IN", { maximumFractionDigits: 0 })}</td>
                  <td className="num">{yoy(r.rev_yoy)}</td>
                  <td className="num">{(r.net_profit ?? 0) < 0 ? <span className="neg">loss</span> : yoy(r.profit_yoy)}</td>
                  <td className="num">{pct(r.margin)}</td>
                </tr>
              ))}</tbody>
            </table>
          ) : <Empty>no results filed in the last 10 days</Empty>}
        </Panel>
      </div>

      <div className="grid cols-3">
        {(["gainers", "losers"] as const).map((k) => (
          <Panel key={k} title={k === "gainers" ? "Top gainers" : "Top losers"} sub="listed pharma, today">
            <table className="tt"><tbody>{m[k].map((r: Row) => (
              <tr key={r.ticker} onClick={() => r.slug && nav(`/g/${r.slug}`)}>
                <td className="amb">{r.ticker.replace(".NS", "")}</td><td className="mut">{r.group_name ?? r.name}</td>
                <td className="num">{price(r.price)}</td>
                <td className={`num ${r.change_pct >= 0 ? "pos" : "neg"}`}>{signed(r.change_pct)}</td>
              </tr>
            ))}</tbody></table>
          </Panel>
        ))}
        <Panel title="Elsewhere" sub="the rest of the terminal">
          <div className="chips">
            <Link className="chip" to="/market">Market structure</Link><Link className="chip" to="/reg">Regulatory desk</Link>
            <Link className="chip" to="/pipeline">Pipeline</Link><Link className="chip" to="/equities">All quotes</Link>
            <Link className="chip" to="/news">News wire</Link>
          </div>
          <div className="faint" style={{ marginTop: 8 }}>Quotes: NSE via Yahoo, ~15 min delay. Results: NSE integrated filings.</div>
        </Panel>
      </div>
    </div>
  );
}
