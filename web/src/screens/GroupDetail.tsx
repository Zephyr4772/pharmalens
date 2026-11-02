import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { crore, day, get, num, pct, signed, type Row } from "../lib/api";
import { Dossier } from "../components/Dossier";
import { Empty, ErrorBox, EventRow, Kpi, LineChart, Loading, Panel, Star, Tabs } from "../components/ui";
import { Outcome } from "./Pipeline";
import { Flags } from "./Companies";
import { Debarments, Filings, Licences, Tenders, UsPortfolio } from "../components/Depth";

type Tab = "overview" | "fin" | "risk" | "pipe" | "port";
const yoy = (n: number | null | undefined) => <span className={n == null ? "faint" : n >= 0 ? "pos" : "neg"}>{signed(n, 0)}</span>;
const cr = (n: number | null | undefined) => (n == null ? "—" : n.toLocaleString("en-IN", { maximumFractionDigits: 0 }));

// The company dossier, organised the way an analyst reads a company: overview, financials, risk, pipeline, business.
export default function GroupDetail() {
  const { slug } = useParams();
  const [sp, setSp] = useSearchParams();
  const g = useQuery({ queryKey: ["parent", slug], queryFn: () => get(`/parents/${slug}`), refetchInterval: 300_000 });
  const x = useQuery({ queryKey: ["dossier", slug], queryFn: () => get(`/invest/dossier/${slug}`), refetchInterval: 300_000 });
  if (g.isLoading) return <Loading />;
  if (g.error) return <ErrorBox e={g.error} />;
  const d = g.data;
  const v: Row = x.data ?? {};
  const listed = !!d.ticker;
  const tab = (sp.get("tab") as Tab) || "overview";
  const reds = (v.scorecard ?? []).filter((s: Row) => s.level === "red").length;
  const tabs: [Tab, string][] = [["overview", "Overview"], ...(listed ? [["fin", "Financials"] as [Tab, string]] : []),
    ["risk", reds ? `Risk (${reds})` : "Risk"], ["pipe", "Pipeline"], ["port", "Portfolio & business"]];
  const m = v.metrics ?? {};
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
        {m.flags && <Flags f={m.flags} />}
      </div>
      <Tabs tabs={tabs} value={tabs.some((t) => t[0] === tab) ? tab : "overview"} onChange={(t) => setSp(t === "overview" ? {} : { tab: t }, { replace: true })} />
      {tab === "fin" && listed ? <Financials v={v} loading={x.isLoading} />
        : tab === "risk" ? <Risk d={d} v={v} />
        : tab === "pipe" ? <Pipe d={d} v={v} />
        : tab === "port" ? <Business d={d} />
        : <Overview d={d} v={v} />}
    </div>
  );
}

function Overview({ d, v }: { d: Row; v: Row }) {
  const m = v.metrics ?? {};
  const skus = d.subsidiaries.reduce((a: number, s: Row) => a + (s.product_count ?? 0), 0);
  return (
    <>
      <div className="kpis">
        <Kpi label="Market cap" value={d.market_cap ? crore(d.market_cap) : "—"} tone="amber" />
        <Kpi label="P/E (trailing)" value={m.pe ? m.pe.toFixed(1) : "—"} sub={m.eps_ttm ? `EPS ₹${m.eps_ttm.toFixed(1)} (4 qtrs)` : undefined} />
        <Kpi label="1Y return" value={signed(m.chg_1y, 0)} tone={m.chg_1y == null ? undefined : m.chg_1y >= 0 ? "up" : "down"}
          sub={d.week52_low ? `52w ₹${d.week52_low.toFixed(0)}–${d.week52_high.toFixed(0)}` : undefined} />
        <Kpi label={`Revenue YoY${m.quarter ? ` · ${m.quarter}` : ""}`} value={signed(m.rev_yoy, 0)} sub={m.profit_yoy != null ? `profit ${signed(m.profit_yoy, 0)}` : undefined} />
        <Kpi label="Net margin" value={pct(m.margin)} />
        <Kpi label="Next results" value={m.next_results ? day(m.next_results) : "—"} />
        <Kpi label="SKUs (India retail)" value={num(skus)} sub={`${num(d.subsidiaries.length)} legal entities`} />
      </div>
      {d.history?.length > 1 && <PriceHistory rows={d.history} />}
      <div className="grid cols-3">
        <Panel title="Timeline" sub="everything the feeds caught about this group" className="span-2 tall">
          {v.timeline?.length ? v.timeline.map((e: Row) => <EventRow key={e.id} e={e} />) : <Empty>no events yet</Empty>}
        </Panel>
        <Panel title="News" className="tall">
          {d.news.length ? d.news.map((n: Row) => <div className="ev" key={n.id}><span className="ev-time">{day(n.published_at)}</span><span className={`ev-kind topic-${n.topic}`}>{n.topic}</span><a className="ev-title" href={n.url} target="_blank" rel="noreferrer">{n.title}</a></div>) : <div className="empty">no recent coverage</div>}
        </Panel>
      </div>
    </>
  );
}

