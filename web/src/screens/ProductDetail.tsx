import { useQuery } from "@tanstack/react-query";
import { BrandRegistry, MoleculeReference, Pharmacology, Procurement } from "../components/Depth";
import { Link, useParams } from "react-router-dom";
import { day, get, inr, num, type Row } from "../lib/api";
import { ErrorBox, Kpi, Loading, Panel, Star } from "../components/ui";
import { ProductTable } from "./Screener";

const SAFETY_ORDER = ["alcohol", "pregnancy", "breastfeeding", "driving", "kidney", "liver"];
const LEVEL_UI: Record<string, [string, string]> = {
  unsafe: ["b-down", "UNSAFE"], caution: ["b-warn", "CAUTION"], consult: ["b-info", "CONSULT"],
  safe_if_prescribed: ["b-up", "SAFE IF PRESCRIBED"], safe: ["b-up", "SAFE"], not_applicable: ["b-mute", "N/A"], info: ["b-mute", "SEE NOTE"],
};

function SafetyGrid({ safety }: { safety: Record<string, Row> }) {
  const keys = SAFETY_ORDER.filter((k) => safety[k]);
  return (
    <Panel title="Safety profile" sub="label advice, graded · reference for prescribers and pharmacists">
      <div className="safety-grid">
        {keys.map((k) => {
          const [cls, txt] = LEVEL_UI[safety[k].level] ?? LEVEL_UI.info;
          return (
            <div key={k} className="safety-cell">
              <div className="safety-head"><span>{SAFETY_LABEL[k] ?? k}</span><span className={`badge ${cls}`}>{txt}</span></div>
              <div className="safety-text">{safety[k].text}</div>
            </div>
          );
        })}
      </div>
    </Panel>
  );
}

function LabelPanel({ d }: { d: Row }) {
  const l = d.label ?? {};
  return (
    <Panel title="Label information" sub="product monograph text as published by Indian e-pharmacies (1mg-derived)">
      <div className="grid cols-2">
        <div>
          {l.introduction && <p className="prose">{l.introduction}</p>}
          {l.how_it_works && <><div className="section-title" style={{ marginTop: 8 }}>How it works</div><p className="prose">{l.how_it_works}</p></>}
          {l.how_to_use && <><div className="section-title" style={{ marginTop: 8 }}>How to use</div><p className="prose">{l.how_to_use}</p></>}
          {!l.introduction && d.uses && <p className="prose"><b>Indications:</b> {d.uses}</p>}
        </div>
        <div>
          {l.benefits?.length > 0 && <>
            <div className="section-title">Uses & benefits</div>
            {l.benefits.map((b: Row, i: number) => <p key={i} className="prose">{b.title && <b>{b.title}. </b>}{b.text}</p>)}
          </>}
          {l.quick_tips?.length > 0 && <>
            <div className="section-title" style={{ marginTop: 8 }}>Quick tips</div>
            <ul className="prose tips">{l.quick_tips.map((t: string, i: number) => <li key={i}>{t}</li>)}</ul>
          </>}
          {(l.side_effects?.length > 0 || d.side_effects) && <>
            <div className="section-title" style={{ marginTop: 8 }}>Side effects</div>
            {l.side_effects?.length ? <div className="chips">{l.side_effects.map((s: string) => <span key={s} className="chip">{s}</span>)}</div>
              : <p className="prose">{d.side_effects}</p>}
          </>}
        </div>
      </div>
    </Panel>
  );
}

const SAFETY_LABEL: Record<string, string> = {
  alcohol_interaction: "Alcohol", pregnancy: "Pregnancy", breastfeeding: "Breastfeeding", driving: "Driving", kidney: "Kidney", liver: "Liver",
};

