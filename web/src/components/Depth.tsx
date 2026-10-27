// Depth panels fed by the expansion sources: ChEMBL / openFDA / FAERS pharmacology, state procurement tenders,
// US & WHO & EU registrations, NSE filings, CDSCO brand-name registry.
import { useState } from "react";
import { Link } from "react-router-dom";
import { day, inr, num, type Row } from "../lib/api";
import { Bar, Panel, Tabs } from "./ui";

const LABEL_TITLES: Record<string, string> = {
  boxed_warning: "Boxed warning", indications: "Indications", contraindications: "Contraindications", warnings: "Warnings & precautions",
  adverse_reactions: "Adverse reactions", interactions: "Drug interactions", mechanism: "Mechanism of action",
  pregnancy: "Pregnancy & special populations", overdosage: "Overdosage",
};

export function Pharmacology({ e, compact = false }: { e: Row | null | undefined; compact?: boolean }) {
  const [sec, setSec] = useState<string | null>(null);
  if (!e) return <Panel title="Pharmacology" sub="ChEMBL · US label · FAERS"><div className="empty">not enriched yet — the enrichment feed works through molecules largest-first</div></Panel>;
  const label: Row = e.us_label ?? {};
  const meta: Row = e.us_label_meta ?? {};
  const faers: Row[] = e.faers_top ?? [];
  const max = Math.max(...faers.map((f) => f.count), 1);
  const keys = Object.keys(LABEL_TITLES).filter((k) => label[k]);
  const open = sec ?? keys[0];
  return (
    <div className={compact ? "stack" : "grid cols-3"}>
      <Panel title="Pharmacology" sub="ChEMBL (EMBL-EBI)"
        right={e.chembl_id && <a href={`https://www.ebi.ac.uk/chembl/compound_report_card/${e.chembl_id}/`} target="_blank" rel="noreferrer">{e.chembl_id} ›</a>}>
        {e.chembl_id ? (
          <div className="stack-sm">
            <div className="chips">
              {(e.atc ?? []).map((a: string) => <span key={a} className="badge b-info" title="WHO ATC code">{a}</span>)}
              {e.max_phase != null && <span className="badge b-mute">phase {e.max_phase}</span>}
              {e.first_approval && <span className="badge b-mute">first approved {e.first_approval}</span>}
              {e.black_box && <span className="badge b-down">BOXED WARNING</span>}
              {e.withdrawn && <span className="badge b-down">WITHDRAWN (somewhere)</span>}
            </div>
            {(e.mechanisms ?? []).length > 0 && <table className="tt"><tbody>{e.mechanisms.map((m: Row, i: number) => (
              <tr key={i}><td>{m.moa}</td><td className="mut">{m.action?.toLowerCase()}</td></tr>))}</tbody></table>}
            {(e.indications ?? []).length > 0 && <div className="chips">{e.indications.slice(0, compact ? 12 : 24).map((i: Row) => (
              <span key={i.term} className={`chip ${i.phase >= 4 ? "chip-on" : ""}`} title={`max phase ${i.phase}`}>{i.term}</span>))}</div>}
          </div>
        ) : <div className="empty">{e.chembl_ambiguous ? "name denotes a class or several compounds — not assigned" : "no ChEMBL match"}</div>}
      </Panel>
      <Panel title="Most-reported adverse reactions"
        sub={`US FAERS · ${e.faers_total ? `${num(e.faers_total)} reports listing a single-ingredient product` : "spontaneous reports"} · reports, not incidence; the drug may be concomitant, not the cause`}>
        {faers.length ? (
          <>
            {faers.slice(0, compact ? 8 : 14).map((f) => (
              <Bar key={f.term} label={<span title={f.prr != null ? `PRR ${f.prr}: reported ${f.prr}× as often as across all FAERS` : ""}>{f.term}</span>}
                value={f.count} max={max} tone={f.signal ? "down" : ""}
                text={`${num(f.count)}${f.prr != null ? ` · PRR ${f.prr}` : ""}${f.signal ? " ▲" : ""}`} />))}
            {(e.faers_co ?? []).length > 0 && (
              <div className="faint" style={{ marginTop: 6 }}>Often co-reported: {e.faers_co.slice(0, 6).map((c: Row) => `${c.drug} ${(c.share * 100).toFixed(0)}%`).join(" · ")}</div>)}
            <div className="faint" style={{ marginTop: 4 }}>▲ signal = PRR ≥ 2 with ≥ 3 reports (Evans screening rule)</div>
          </>
        ) : <div className="empty">no FAERS reports for a single-ingredient US product</div>}
      </Panel>
      <Panel title="US prescribing label" sub={meta.generic ? `${meta.brand ?? meta.generic} · ${meta.manufacturer ?? ""} · ${meta.product_type === "HUMAN OTC DRUG" ? "OTC monograph · " : ""}${meta.effective ? `${meta.effective.slice(0, 4)}-${meta.effective.slice(4, 6)}` : ""}` : "openFDA"}
        right={meta.set_id && <a href={meta.url} target="_blank" rel="noreferrer">DailyMed ›</a>}>
        {keys.length ? (
          <>
            <div className="chips">{keys.map((k) => (
              <button key={k} className={`chip ${k === open ? "chip-on" : ""} ${k === "boxed_warning" ? "neg" : ""}`} onClick={() => setSec(k)}>{LABEL_TITLES[k]}</button>))}</div>
            <div className="label-text">{label[open]}</div>
          </>
        ) : <div className="empty">no single-ingredient US label (not marketed alone in the US, or a supplement)</div>}
      </Panel>
    </div>
  );
}