const PEER_LABEL: Record<string, [string, (n: number) => string]> = {
  rev_yoy: ["Revenue growth YoY", (n) => signed(n, 0)], profit_yoy: ["Profit growth YoY", (n) => signed(n, 0)],
  margin: ["Net margin", (n) => pct(n)], pe: ["P/E (cheapest = #1)", (n) => n.toFixed(1)],
  chg_1y: ["1Y share return", (n) => signed(n, 0)], market_cap: ["Market cap", (n) => crore(n)],
};

function Financials({ v, loading }: { v: Row; loading: boolean }) {
  if (loading) return <Loading what="loading financials" />;
  const q: Row[] = v.quarters ?? [];
  if (!q.length) return <Empty>No results filed in NSE's integrated format yet.</Empty>;
  const lastCal = (v.calendar ?? []).find((c: Row) => new Date(c.meeting_date) >= new Date(new Date().toDateString()));
  return (
    <>
      <div className="grid cols-3">
        <Panel title="Revenue and margins" sub="consolidated, ₹ crore · bars: revenue · lines: EBITDA and net margin" className="span-2">
          <FinChart rows={[...q].reverse()} />
        </Panel>
        <Panel title="Against listed peers" sub={`rank among listed Indian pharma groups`}>
          <table className="tt"><tbody>{(v.peers ?? []).map((p: Row) => {
            const [label, f] = PEER_LABEL[p.field];
            const top = p.rank <= Math.ceil(p.of / 4), bottom = p.rank > p.of - Math.ceil(p.of / 4);
            return (
              <tr key={p.field}><td>{label}</td><td className="num amb">{f(p.value)}</td>
                <td className={`num ${top ? "pos" : bottom ? "neg" : ""}`}>#{p.rank}<span className="faint"> / {p.of}</span></td>
                <td className="num faint">median {f(p.median)}</td></tr>
            );
          })}</tbody></table>
          {lastCal && <div style={{ marginTop: 8 }}>Next board meeting: <span className="amb">{day(lastCal.meeting_date)}</span> <span className="faint">{lastCal.purpose}</span></div>}
        </Panel>
      </div>
      <Panel title="Quarterly results" sub="consolidated, ₹ crore · YoY against the same quarter a year earlier · EBITDA = PBT + interest + depreciation − other income">
        <div style={{ overflowX: "auto" }}>
          <table className="tt">
            <thead><tr><th>Quarter</th><th className="num">Revenue</th><th className="num">YoY</th><th className="num">EBITDA</th><th className="num">EBITDA %</th>
              <th className="num">Net profit</th><th className="num">YoY</th><th className="num">Net %</th><th className="num">EPS ₹</th><th className="num">EPS YoY</th>
              <th className="num">Employee cost</th><th className="num">Finance cost</th><th>Filed</th><th /></tr></thead>
            <tbody>{q.map((r) => (
              <tr key={r.period_end}>
                <td className="amb">{r.label}</td><td className="num">{cr(r.revenue)}</td><td className="num">{yoy(r.revenue_yoy)}</td>
                <td className="num">{cr(r.ebitda)}</td><td className="num mut">{pct(r.ebitda_margin)}</td>
                <td className={`num ${(r.net_profit ?? 0) < 0 ? "neg" : ""}`}>{cr(r.net_profit)}</td><td className="num">{yoy(r.net_profit_yoy)}</td>
                <td className="num mut">{pct(r.margin)}</td><td className="num">{r.eps?.toFixed(2) ?? "—"}</td><td className="num">{yoy(r.eps_yoy)}</td>
                <td className="num mut">{cr(r.employee_cost)}</td><td className="num mut">{cr(r.finance_costs)}</td>
                <td className="faint">{day(r.filed_at)}</td><td>{r.source_url && <a href={r.source_url} target="_blank" rel="noreferrer">filing</a>}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      </Panel>
      {v.annual?.length > 0 && (
        <Panel title="Annual" sub="consolidated, ₹ crore, financial years (April–March)">
          <table className="tt">
            <thead><tr><th>Year</th><th className="num">Revenue</th><th className="num">YoY</th><th className="num">EBITDA %</th><th className="num">Net profit</th>
              <th className="num">YoY</th><th className="num">Net %</th><th className="num">EPS ₹</th></tr></thead>
            <tbody>{v.annual.map((r: Row) => (
              <tr key={r.period_end}><td className="amb">{r.label}</td><td className="num">{cr(r.revenue)}</td><td className="num">{yoy(r.revenue_yoy)}</td>
                <td className="num mut">{pct(r.ebitda_margin)}</td><td className="num">{cr(r.net_profit)}</td><td className="num">{yoy(r.net_profit_yoy)}</td>
                <td className="num mut">{pct(r.margin)}</td><td className="num">{r.eps?.toFixed(2) ?? "—"}</td></tr>
            ))}</tbody>
          </table>
        </Panel>
      )}
    </>
  );
}

// Revenue bars with EBITDA and net margin lines (right axis, %).
function FinChart({ rows }: { rows: Row[] }) {
  const W = 760, H = 220, L = 52, R = 40, T = 10, B = 24;
  const maxRev = Math.max(...rows.map((r) => r.revenue ?? 0), 1);
  const ms = rows.flatMap((r) => [r.margin, r.ebitda_margin]).filter((x) => x != null) as number[];
  const mMin = Math.min(0, ...ms), mMax = Math.max(10, ...ms);
  const bw = (W - L - R) / rows.length;
  const y = (v: number) => T + (H - T - B) * (1 - v / maxRev);
  const ym = (v: number) => T + (H - T - B) * (1 - (v - mMin) / (mMax - mMin));
  const cx = (i: number) => L + bw * i + bw / 2;
  const line = (k: string) => rows.map((r, i) => (r[k] == null ? null : `${cx(i)},${ym(r[k])}`)).filter(Boolean).join(" ");
  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: "auto" }}>
      {[0, 0.5, 1].map((f) => <g key={f}>
        <line x1={L} x2={W - R} y1={y(maxRev * f)} y2={y(maxRev * f)} stroke="var(--line-2)" strokeDasharray="2 3" />
        <text x={L - 6} y={y(maxRev * f) + 3} fontSize="10" textAnchor="end" fill="var(--faint)">{cr(maxRev * f)}</text>
      </g>)}
      {rows.map((r, i) => <g key={r.period_end}>
        <rect x={cx(i) - bw * 0.32} width={bw * 0.64} y={y(r.revenue ?? 0)} height={H - B - y(r.revenue ?? 0)} fill="var(--amber)" opacity={0.75}>
          <title>{`${r.label}: revenue ₹${cr(r.revenue)} cr, net margin ${pct(r.margin)}, EBITDA margin ${pct(r.ebitda_margin)}`}</title>
        </rect>
        <text x={cx(i)} y={H - 8} fontSize="10" textAnchor="middle" fill="var(--faint)">{r.label.replace(" FY", "·")}</text>
      </g>)}
      <polyline points={line("ebitda_margin")} fill="none" stroke="var(--info)" strokeWidth={1.8} />
      <polyline points={line("margin")} fill="none" stroke="var(--up)" strokeWidth={1.8} />
      {[mMin, mMax].map((v) => <text key={v} x={W - R + 6} y={ym(v) + 3} fontSize="10" fill="var(--faint)">{v.toFixed(0)}%</text>)}
      <text x={W - R - 4} y={T + 10} fontSize="10" textAnchor="end" fill="var(--info)">EBITDA %</text>
      <text x={W - R - 4} y={T + 22} fontSize="10" textAnchor="end" fill="var(--up)">net %</text>
    </svg>
  );
}

