import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { csvUrl, day, get, num, type Row } from "../lib/api";
import { Bar, ErrorBox, Kpi, Loading, Pager, Panel, Tabs, Csv } from "../components/ui";

type Tab = "sec" | "approvals" | "trials" | "brands";

const OUTCOME_CLASS: Record<string, string> = { recommended: "b-up", not_recommended: "b-down", deferred: "b-warn", noted: "b-mute" };
const DIV_LABEL: Record<string, string> = {
  new_drug: "MARKETING", clinical_trial: "TRIAL", fdc: "FDC", be: "BE", biological: "BIOLOGICAL", import: "IMPORT",
  medical_device: "DEVICE", other: "OTHER",
};

export function Outcome({ o }: { o: string }) {
  return <span className={`badge ${OUTCOME_CLASS[o] ?? "b-mute"}`}>{o.replace("_", " ")}</span>;
}

export default function Pipeline() {
  const [sp, setSp] = useSearchParams();
  const tab = (sp.get("tab") as Tab) || "sec";
  const s = useQuery({ queryKey: ["pipeline-summary"], queryFn: () => get("/pipeline/summary"), refetchInterval: 600_000 });
  if (s.isLoading) return <Loading />;
  if (s.error) return <ErrorBox e={s.error} />;
  const k = s.data.kpis;
  const maxY = Math.max(...s.data.approvals_by_year.map((r: Row) => r.n), 1);
  const maxS = Math.max(...s.data.sponsors.map((r: Row) => r.n), 1);
  const maxF = Math.max(...s.data.sec_firms.map((r: Row) => r.n), 1);
  return (
    <div className="stack">
      <div className="kpis">
        <Kpi label="SEC agenda items" value={num(k.sec_items)} sub={`latest meeting ${day(k.last_sec)}`} />
        <Kpi label="SEC recommended (90d)" value={num(k.sec_recommended_90d)} tone="up" />
        <Kpi label="Marketing permissions (12m)" value={num(k.marketing_12m)} sub="SEC new-drug recommendations" tone="amber" />
        <Kpi label="CDSCO new drug approvals" value={num(k.approvals)} sub={`since 2015 · last ${day(k.last_approval)}`} />
        <Kpi label="Trials with Indian sites" value={num(k.trials)} sub={`${num(k.trials_recruiting)} recruiting`} />
        <Kpi label="NLEM 2022" value={num(k.nlem_medicines)} sub="essential medicines" />
      </div>
      <div className="grid cols-3">
        <Panel title="New drug approvals by year" sub="CDSCO New Drugs Division">
          <div className="hist">
            {s.data.approvals_by_year.map((r: Row) => (
              <div className="hist-col" key={r.y} onClick={() => setSp({ tab: "approvals", year: String(r.y) })} style={{ cursor: "pointer" }}>
                <span className="hist-y">{r.n}</span>
                <div className="hist-bar" style={{ height: `${(r.n / maxY) * 100}px` }} />
                <span className="hist-x">{String(r.y).slice(2)}</span>
              </div>
            ))}
          </div>
        </Panel>
        <Panel title="Most active at SEC" sub="agenda items, last 12 months">
          {s.data.sec_firms.map((f: Row) => <Bar key={f.firm} label={f.firm} to={f.slug ? `/g/${f.slug}` : undefined} value={f.n} max={maxF} text={`${f.n} · ${f.rec} rec`} />)}
        </Panel>
        <Panel title="Trial sponsors in India" sub="interventional, updated in last 3 years">
          {s.data.sponsors.map((f: Row) => <Bar key={f.sponsor} label={f.sponsor} to={f.slug ? `/g/${f.slug}` : undefined} value={f.n} max={maxS} text={`${f.n} · ${f.active} active`} tone="cyan" />)}
        </Panel>
      </div>
      <Tabs<Tab> value={tab} onChange={(t) => setSp({ tab: t })} tabs={[
        ["sec", "SEC RECOMMENDATIONS"], ["approvals", "CDSCO NEW DRUG APPROVALS"], ["trials", "CLINICAL TRIALS (INDIA)"], ["brands", "NEW BRAND REGISTRATIONS"],
      ]} />
      {tab === "sec" && <SecTab committees={s.data.committees} />}
      {tab === "approvals" && <ApprovalsTab year={sp.get("year") ?? ""} />}
      {tab === "trials" && <TrialsTab />}
      {tab === "brands" && <BrandsTab />}
    </div>
  );
}

