import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { day, inr, type Row } from "../lib/api";
import { Panel, Tabs } from "./ui";

// Derived links (Phase 1): high-confidence rows show by default; inferred ones only on request, and labelled.
export function Inferred({ r }: { r: Row }) {
  const why = `${r.method} · confidence ${Number(r.confidence).toFixed(2)}${r.evidence ? `\n${r.evidence}` : ""}`;
  return r.inferred ? <span className="badge b-mute" title={why}>INFERRED</span> : <span className="faint" title={why}>ⓘ</span>;
}

export function useShowInferred() {
  const [on, setOn] = useState(false);
  const toggle = (
    <label className="faint" style={{ cursor: "pointer", whiteSpace: "nowrap" }}>
      <input type="checkbox" checked={on} onChange={(e) => setOn(e.target.checked)} /> show inferred
    </label>
  );
  return { on, toggle, keep: (rows: Row[] | undefined) => (rows ?? []).filter((r) => on || !r.inferred) };
}

type Tab = "brands" | "recalls" | "trials" | "news" | "tenders";

export function MoleculeLinks({ links }: { links: Row | undefined }) {
  const [tab, setTab] = useState<Tab>("brands");
  const { toggle, keep } = useShowInferred();
  if (!links) return null;
  const sets: Record<Tab, Row[]> = {
    brands: keep(links.brand_registry), recalls: keep(links.us_recalls), trials: keep(links.trials),
    news: keep(links.news), tenders: keep(links.tenders),
  };
  const tot = links.brand_registry_total ?? {};
  const body: Record<Tab, ReactNode> = {
    brands: <table className="tt"><thead><tr><th>Brand</th><th>Licensed firm</th><th>Declared generic</th><th>Licence</th><th /></tr></thead><tbody>
      {sets.brands.map((r, i) => <tr key={i}><td>{r.brand_name}</td>
        <td>{r.company_slug ? <Link to={`/co/${r.company_slug}`}>{r.firm_name}</Link> : r.firm_name}</td>
        <td className="mut" title={r.generic_name}>{r.generic_name}</td><td className="faint">{r.license_number}</td><td><Inferred r={r} /></td></tr>)}</tbody></table>,
    recalls: <table className="tt"><tbody>{sets.recalls.map((r, i) => <tr key={i}><td>{day(r.issued_on)}</td><td>{r.firm}</td>
      <td className="mut" title={r.subject}>{r.subject}</td><td><Inferred r={r} /></td></tr>)}</tbody></table>,
    trials: <table className="tt"><tbody>{sets.trials.map((t) => <tr key={t.nct_id}>
      <td><a href={`https://clinicaltrials.gov/study/${t.nct_id}`} target="_blank" rel="noreferrer">{t.nct_id}</a></td>
      <td title={t.title}>{t.title}</td><td className="mut">{t.phase?.replace(/PHASE/g, "P")}</td><td className="mut">{t.status?.toLowerCase().replace(/_/g, " ")}</td><td><Inferred r={t} /></td></tr>)}</tbody></table>,
    news: <>{sets.news.map((n) => <div className="ev" key={n.id}><span className="ev-time">{day(n.published_at)}</span>
      <a className="ev-title" href={n.url} target="_blank" rel="noreferrer">{n.title}</a><span className="ev-src">{n.source}</span> <Inferred r={n} /></div>)}</>,
    tenders: <table className="tt"><tbody>{sets.tenders.map((r, i) => <tr key={i}><td className="mut">{r.buyer}</td><td title={r.item}>{r.item}</td>
      <td>{r.supplier}</td><td className="num amb">{inr(r.rate)}</td><td className="faint">{r.level}</td><td><Inferred r={r} /></td></tr>)}</tbody></table>,
  };
  return (
    <Panel title="Linked records" sub={`resolved from registry, recall, trial, news and tender text${tot.n ? ` · ${tot.high} of ${tot.n} brand registrations high-confidence` : ""} · hover ⓘ for the evidence`}
      right={<div style={{ display: "flex", gap: 10, alignItems: "center" }}>{toggle}
        <Tabs value={tab} onChange={setTab} tabs={[["brands", `brand regs ${sets.brands.length}`], ["recalls", `US recalls ${sets.recalls.length}`],
          ["trials", `trials +${sets.trials.length}`], ["news", `news +${sets.news.length}`], ["tenders", `tenders +${sets.tenders.length}`]]} /></div>}>
      {sets[tab].length ? body[tab] : <div className="empty">nothing linked{tab !== "brands" && tab !== "recalls" ? " beyond what is listed above" : ""}</div>}
    </Panel>
  );
}