export function Procurement({ rows, title = "Government procurement rates", sub }: { rows: Row[] | undefined; title?: string; sub?: string }) {
  const list = rows ?? [];
  return (
    <Panel title={title} sub={sub ?? "state medical corporation tenders — what the public system pays (RMSCL Rajasthan, TNMSC Tamil Nadu)"}>
      {list.length ? (
        <table className="tt">
          <thead><tr><th>Buyer</th><th>Item</th><th>Pack</th><th className="num">Rate</th><th>Rank</th><th>Supplier</th><th>Tender</th><th>Valid to</th></tr></thead>
          <tbody>{list.map((r, i) => (
            <tr key={i}>
              <td className="mut">{r.buyer}</td><td title={r.item}>{r.item}</td><td className="mut">{r.unit}</td>
              <td className="num amb">{inr(r.rate)}</td>
              <td>{r.level === "L1" ? <span className="badge b-up">L1</span> : <span className="faint">{r.level}</span>}{r.order_share != null && <span className="faint"> {r.order_share}%</span>}</td>
              <td title={r.supplier}>{r.supplier}</td><td className="faint" title={r.tender_no}>{r.tender_no}</td><td className="mut">{day(r.valid_to)}</td>
            </tr>))}</tbody>
        </table>
      ) : <div className="empty">no state tender for this composition</div>}
    </Panel>
  );
}

export function GlobalRegs({ g }: { g: Row | undefined }) {
  const [tab, setTab] = useState<"us" | "pat" | "who" | "ema">("us");
  if (!g) return null;
  const ndc = g.us_ndc ?? {};
  return (
    <Panel title="Global registrations" sub="US FDA (Drugs@FDA · Orange Book · NDC) · WHO prequalification · EMA"
      right={<Tabs value={tab} onChange={setTab} tabs={[["us", `US apps ${g.us_applications?.length ?? 0}`], ["pat", `patents ${g.us_patents?.length ?? 0}`], ["who", `WHO PQ ${g.who_pq?.length ?? 0}`], ["ema", `EMA ${g.ema?.length ?? 0}`]]} />}>
      {ndc.n > 0 && <div className="faint" style={{ marginBottom: 6 }}>{num(ndc.n)} US NDC listings from {num(ndc.labelers)} labelers · {num(ndc.indian_group_ndcs)} by groups tracked here{ndc.indian_groups?.length ? `: ${ndc.indian_groups.slice(0, 8).join(", ")}` : ""}</div>}
      {tab === "us" && (g.us_applications?.length ? <table className="tt"><tbody>{g.us_applications.map((a: Row) => (
        <tr key={a.application_number}><td className="mut">{a.application_number}</td><td>{a.parent ? <Link to={`/g/${a.parent_slug}`}>{a.sponsor}</Link> : a.sponsor}</td>
          <td className="mut" title={a.brands}>{a.brands}</td><td className="faint">{a.dosage_forms}</td><td className="mut">{a.marketing_status}</td><td>{day(a.last_action)}</td></tr>))}</tbody></table>
        : <div className="empty">no US applications matched</div>)}
      {tab === "pat" && (g.us_patents?.length ? <table className="tt"><thead><tr><th>Application</th><th>Kind</th><th>Number / code</th><th>Use</th><th>Expires</th></tr></thead><tbody>{g.us_patents.map((p: Row, i: number) => (
        <tr key={i}><td className="mut">{p.application_number}</td><td>{p.kind}</td><td>{p.code}</td><td className="faint">{p.use_code}</td><td className="amb">{day(p.expires_on)}</td></tr>))}</tbody></table>
        : <div className="empty">no live US patents or exclusivities</div>)}
      {tab === "who" && (g.who_pq?.length ? <table className="tt"><tbody>{g.who_pq.map((w: Row) => (
        <tr key={w.ref}><td className="mut">{w.ref}</td><td title={w.inn}>{w.inn}</td><td>{w.applicant}</td><td className="faint">{w.dosage_form}</td><td>{day(w.prequalified_on)}</td></tr>))}</tbody></table>
        : <div className="empty">not WHO-prequalified</div>)}
      {tab === "ema" && (g.ema?.length ? <table className="tt"><tbody>{g.ema.map((e: Row, i: number) => {
        const name = e.name_of_medicine ?? e.medicine_name ?? Object.values(e)[1];
        const status = e.medicine_status ?? e.authorisation_status ?? "";
        const holder = e.marketing_authorisation_developer_applicant_holder ?? e.marketing_authorisation_holder_company_name ?? "";
        return <tr key={i}><td>{String(name)}</td><td className="mut">{String(status)}</td><td className="faint">{String(holder)}</td></tr>;
      })}</tbody></table> : <div className="empty">no EU centralised authorisation</div>)}
    </Panel>
  );
}

