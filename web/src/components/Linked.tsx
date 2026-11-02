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

// US and EU status of an exact ingredient set: Orange Book (NDA / ANDA), live patents and exclusivities, EMA.
export function UsEuStatus({ s, what }: { s: Row | null | undefined; what: string }) {
  const [tab, setTab] = useState<"ob" | "pat" | "ema">("ob");
  if (!s) return null;
  const m = s.summary;
  return (
    <Panel title="US & EU status" sub={`records with exactly the same ingredients as this ${what} (any strength or form) · matched on the full ingredient set`}
      right={<Tabs value={tab} onChange={setTab} tabs={[["ob", `Orange Book ${s.orange_book.length}`], ["pat", `patents & excl. ${s.patents.length}`], ["ema", `EMA ${s.ema.length}`]]} />}>
      <div className="chips" style={{ marginBottom: 6 }}>
        <span className="chip">{m.nda} NDA ({m.nda_marketed} marketed)</span>
        <span className="chip">{m.anda} ANDA generics ({m.anda_marketed} marketed)</span>
        {m.first_generic && <span className="chip">first US generic {day(m.first_generic)}</span>}
        {m.reference_brands?.length > 0 && <span className="chip">reference: {m.reference_brands.join(", ")}</span>}
        <span className={`chip ${m.protection_until ? "chip-on" : ""}`}>{m.patents_live} live patents · {m.exclusivities_live} exclusivities{m.protection_until ? ` · last expiry ${day(m.protection_until)}` : ""}</span>
        <span className="chip">{m.ema ? `${m.ema} EU authorisation${m.ema > 1 ? "s" : ""}` : "no EU central authorisation"}</span>
      </div>
      {m.indian_groups?.length > 0 && <div className="faint" style={{ marginBottom: 6 }}>US generics held by tracked Indian groups: {m.indian_groups.join(", ")}</div>}
      {tab === "ob" && (s.orange_book.length ? <table className="tt"><thead><tr><th>Appl.</th><th>Type</th><th>Brand</th><th>Strength</th><th>Form</th><th>Holder</th><th>Approved</th><th>Status</th><th /></tr></thead><tbody>
        {s.orange_book.map((o: Row) => <tr key={`${o.application_number}-${o.product_number}`}><td className="mut">{o.application_number}</td>
          <td>{o.app_type === "N" ? <span className="badge b-info">NDA{o.rld ? " RLD" : ""}</span> : "ANDA"}</td><td>{o.brand}</td><td className="faint">{o.strengths}</td>
          <td className="faint">{o.dosage_form}</td><td>{o.parent_slug ? <Link to={`/g/${o.parent_slug}`}>{o.applicant}</Link> : o.applicant}</td>
          <td>{day(o.approval_date)}</td><td className="mut">{o.marketing_status}</td><td><Inferred r={o} /></td></tr>)}</tbody></table>
        : <div className="empty">no Orange Book product with exactly these ingredients</div>)}
      {tab === "pat" && (s.patents.length ? <table className="tt"><thead><tr><th>Appl.</th><th>Kind</th><th>Number / code</th><th>Use</th><th>Expires</th></tr></thead><tbody>
        {s.patents.map((p: Row, i: number) => <tr key={i}><td className="mut">{p.application_number}/{p.product_number}</td><td>{p.kind}</td><td>{p.code}</td>
          <td className="faint">{p.use_code}</td><td className="amb">{day(p.expires_on)}</td></tr>)}</tbody></table>
        : <div className="empty">no live US patents or exclusivities</div>)}
      {tab === "ema" && (s.ema.length ? <table className="tt"><tbody>{s.ema.map((e: Row) => <tr key={e.ema_product_number}><td>{e.name_of_medicine}</td>
        <td className="mut">{e.medicine_status}</td><td className="faint">{e.holder}</td><td>{e.generic === "Yes" ? "generic" : e.biosimilar === "Yes" ? "biosimilar" : ""}</td>
        <td>{day(e.marketing_authorisation_date)}</td><td><Inferred r={e} /></td></tr>)}</tbody></table>
        : <div className="empty">no EU centralised authorisation with these ingredients</div>)}
    </Panel>
  );
}