const LEVEL: Record<string, [string, string]> = { red: ["b-down", "RED"], amber: ["b-warn", "WATCH"], green: ["b-up", "OK"], info: ["b-mute", "INFO"] };
const TOPIC: Record<string, string> = { regulatory_action: "ORDER", litigation: "LEGAL", mgmt_exit: "EXIT", credit: "CREDIT", usfda: "USFDA", plant: "PLANT" };

function Risk({ d, v }: { d: Row; v: Row }) {
  const nq: Row[] = v.nsq_quarterly ?? [];
  const max = Math.max(1, ...nq.map((r) => r.n));
  return (
    <>
      <div className="grid cols-3">
        <Panel title="Sanity check" sub="public records only: no flag is not a clean bill of health" className="span-2">
          {v.scorecard ? (
            <table className="tt"><tbody>{v.scorecard.map((s: Row) => (
              <tr key={s.area}><td style={{ width: 60 }}><span className={`badge ${LEVEL[s.level][0]}`}>{LEVEL[s.level][1]}</span></td><td>{s.area}</td><td className="mut">{s.text}</td></tr>
            ))}</tbody></table>
          ) : <Loading />}
        </Panel>
        <Panel title="Failed-quality batches" sub="CDSCO / state NSQ listings per quarter, 3 years">
          {nq.length ? (
            <div style={{ display: "flex", alignItems: "flex-end", gap: 3, height: 120 }}>
              {nq.map((r) => (
                <div key={r.q} title={`${r.q}: ${r.n} listings${r.spurious ? `, ${r.spurious} spurious` : ""}`} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center" }}>
                  <span className="faint" style={{ fontSize: 9 }}>{r.n}</span>
                  <div style={{ width: "100%", height: (r.n / max) * 90, background: r.spurious ? "var(--down)" : "var(--warn)" }} />
                  <span className="faint" style={{ fontSize: 9 }}>{r.q.slice(2, 4)}Q{Math.floor((Number(r.q.slice(5)) - 1) / 3) + 1}</span>
                </div>
              ))}
            </div>
          ) : <Empty>no NSQ listings in 3 years</Empty>}
        </Panel>
      </div>
      <div className="grid cols-2">
        <Panel title="Disclosures to NSE" sub="orders, litigation, senior exits, credit ratings, USFDA and plant events · 2 years" className="tall">
          {v.disclosures?.length ? v.disclosures.map((x: Row, i: number) => (
            <div className="ev" key={i}><span className="ev-time">{day(x.announced_at)}</span>
              <span className={`badge ${["regulatory_action", "mgmt_exit"].includes(x.topic) ? "b-down" : "b-warn"}`}>{TOPIC[x.topic] ?? x.topic}</span>
              {x.attachment ? <a className="ev-title" href={x.attachment} target="_blank" rel="noreferrer" title={x.text}>{x.text}</a> : <span className="ev-title" title={x.text}>{x.text}</span>}
            </div>
          )) : <Empty>{d.ticker ? "no such disclosures in 2 years" : "unlisted: no exchange disclosures"}</Empty>}
        </Panel>
        <Panel title="US FDA actions" sub="recalls, import alerts (66-40 cGMP) and warning letters" className="tall">
          {d.usfda.length ? d.usfda.map((u: Row, i: number) => <div className="ev" key={i}><span className="ev-time">{day(u.issued_on)}</span><span className="ev-title" title={u.subject}>{u.subject}</span></div>) : <div className="empty">none on record</div>}
        </Panel>
      </div>
      <Dossier d={d} part="quality" />
      <Debarments rows={d.debarments} />
    </>
  );
}

