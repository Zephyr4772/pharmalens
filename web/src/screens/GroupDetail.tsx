import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { crore, day, get, num, signed, type Row } from "../lib/api";
import { Dossier } from "../components/Dossier";
import { ErrorBox, Kpi, LineChart, Loading, Panel, Star, Tabs } from "../components/ui";
import { Outcome } from "./Pipeline";
import { Debarments, Filings, Licences, Tenders, UsPortfolio } from "../components/Depth";

export default function GroupDetail() {
  const { slug } = useParams();
  const g = useQuery({ queryKey: ["parent", slug], queryFn: () => get(`/parents/${slug}`), refetchInterval: 300_000 });
  if (g.isLoading) return <Loading />;
  if (g.error) return <ErrorBox e={g.error} />;
  const d = g.data;
  const skus = d.subsidiaries.reduce((a: number, s: Row) => a + (s.product_count ?? 0), 0);
  return (
    <div className="stack">
      <div className="detail-head">
        <Star k={`g:${d.slug}`} label={d.name} href={`/g/${d.slug}`} />
        <span className="detail-title">{d.name}</span>
        {d.ticker && <span className="badge b-flag">NSE: {d.ticker}</span>}
        <span className="muted">{d.hq}</span>
        <span className="faint">{d.ownership?.replace("_", " ")}</span>
        {d.notes && <span className={`badge ${/amalgamated|delisted/i.test(d.notes) ? "b-warn" : "b-mute"}`} title={d.notes}>{d.notes.split(" (")[0]}</span>}
        {d.price != null && <span className="price-big">₹{d.price.toLocaleString("en-IN", { maximumFractionDigits: 2 })}</span>}
        {d.change_pct != null && <span className={d.change_pct >= 0 ? "pos" : "neg"}>{signed(d.change_pct)}</span>}
      </div>
      <div className="kpis">
        <Kpi label="SKUs (India retail)" value={num(skus)} />
        <Kpi label="Legal entities" value={num(d.subsidiaries.length)} />
        <Kpi label="Market cap" value={d.market_cap ? crore(d.market_cap) : "—"} />
        <Kpi label="52w range" value={d.week52_low ? `${d.week52_low.toFixed(0)} – ${d.week52_high.toFixed(0)}` : "—"} />
        <Kpi label="NSQ listings" value={num(d.nsq.length)} tone={d.nsq.length ? "down" : undefined} />
        <Kpi label="USFDA actions" value={num(d.usfda.length)} tone={d.usfda.length ? "down" : undefined} />
        <Kpi label="US FDA applications" value={num(d.us_portfolio?.applications)} sub={d.us_portfolio?.andas ? `${num(d.us_portfolio.andas)} ANDA` : undefined} />
        <Kpi label="State tenders" value={num(d.tenders?.length)} sub={d.tenders?.length ? `${num(d.tenders.filter((t: Row) => t.level === "L1").length)} as L1` : undefined} />
      </div>
      {d.history?.length > 1 && <PriceHistory rows={d.history} />}
      <div className="grid cols-3">
        <Panel title="Entities in group">
          <table className="tt"><tbody>{d.subsidiaries.map((s: Row) => (
            <tr key={s.id}><td><Link to={`/co/${s.slug}`}>{s.name}</Link></td><td className="num">{num(s.product_count)}</td><td className="num mut">{num(s.molecule_count)} mol</td></tr>
          ))}</tbody></table>
        </Panel>
        <Panel title="USFDA actions" sub="recalls, import alerts (66-40 cGMP) and warning letters">
          {d.usfda.length ? d.usfda.map((u: Row, i: number) => <div className="ev" key={i}><span className="ev-time">{day(u.issued_on)}</span><span className="ev-title" title={u.subject}>{u.subject}</span></div>) : <div className="empty">none on record</div>}
        </Panel>
        <Panel title="News">
          {d.news.length ? d.news.map((n: Row) => <div className="ev" key={n.id}><span className="ev-time">{day(n.published_at)}</span><span className={`ev-kind topic-${n.topic}`}>{n.topic}</span><a className="ev-title" href={n.url} target="_blank" rel="noreferrer">{n.title}</a></div>) : <div className="empty">no recent coverage</div>}
        </Panel>
      </div>
      <div className="grid cols-2">
        <Panel title="Regulatory pipeline — SEC" sub="this group's agenda items at CDSCO expert committees">
          {d.sec.length ? <table className="tt"><tbody>{d.sec.map((x: Row, i: number) => (
            <tr key={i}><td>{day(x.meeting_date)}</td><td className="mut">{String(x.committee).replace("SEC ", "")}</td><td title={x.drug_text}>{x.drug_text}</td><td><Outcome o={x.outcome} /></td>
              <td><a href={x.source_url} target="_blank" rel="noreferrer">pdf</a></td></tr>
          ))}</tbody></table> : <div className="empty">no SEC items matched to this group</div>}
        </Panel>
        <Panel title="Clinical trials in India" sub="sponsored by this group">
          {d.trials.length ? <table className="tt"><tbody>{d.trials.map((t: Row) => (
            <tr key={t.nct_id}><td><a href={`https://clinicaltrials.gov/study/${t.nct_id}`} target="_blank" rel="noreferrer">{t.nct_id}</a></td>
              <td title={t.title}>{t.title}</td><td className="mut">{t.phase?.replace(/PHASE/g, "P")}</td><td className="mut">{t.status?.toLowerCase().replace(/_/g, " ")}</td></tr>
          ))}</tbody></table> : <div className="empty">no trials on record</div>}
        </Panel>
      </div>
      <div className="grid cols-2">
        <Filings rows={d.filings} />
        <UsPortfolio p={d.us_portfolio} recent={d.us_recent} ndc={d.us_ndc_count} pq={d.who_pq} />
      </div>
      <div className="grid cols-2">
        <Tenders rows={d.tenders} />
        <Licences rows={d.licences} />
      </div>
      <Debarments rows={d.debarments} />
      <Dossier d={d} />
    </div>
  );
}

const RANGES: [string, string, number][] = [["1y", "1Y", 365], ["5y", "5Y", 365 * 5], ["10y", "10Y", 365 * 10], ["max", "Max", 0]];

function PriceHistory({ rows }: { rows: Row[] }) {
  const [range, setRange] = useState("1y");
  const data = useMemo(() => {
    const days = RANGES.find((r) => r[0] === range)![2];
    const cut = days ? new Date(Date.now() - days * 864e5).toISOString().slice(0, 10) : "";
    const sel = cut ? rows.filter((r) => r.d >= cut) : rows;
    // keep the chart light: at most ~800 points (weekly sampling for long ranges)
    const step = Math.max(1, Math.ceil(sel.length / 800));
    return sel.filter((_, i) => i % step === 0 || i === sel.length - 1);
  }, [rows, range]);
  const first = data[0]?.close, last = data[data.length - 1]?.close;
  const chg = first && last ? ((last / first - 1) * 100).toFixed(0) : null;
  return (
    <Panel title="Share price" sub={`daily close (NSE) · since ${rows[0].d}${chg ? ` · ${Number(chg) >= 0 ? "+" : ""}${chg}% over range` : ""}`}
      right={<Tabs value={range} onChange={setRange} tabs={RANGES.map(([k, l]) => [k, l] as [string, string])} />}>
      <LineChart data={data} x="d" y="close" fmt={(v) => `₹${v.toFixed(0)}`} />
    </Panel>
  );
}