export function BrandRegistry({ rows }: { rows: Row[] | undefined }) {
  return (
    <Panel title="CDSCO brand-name registry" sub="Rule 84AB declarations — licensed manufacturer behind the brand">
      {rows?.length ? <table className="tt"><tbody>{rows.map((b, i) => (
        <tr key={i}><td>{b.brand_name}</td><td className="mut" title={b.generic_name}>{b.generic_name}</td><td title={b.firm_name}>{b.firm_name}</td><td className="faint">{b.license_number}</td></tr>))}</tbody></table>
        : <div className="empty">no declaration found for this brand name</div>}
    </Panel>
  );
}

export function Filings({ rows }: { rows: Row[] | undefined }) {
  return (
    <Panel title="Exchange filings" sub="NSE corporate announcements">
      {rows?.length ? rows.map((f, i) => (
        <div className="ev" key={i}><span className="ev-time">{day(f.announced_at)}</span>{f.topic && <span className={`ev-kind topic-${f.topic}`}>{f.topic}</span>}
          {f.attachment ? <a className="ev-title" href={f.attachment} target="_blank" rel="noreferrer" title={f.text}>{f.category}: {f.text}</a> : <span className="ev-title" title={f.text}>{f.category}: {f.text}</span>}</div>))
        : <div className="empty">no filings fetched</div>}
    </Panel>
  );
}

export function Tenders({ rows }: { rows: Row[] | undefined }) {
  return (
    <Panel title="Government tender wins" sub="state rate contracts held as L1 or matched supplier">
      {rows?.length ? <table className="tt"><tbody>{rows.map((r, i) => (
        <tr key={i}><td className="mut">{r.buyer}</td><td title={r.item}>{r.item}</td><td className="mut">{r.unit}</td><td className="num amb">{inr(r.rate)}</td>
          <td>{r.level === "L1" ? <span className="badge b-up">L1</span> : <span className="faint">{r.level}</span>}{r.order_share != null && <span className="faint"> {r.order_share}%</span>}</td></tr>))}</tbody></table>
        : <div className="empty">no state tender contracts matched</div>}
    </Panel>
  );
}

export function Licences({ rows }: { rows: Row[] | undefined }) {
  return (
    <Panel title="Manufacturing licences" sub="from CDSCO brand-name declarations">
      {rows?.length ? <table className="tt"><tbody>{rows.map((l, i) => (
        <tr key={i}><td>{l.license_number}</td><td className="mut" title={l.firm}>{l.firm}</td><td className="num">{num(l.brands)} brands</td></tr>))}</tbody></table>
        : <div className="empty">no declarations matched</div>}
    </Panel>
  );
}

export function UsPortfolio({ p, recent, ndc, pq }: { p: Row | null | undefined; recent: Row[] | undefined; ndc: number; pq: Row[] | undefined }) {
  return (
    <Panel title="US & WHO footprint" sub={p ? `${num(p.applications)} FDA applications · ${num(p.andas)} ANDA · ${num(p.ndas)} NDA · ${num(p.blas)} BLA · ${num(ndc)} NDC listings · ${num(pq?.length)} WHO PQ` : "openFDA"}>
      {recent?.length ? <table className="tt"><tbody>{recent.map((a) => (
        <tr key={a.application_number}><td className="mut">{a.application_number}</td><td title={a.ingredients}>{a.brands || a.ingredients}</td><td className="faint">{a.dosage_forms}</td><td className="mut">{a.marketing_status}</td><td>{day(a.last_action)}</td></tr>))}</tbody></table>
        : <div className="empty">no US applications matched</div>}
    </Panel>
  );
}