// Events linked to this entity through event_entities; inferred links only on request.
export function Timeline({ rows, sub }: { rows: Row[] | undefined; sub?: string }) {
  const { toggle, keep } = useShowInferred();
  const shown = keep(rows);
  if (!rows?.length) return null;
  return (
    <Panel title="Timeline" sub={sub ?? "events linked to this entity, newest first · hover ⓘ for why"} className="tall" right={toggle}>
      {shown.length ? shown.map((e) => (
        <div key={e.id} className={`ev ev-${e.severity}`}>
          <span className="ev-time" title={e.ts}>{day(e.ts)}</span>
          <span className="ev-kind">{String(e.kind).toUpperCase()}</span>
          {e.url ? <a href={e.url} target="_blank" rel="noreferrer" className="ev-title">{e.title}</a> : <span className="ev-title">{e.title}</span>}
          <Inferred r={e} />
        </div>
      )) : <div className="empty">only inferred links: tick “show inferred”</div>}
    </Panel>
  );
}

// Prohibited-FDC notifications whose ingredient set matches this combination (Phase 1 #12).
export function BanLinks({ rows }: { rows: Row[] | undefined }) {
  const { toggle, keep } = useShowInferred();
  const shown = keep(rows);
  if (!rows?.length) return null;
  return (
    <Panel title="Prohibited FDC notifications" sub="Gazette bans whose ingredients match this combination exactly (salt forms folded); check strengths in the notification" right={toggle}>
      {shown.length ? <table className="tt"><tbody>{shown.map((b) => <tr key={b.id}>
        <td><span className={`badge ${b.status === "banned" ? "b-down" : "b-warn"}`}>{String(b.status).toUpperCase()}</span></td>
        <td title={b.combo_text}>{b.combo_text}</td><td className="mut">{b.notification}</td><td>{day(b.notified_on)}</td>
        <td>{b.source_url && <a href={b.source_url} target="_blank" rel="noreferrer">pdf</a>}</td><td><Inferred r={b} /></td></tr>)}</tbody></table>
        : <div className="empty">only inferred matches: tick “show inferred”</div>}
    </Panel>
  );
}

const LAUNCH_KIND: Record<string, string> = { registry_arrival: "NEW BRAND", nppa_launch_price: "NPPA PRICE", cdci_record_date: "CDCI DATE" };

// Dated launch signals (Phase 1 #5): new brand registrations, NPPA new-drug prices, CDCI record dates (inferred).
export function LaunchSignals({ rows, showCompany = true }: { rows: Row[] | undefined; showCompany?: boolean }) {
  const { toggle, keep } = useShowInferred();
  const shown = keep(rows);
  if (!rows?.length) return null;
  return (
    <Panel title="Launch signals" sub="dated evidence of products coming to market: new 84AB brand registrations, NPPA new-drug retail prices; CDCI record dates are inferred (added or updated by)" className="tall" right={toggle}>
      {shown.length ? <table className="tt"><tbody>{shown.map((l, i) => <tr key={i}>
        <td>{day(l.dated_on)}</td><td><span className="badge b-info">{LAUNCH_KIND[l.kind] ?? l.kind}</span></td>
        <td>{l.brand ?? ""}</td><td className="mut" title={l.evidence}>{l.ingredients ?? "ingredients not fully resolved"}</td>
        {showCompany && <td>{l.company_slug ? <Link to={`/co/${l.company_slug}`}>{l.company}</Link> : <span className="faint">—</span>}</td>}
        <td><Inferred r={l} /></td></tr>)}</tbody></table>
        : <div className="empty">only inferred signals: tick “show inferred”</div>}
    </Panel>
  );
}

// The auto-group of a company outside the curated groups (#3), and the CDSCO approvals linked to it.
export function AutoGroup({ g }: { g: Row | null | undefined }) {
  const { on, toggle } = useShowInferred();
  if (!g) return null;
  const aliases: Row[] = on ? g.possible_aliases ?? [] : [];
  return (
    <Panel title="Group" sub={g.members > 1 ? `auto-group: ${g.members} catalog names for one firm (name variants)` : "auto-group: this company on its own (not part of a curated group)"}
      right={g.possible_aliases?.length ? toggle : undefined}>
      <div><span className="badge b-mute">AUTO</span> {g.name} <span className="faint">· {g.active_skus} active SKUs</span> <Inferred r={g} /></div>
      {g.members_list?.length > 0 && <table className="tt" style={{ marginTop: 6 }}><tbody>{g.members_list.map((m: Row) => <tr key={m.id}>
        <td><Link to={`/co/${m.slug}`}>{m.name}</Link></td><td className="num faint">{m.active_count} SKUs</td></tr>)}</tbody></table>}
      {aliases.length > 0 && <table className="tt" style={{ marginTop: 6 }}><tbody>{aliases.map((m: Row) => <tr key={m.id}>
        <td><Link to={`/co/${m.slug}`}>{m.name}</Link></td><td className="faint">possible alias</td><td><Inferred r={{ ...m, inferred: true }} /></td></tr>)}</tbody></table>}
    </Panel>
  );
}