function LivePanel({ id, catalogUnit }: { id: number; catalogUnit: number | null }) {
  const live = useQuery({ queryKey: ["product-live", id], queryFn: () => get(`/products/${id}/live`), staleTime: 3600_000 });
  if (live.isLoading) return <Panel title="Live listing" sub="DrugSetu"><Loading what="checking live listing" /></Panel>;
  if (!live.data?.found) return null;
  const l = live.data;
  // compare per unit: live and catalog often quote different pack sizes
  const pk = (l.packagings ?? []).find((p: Row) => p.mrp && Number(p.qty) > 0);
  const liveUnit = pk ? pk.mrp / Number(pk.qty) : null;
  const delta = liveUnit && catalogUnit ? ((liveUnit / catalogUnit - 1) * 100) : null;
  return (
    <Panel title={l.stale ? "DrugSetu listing (saved copy)" : "Live listing"}
      sub={l.stale ? `saved ${day(l.fetched_at)} · live API unavailable, showing the stored record` : `DrugSetu · fetched ${day(l.fetched_at)}`}>
      <div className="grid cols-2">
        <div>
          <table className="tt"><thead><tr><th>Pack</th><th>Form</th><th className="num">MRP now</th></tr></thead>
            <tbody>{l.packagings.map((p: Row, i: number) => <tr key={i}><td>{p.packaging}</td><td className="mut">{p.product_form}</td><td className="num amb">{inr(p.mrp)}</td></tr>)}</tbody></table>
          {delta != null && Math.abs(delta) >= 0.5 && (
            <div className="note">Live price ₹{liveUnit!.toFixed(2)}/unit is <b className={delta > 0 ? "neg" : "pos"}>{delta > 0 ? "+" : ""}{delta.toFixed(1)}%</b> vs catalog ₹{catalogUnit!.toFixed(2)}/unit.</div>
          )}
          <div className="kv">
            <div><span>Marketer</span>{l.marketing_company ?? "—"}</div>
            <div><span>Manufacturer</span>{l.manufacturing_company ?? "—"}</div>
            {l.how_it_works && <div><span>Mechanism</span>{l.how_it_works}</div>}
          </div>
        </div>
        <table className="tt"><thead><tr><th>Safety</th><th>Advice</th><th>Detail</th></tr></thead>
          <tbody>{Object.entries(l.safety ?? {}).map(([k, v]: [string, any]) => (
            <tr key={k}><td>{SAFETY_LABEL[k] ?? k}</td>
              <td><span className={`badge ${/unsafe|consult/.test(v.severity) ? "b-down" : /caution/.test(v.severity) ? "b-warn" : "b-up"}`}>{String(v.severity).replace(/_/g, " ")}</span></td>
              <td className="mut" title={v.description} style={{ whiteSpace: "normal" }}>{v.description}</td></tr>
          ))}</tbody></table>
      </div>
    </Panel>
  );
}