function SecTab({ committees }: { committees: Row[] }) {
  const [q, setQ] = useState("");
  const [division, setDivision] = useState("");
  const [outcome, setOutcome] = useState("");
  const [committee, setCommittee] = useState("");
  const [open, setOpen] = useState<number | null>(null);
  const [page, setPage] = useState(1);
  const params = { q, division, outcome, committee, page, limit: 60 };
  const r = useQuery({ queryKey: ["sec", params], queryFn: () => get("/pipeline/sec", params) });
  const reset = () => setPage(1);
  return (
    <Panel title="Subject Expert Committee recommendations" sub="every agenda item: who asked CDSCO for what, and what the committee said"
      right={<Csv href={csvUrl("/pipeline/sec", { q, division, outcome, committee })} />}>
      <div className="filterbar inline">
        <input placeholder="drug or firm" value={q} onChange={(e) => { setQ(e.target.value); reset(); }} />
        <select value={division} onChange={(e) => { setDivision(e.target.value); reset(); }}>
          <option value="">all types</option>{Object.entries(DIV_LABEL).map(([k, v]) => <option key={k} value={k}>{v.toLowerCase()}</option>)}
        </select>
        <select value={outcome} onChange={(e) => { setOutcome(e.target.value); reset(); }}>
          <option value="">all outcomes</option><option value="recommended">recommended</option><option value="deferred">deferred / more data</option>
          <option value="not_recommended">not recommended</option><option value="noted">noted</option>
        </select>
        <select value={committee} onChange={(e) => { setCommittee(e.target.value); reset(); }}>
          <option value="">all committees</option>{committees.map((c) => <option key={c.committee} value={c.committee}>{c.committee} ({c.n})</option>)}
        </select>
      </div>
      {r.isLoading ? <Loading /> : (
        <table className="tt">
          <thead><tr><th>Meeting</th><th>Committee</th><th>Type</th><th>Drug</th><th>Firm</th><th>Outcome</th><th /></tr></thead>
          <tbody>
            {r.data?.data.map((x: Row) => (
              <>
                <tr key={x.id} onClick={() => setOpen(open === x.id ? null : x.id)} className={open === x.id ? "sel" : ""}>
                  <td>{day(x.meeting_date)}</td>
                  <td className="mut" title={x.committee}>{String(x.committee).replace("SEC ", "")}</td>
                  <td><span className="chip">{DIV_LABEL[x.division] ?? x.division}</span></td>
                  <td title={x.drug_text} style={{ maxWidth: 380 }}>{x.drug_text}</td>
                  <td title={x.firm}>{x.parent_slug ? <Link to={`/g/${x.parent_slug}`} onClick={(e) => e.stopPropagation()}>{x.firm}</Link> : x.firm}</td>
                  <td><Outcome o={x.outcome} /></td>
                  <td><a href={x.source_url} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}>pdf</a></td>
                </tr>
                {open === x.id && <tr key={x.id + "r"}><td colSpan={7} className="prose" style={{ whiteSpace: "normal" }}>{x.file_no && <b>{x.file_no} · </b>}{x.recommendation}</td></tr>}
              </>
            ))}
          </tbody>
        </table>
      )}
      <Pager meta={r.data?.meta} page={page} setPage={setPage} />
    </Panel>
  );
}

function ApprovalsTab({ year }: { year: string }) {
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const params = { q, year, page, limit: 60 };
  const r = useQuery({ queryKey: ["approvals", params], queryFn: () => get("/pipeline/approvals", params) });
  return (
    <Panel title="New drugs approved by CDSCO" sub={year ? `year ${year}` : "all years since 2015"} right={<Csv href={csvUrl("/pipeline/approvals", { q, year })} />}>
      <div className="filterbar inline"><input placeholder="drug or indication" value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} /></div>
      {r.isLoading ? <Loading /> : (
        <table className="tt">
          <thead><tr><th>Approved</th><th>Drug</th><th>Indication</th><th /></tr></thead>
          <tbody>{r.data?.data.map((a: Row) => (
            <tr key={a.id}>
              <td>{day(a.approved_on)}</td>
              <td title={a.drug_text} style={{ maxWidth: 420, whiteSpace: "normal" }}>{a.drug_text}</td>
              <td className="mut" title={a.indication} style={{ maxWidth: 560 }}>{a.indication}</td>
              <td><a href={a.source_url} target="_blank" rel="noreferrer">pdf</a></td>
            </tr>
          ))}</tbody>
        </table>
      )}
      <Pager meta={r.data?.meta} page={page} setPage={setPage} />
    </Panel>
  );
}

const SOURCE_LABEL: Record<string, string> = { cdsco_84ab: "CDSCO 84AB", cdci: "CDCI" };