function Pipe({ d, v }: { d: Row; v: Row }) {
  return (
    <>
      <div className="grid cols-2">
        <Panel title="Approvals, launches, trials" sub="events from CDSCO, SEC, ClinicalTrials.gov, US FDA" className="tall">
          {v.approvals?.length ? v.approvals.map((e: Row, i: number) => <EventRow key={i} e={e} />) : <Empty>none yet</Empty>}
        </Panel>
        <UsPortfolio p={d.us_portfolio} recent={d.us_recent} ndc={d.us_ndc_count} pq={d.who_pq} />
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
      <Filings rows={d.filings} />
    </>
  );
}

function Business({ d }: { d: Row }) {
  return (
    <>
      <div className="grid cols-3">
        <Panel title="Entities in group">
          <table className="tt"><tbody>{d.subsidiaries.map((s: Row) => (
            <tr key={s.id}><td><Link to={`/co/${s.slug}`}>{s.name}</Link></td><td className="num">{num(s.product_count)}</td><td className="num mut">{num(s.molecule_count)} mol</td></tr>
          ))}</tbody></table>
        </Panel>
        <div className="span-2"><Tenders rows={d.tenders} /></div>
      </div>
      <Dossier d={d} part="portfolio" />
      <Licences rows={d.licences} />
    </>
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