export function CompanyApprovals({ rows }: { rows: Row[] | undefined }) {
  if (!rows?.length) return null;
  return (
    <Panel title="CDSCO approvals" sub="approvals whose applicant is this company (exact firm-name match)" className="tall">
      <table className="tt"><tbody>{rows.map((a, i) => <tr key={i}><td>{day(a.approved_on)}</td><td title={a.drug_text}>{a.drug_text}</td>
        <td className="mut">{String(a.approval_type ?? "").replace(/_/g, " ")}</td><td>{a.source_url && <a href={a.source_url} target="_blank" rel="noreferrer">src</a>}</td>
        <td><Inferred r={a} /></td></tr>)}</tbody></table>
    </Panel>
  );
}

// Molecule hygiene: duplicate / misspelt / brand-glued molecule nodes folded onto one canonical molecule.
export function MoleculeHygiene({ h }: { h: Row | undefined }) {
  const { on, toggle } = useShowInferred();
  if (!h) return null;
  if (h.canonical) {
    return (
      <div className="err" style={{ borderColor: "var(--amber)", color: "inherit" }}>
        Same molecule as <Link to={`/m/${h.canonical.id}`}>{h.canonical.name}</Link> <Inferred r={h.canonical} />: this page shows only the records
        filed under this spelling; the derived panels (US & EU status, timeline, launches, linked records) use {h.canonical.name}.
      </div>
    );
  }
  const pending: Row[] = on ? h.pending ?? [] : [];
  if (!h.aliases?.length && !h.pending?.length) return null;
  return (
    <Panel title="Also listed as" sub="other catalog names folded into this molecule; their NSQ, approval, SEC, trial, news and tender records are included on this page"
      right={h.pending?.length ? toggle : undefined}>
      <div className="chips">
        {h.aliases.map((a: Row) => <span key={a.id} className="chip" title={`${a.method} · ${a.evidence}`}><Link to={`/m/${a.id}`}>{a.name}</Link> <span className="faint">{a.product_count}</span></span>)}
        {pending.map((a: Row) => <span key={`p${a.id}`} className="chip" title={`${a.method} · ${a.evidence} · awaiting review`}>
          <Link to={`/m/${a.id}`}>{a.name}</Link> <span className="badge b-mute">REVIEW</span></span>)}
      </div>
    </Panel>
  );
}

const REL_BADGE: Record<string, [string, string]> = { own: ["b-up", "OWN"], same_group: ["b-info", "SAME GROUP"], contract: ["b-flag", "CONTRACT"] };
const mkHref = (k: string) => `/mk/${encodeURIComponent(k)}`;

// Plant stage 1 on a marketer's page: which firms registered its brands (own, same group, contract), and its own maker profile.
export function MadeBy({ rows, asMaker }: { rows: Row[] | undefined; asMaker: Row[] | undefined }) {
  if (!rows?.length && !asMaker?.length) return null;
  return (
    <Panel title="Made by" sub="firms that registered this marketer's brands under Rule 84AB (brand word + exact ingredients)">
      {asMaker?.length ? <div style={{ marginBottom: 6 }}>As a manufacturer: {asMaker.map((m) => <Link key={m.maker_key} to={mkHref(m.maker_key)} style={{ marginRight: 8 }}>{m.name}</Link>)}</div> : null}
      {rows?.length ? <table className="tt"><tbody>{rows.map((f) => <tr key={f.maker_key}><td><Link to={mkHref(f.maker_key)}>{f.maker}</Link></td>
        <td><span className={`badge ${REL_BADGE[f.relation][0]}`}>{REL_BADGE[f.relation][1]}</span></td><td className="num">{f.skus} SKUs</td><td className="mut">{f.example}</td></tr>)}</tbody></table>
        : <div className="empty">no brand registrations matched</div>}
    </Panel>
  );
}

export function RegisteredMaker({ rows }: { rows: Row[] | undefined }) {
  const { toggle, keep } = useShowInferred();
  if (!rows?.length) return null;
  const shown = keep(rows);
  return (
    <Panel title="Registered manufacturer" sub="firm that registered this brand under Rule 84AB (brand word + exact ingredients match)" right={toggle}>
      {shown.length ? <table className="tt"><tbody>{shown.map((r, i) => <tr key={i}><td><Link to={mkHref(r.maker_key)}>{r.name}</Link></td>
        <td className="mut">{r.brand_name}</td><td className="faint">{r.license_number}</td><td><Inferred r={r} /></td></tr>)}</tbody></table>
        : <div className="empty">only inferred matches: tick “show inferred”</div>}
    </Panel>
  );
}