function BrandsTab() {
  const [q, setQ] = useState("");
  const [source, setSource] = useState("");
  const [days, setDays] = useState(90);
  const [page, setPage] = useState(1);
  const r = useQuery({ queryKey: ["new-brands", q, source, days, page], queryFn: () => get("/pipeline/new-brands", { q, source, days, page, limit: 80 }) });
  const since = r.data?.tracking?.find((t: Row) => t.source === "cdsco_84ab")?.since;
  return (
    <Panel title="New brand registrations" sub={`brands that newly appear in the CDSCO Rule 84AB registry (checked weekly${since ? `, tracked since ${day(since)}` : ""}) and in CDCI, the national drug terminology — registrations, not proof of launch; export brands appear too`}
      right={<Csv href={csvUrl("/pipeline/new-brands", { q, source, days })} />}>
      <div className="filterbar inline">
        <input placeholder="brand, company or generic" value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} />
        <select value={source} onChange={(e) => { setSource(e.target.value); setPage(1); }}>
          <option value="">both registries</option><option value="cdsco_84ab">CDSCO 84AB</option><option value="cdci">CDCI</option>
        </select>
        <select value={days} onChange={(e) => { setDays(Number(e.target.value)); setPage(1); }}>
          {[30, 90, 365, 1095].map((d) => <option key={d} value={d}>last {d} days</option>)}
        </select>
      </div>
      <table className="tt">
        <thead><tr><th>First seen</th><th>Registry</th><th>Brand</th><th>Generic / composition</th><th>Company</th><th>Group</th><th>In catalog</th></tr></thead>
        <tbody>{r.data?.data?.map((b: Row, i: number) => (
          <tr key={i}>
            <td className="mut">{day(b.first_seen)}</td><td className="faint">{SOURCE_LABEL[b.source] ?? b.source}</td>
            <td>{b.brand}</td><td className="faint" title={b.generic}>{(b.generic ?? "").slice(0, 80)}</td>
            <td title={b.firm}>{b.company_slug ? <Link to={`/co/${b.company_slug}`}>{b.firm}</Link> : b.firm}</td>
            <td>{b.parent_slug ? <Link to={`/g/${b.parent_slug}`}>{b.parent}</Link> : <span className="faint">—</span>}</td>
            <td>{b.in_catalog ? <span className="badge b-mute">LISTED</span> : <span className="badge b-up">NEW</span>}</td>
          </tr>))}</tbody>
      </table>
      {!r.isLoading && !r.data?.data?.length && <div className="empty">no new registrations in this window</div>}
      <Pager meta={r.data?.meta} page={page} setPage={setPage} />
    </Panel>
  );
}

function TrialsTab() {
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("active");
  const [phase, setPhase] = useState("");
  const [indian, setIndian] = useState(false);
  const [page, setPage] = useState(1);
  const params = { q, status, phase, indian_sponsor: indian || undefined, page, limit: 60 };
  const r = useQuery({ queryKey: ["trials", params], queryFn: () => get("/pipeline/trials", params) });
  return (
    <Panel title="Interventional trials with Indian sites" sub="ClinicalTrials.gov (CTRI is CAPTCHA-gated; CTRI ids shown where cross-registered)"
      right={<Csv href={csvUrl("/pipeline/trials", params)} />}>
      <div className="filterbar inline">
        <input placeholder="drug, condition or sponsor" value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} />
        <select value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }}>
          <option value="active">active / recruiting</option><option value="">any status</option><option value="COMPLETED">completed</option><option value="TERMINATED">terminated</option>
        </select>
        <select value={phase} onChange={(e) => { setPhase(e.target.value); setPage(1); }}>
          <option value="">any phase</option><option value="PHASE1">phase 1</option><option value="PHASE2">phase 2</option><option value="PHASE3">phase 3</option><option value="PHASE4">phase 4</option>
        </select>
        <label><input type="checkbox" checked={indian} onChange={(e) => { setIndian(e.target.checked); setPage(1); }} /> Indian sponsors only</label>
      </div>
      {r.isLoading ? <Loading /> : (
        <table className="tt">
          <thead><tr><th>Trial</th><th>Title</th><th>Sponsor</th><th>Phase</th><th>Status</th><th>Interventions</th><th className="num">IN sites</th><th>Updated</th></tr></thead>
          <tbody>{r.data?.data.map((t: Row) => (
            <tr key={t.nct_id}>
              <td><a href={`https://clinicaltrials.gov/study/${t.nct_id}`} target="_blank" rel="noreferrer">{t.nct_id}</a>{t.ctri_id && <div className="faint">{t.ctri_id}</div>}</td>
              <td title={t.title} style={{ maxWidth: 360 }}>{t.title}</td>
              <td>{t.parent_slug ? <Link to={`/g/${t.parent_slug}`}>{t.sponsor}</Link> : t.sponsor}</td>
              <td className="mut">{t.phase?.replace(/PHASE/g, "P")}</td>
              <td className="mut">{t.status?.toLowerCase().replace(/_/g, " ")}</td>
              <td className="mut" title={t.interventions} style={{ maxWidth: 260 }}>{t.interventions}</td>
              <td className="num">{num(t.india_sites)}</td>
              <td>{day(t.last_update)}</td>
            </tr>
          ))}</tbody>
        </table>
      )}
      <Pager meta={r.data?.meta} page={page} setPage={setPage} />
    </Panel>
  );
}