export function MoleculeReference({ r }: { r: Row | null | undefined }) {
  const [sec, setSec] = useState<string | null>(null);
  if (!r) return null;
  const g: Row | undefined = r.cdci?.[0];
  const label: Row = r.us_label?.sections ?? {};
  const keys = Object.keys(LABEL_TITLES).filter((k) => label[k]);
  const open = sec ?? keys[0];
  return (
    <Panel title="Molecule reference" sub="no product label on record — molecule-level reference text, not this brand's own leaflet">
      <div className="grid cols-2">
        <div className="stack-sm">
          {g ? (
            <>
              <div className="faint">CDCI national drug terminology · {g.generic_name}</div>
              {g.therapeutic_role && <div className="chips"><span className="chip">{g.therapeutic_role}</span>{g.classification_of_drugs && <span className="chip">{g.classification_of_drugs}</span>}</div>}
              {g.indication && <div><div className="mut">Indication</div><div className="label-text">{g.indication}</div></div>}
              {g.contra_indication && <div><div className="mut">Contraindications</div><div className="label-text">{g.contra_indication}</div></div>}
              {g.interaction_with_drugs && <div><div className="mut">Interactions</div><div className="label-text">{g.interaction_with_drugs}</div></div>}
            </>
          ) : <div className="empty">no CDCI monograph for this exact composition</div>}
        </div>
        <div>
          {keys.length ? (
            <>
              <div className="faint">US prescribing label · {r.us_label.meta?.generic} · {r.us_label.meta?.manufacturer}</div>
              <div className="chips">{keys.map((k) => (
                <button key={k} className={`chip ${k === open ? "chip-on" : ""}`} onClick={() => setSec(k)}>{LABEL_TITLES[k]}</button>))}</div>
              <div className="label-text">{label[open]}</div>
            </>
          ) : <div className="empty">no single-ingredient US label</div>}
        </div>
      </div>
    </Panel>
  );
}

export function Debarments({ rows, showFirm = false }: { rows: Row[] | undefined; showFirm?: boolean }) {
  if (!rows?.length) return null;
  return (
    <Panel title="State blacklisting orders" sub="firms debarred by state medical corporations, mostly for NSQ batches">
      <table className="tt"><tbody>{rows.map((d, i) => (
        <tr key={i}><td>{day(d.ordered_on)}</td><td className="mut">{d.state}</td>{showFirm && <td title={d.firm}>{d.firm}</td>}
          <td title={d.drug_text}>{d.drug_text}</td><td className="neg">{d.reason}</td><td className="faint">{d.years ? `${d.years} yr` : ""}</td>
          <td>{d.document_url && <a href={d.document_url} target="_blank" rel="noreferrer">order</a>}</td></tr>))}</tbody></table>
    </Panel>
  );
}

export function CeilingHistory({ rows }: { rows: Row[] | undefined }) {
  if (!rows?.length) return null;
  const years = [...new Set(rows.map((r) => r.year))].sort();
  if (years.length < 2) return null;
  const byForm = new Map<string, Row>();
  for (const r of rows) {
    const k = `${(r.form_strength || "").toLowerCase()} | ${(r.unit || "").toLowerCase()}`;
    const e = byForm.get(k) ?? { form: r.form_strength, unit: r.unit };
    e[r.year] = r.ceiling_price;
    byForm.set(k, e);
  }
  const list = [...byForm.values()].filter((e) => years.filter((y) => e[y] != null).length >= 2);
  if (!list.length) return null;
  return (
    <Panel title="Ceiling price history" sub="NPPA notified ceiling per unit — formulations notified in at least two years">
      <table className="tt">
        <thead><tr><th>Formulation</th><th>Unit</th>{years.map((y) => <th key={y} className="num">{y}</th>)}</tr></thead>
        <tbody>{list.slice(0, 40).map((e, i) => (
          <tr key={i}><td title={e.form}>{e.form}</td><td className="faint">{e.unit}</td>
            {years.map((y) => <td key={y} className="num amb">{e[y] != null ? inr(e[y]) : ""}</td>)}</tr>))}</tbody>
      </table>
    </Panel>
  );
}

export function PvpiAlerts({ rows }: { rows: Row[] | undefined }) {
  if (!rows?.length) return null;
  return (
    <Panel title="India safety alerts (PvPI)" sub="drug safety alerts issued by the Pharmacovigilance Programme of India for healthcare professionals">
      <table className="tt"><tbody>{rows.map((r, i) => (
        <tr key={i}><td>{day(r.issue_month)}</td><td className="neg">{r.reaction}</td><td className="mut" title={r.drug_text}>{r.drug_text}</td>
          <td className="faint" title={r.indication}>{r.indication}</td></tr>))}</tbody></table>
    </Panel>
  );
}
