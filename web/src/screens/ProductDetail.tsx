import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { day, get, inr, num, type Row } from "../lib/api";
import { ErrorBox, Kpi, Loading, Panel, Star } from "../components/ui";
import { ProductTable } from "./Screener";

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
        <Panel title="Drug interactions" sub="reference — molecule level">
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
      {(d.uses || d.side_effects) && (
        <Panel title="Label information" sub="as listed by retailers">
          {d.uses && <p className="prose"><b>Indications:</b> {d.uses}</p>}
          {d.side_effects && <p className="prose"><b>Common side effects:</b> {d.side_effects}</p>}
        </Panel>
      )}
      <Panel title="Cheapest same-composition brands" sub="per unit"><ProductTable rows={d.equivalents} /></Panel>
    </div>
  );
}