export default function ProductDetail() {
  const { id } = useParams();
  const p = useQuery({ queryKey: ["product", id], queryFn: () => get(`/products/${id}`) });
  if (p.isLoading) return <Loading />;
  if (p.error) return <ErrorBox e={p.error} />;
  const d = p.data;
  const cheapest = d.equivalents?.[0];
  const ja = d.jan_aushadhi?.[0];
  const premium = d.combo_median && d.mrp ? ((d.mrp / d.combo_median - 1) * 100) : null;
  return (
    <div className="stack">
      <div className="detail-head">
        <Star k={`p:${d.id}`} label={d.name} href={`/p/${d.id}`} />
        <span className="detail-title">{d.name}</span>
        <span className="price-big">{inr(d.mrp)}</span>
        <span className="muted">{d.pack_size}</span>
        <span className="faint">MRP as of {d.mrp_asof ?? "—"}</span>
        {d.ban_level === "exact" && <span className="badge b-down">PROHIBITED FDC</span>}
        {d.ban_level === "review" && <span className="badge b-warn">CHECK AGAINST BAN</span>}
        {d.is_discontinued && <span className="badge b-mute">DISCONTINUED</span>}
        {d.in_stock === true && <span className="badge b-up">IN STOCK (2025)</span>}
        {d.in_stock === false && <span className="badge b-mute">OUT OF STOCK (2025)</span>}
        {d.rx_required && <span className="chip">Rx</span>}
        {d.habit_forming && <span className="badge b-warn">HABIT FORMING</span>}
      </div>
      {d.ban?.length > 0 && (
        <div className={`banner ${d.ban_level === "exact" ? "banner-crit" : "banner-warn"}`}>
          {d.ban_level === "exact" ? "Matches prohibited FDC" : "Same molecules as prohibited FDC — verify strength/form"}: <b>{d.ban[0].combo_text}</b> · {d.ban[0].notification} ({day(d.ban[0].notified_on)}) · <a href={d.ban[0].source_url} target="_blank" rel="noreferrer">notification</a>
        </div>
      )}
      <div className="kpis">
        <Kpi label="Marketer" value={d.company_slug ? <Link to={`/co/${d.company_slug}`}>{d.company}</Link> : (d.company ?? "—")} sub={d.parent ? <Link to={`/g/${d.parent_slug}`}>{d.parent}</Link> : undefined} />
        <Kpi label="₹ per unit" value={d.unit_price != null ? `₹${d.unit_price.toFixed(2)}` : "—"} />
        <Kpi label="vs median brand" value={premium != null ? `${premium > 0 ? "+" : ""}${premium.toFixed(0)}%` : "—"} tone={premium != null && premium > 25 ? "down" : undefined} sub={`median ${inr(d.combo_median)}`} />
        <Kpi label="Cheapest equivalent" value={cheapest ? inr(cheapest.mrp) : "—"} sub={cheapest?.name} tone="up" />
        <Kpi label="Jan Aushadhi" value={ja ? inr(ja.mrp) : "—"} sub={ja ? `${ja.unit_size}` : "no generic listed"} />
        <Kpi label="Same-salt brands" value={num(d.combo_products)} sub={`${num(d.combo_companies)} marketers`} />
      </div>
      <div className="grid cols-3">
        <Panel title="Composition">
          <table className="tt"><tbody>{d.molecules.map((m: Row) => (
            <tr key={m.id}><td><Link to={`/m/${m.id}`}>{m.name}</Link></td><td className="amb">{m.strength}</td><td className="mut" title={m.action_class}>{m.action_class}</td><td className="num">{m.nppa_ceiling != null ? `ceiling ${inr(m.nppa_ceiling)}` : ""}</td></tr>
          ))}</tbody></table>
          {d.combo_id && <div style={{ marginTop: 6 }}><Link to={`/c/${d.combo_id}`}>full brand ladder for {d.combo_label} ›</Link></div>}
          <div className="kv">
            <div><span>Form</span>{d.dosage_form ?? "—"}</div>
            <div><span>Class</span>{d.therapeutic_class ?? "—"}</div>
            <div><span>Action</span>{d.action_class ?? "—"}</div>
            <div><span>Chemical</span>{d.chemical_class ?? "—"}</div>
            <div><span>Sources</span>{d.sources} ({d.source_count} listings)</div>
          </div>
        </Panel>
        <Panel title="Drug interactions" sub={d.interactions_source === "same_molecules" ? "molecule level · listed on another brand with the same molecules" : "reference — molecule level"}>
          {d.interactions?.length ? (
            <table className="tt"><tbody>{d.interactions.map((x: Row, i: number) => (
              <tr key={i}><td>{x.drug}</td><td><span className={`badge ${x.severity === "MAJOR" ? "b-down" : x.severity === "MODERATE" ? "b-warn" : "b-mute"}`}>{x.severity}</span></td><td className="mut" title={x.brands}>{x.brands}</td></tr>
            ))}</tbody></table>
          ) : <div className="empty">none recorded</div>}
        </Panel>
        <div className="stack">
          <Panel title="Price record">
            <table className="tt"><tbody>{d.price_history.map((h: Row, i: number) => <tr key={i}><td>{day(h.observed_on)}</td><td className="num amb">{inr(h.mrp)}</td><td className="mut">{h.source}</td></tr>)}</tbody></table>
            {d.nppa_ceiling.length > 0 && <>
              <div className="section-title" style={{ marginTop: 8 }}>NPPA ceiling (per unit)</div>
              <table className="tt"><tbody>{d.nppa_ceiling.slice(0, 6).map((c: Row, i: number) => <tr key={i}><td className="mut">{c.molecule_name} {c.form_strength}</td><td className="num amb">{inr(c.ceiling_price)}</td><td className="faint">{c.unit}</td></tr>)}</tbody></table>
            </>}
          </Panel>
          <Panel title="Maker's quality record" sub={`${num(d.nsq_same_molecule)} NSQ listings for these molecules industry-wide`}>
            {d.nsq_same_maker.length ? <table className="tt"><tbody>{d.nsq_same_maker.slice(0, 10).map((n: Row, i: number) => <tr key={i}><td>{n.alert_month}</td><td title={n.product_text}>{n.product_text}</td><td className="amb">{n.batch_no}</td></tr>)}</tbody></table> : <div className="empty">no NSQ listings for this marketer</div>}
          </Panel>
        </div>
      </div>
      {d.label?.safety && <SafetyGrid safety={d.label.safety} />}
      {(d.label || d.uses || d.side_effects) && <LabelPanel d={d} />}
      {!d.label && <MoleculeReference r={d.molecule_reference} />}
      <LivePanel id={d.id} catalogUnit={d.unit_price} />
      <Panel title="Cheapest same-composition brands" sub="per unit"><ProductTable rows={d.equivalents} /></Panel>
      <div className="grid cols-2">
        <Procurement rows={d.procurement} sub="what state medical corporations pay for this composition (per tender pack)" />
        <BrandRegistry rows={d.brand_registry} />
      </div>
      {d.pharmacology && <Pharmacology e={d.pharmacology} />}
    </div>
  );
}
