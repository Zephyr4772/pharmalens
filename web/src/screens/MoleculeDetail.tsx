import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";
import { day, get, inr, num, type Row } from "../lib/api";
import { ShareTable } from "../components/Share";
import { ErrorBox, Kpi, Loading, Pager, Panel, Star } from "../components/ui";
import { ProductTable } from "./Screener";

export default function MoleculeDetail() {
  const { id } = useParams();
  const nav = useNavigate();
  const [page, setPage] = useState(1);
  const m = useQuery({ queryKey: ["molecule", id], queryFn: () => get(`/molecules/${id}`) });
  const prods = useQuery({ queryKey: ["mol-products", id, page], queryFn: () => get("/products", { molecule_id: id, mono: true, sort: "unit_asc", active_only: true, page, limit: 40 }) });
  if (m.isLoading) return <Loading />;
  if (m.error) return <ErrorBox e={m.error} />;
  const d = m.data;
  return (
    <div className="stack">
      <div className="detail-head">
        <Star k={`m:${d.id}`} label={d.name} href={`/m/${d.id}`} />
        <span className="detail-title">{d.name}</span>
        <span className="muted">{d.therapeutic_class}</span>
        <span className="muted">{d.action_class}</span>
        {d.chemical_class && <span className="faint">{d.chemical_class}</span>}
        {d.nppa_ceiling != null && <span className="badge b-info">NPPA PRICE-CONTROLLED</span>}
        {d.bans?.length > 0 && <span className="badge b-down">{d.bans.length} PROHIBITED FDCs</span>}
      </div>
      <div className="kpis">
        <Kpi label="SKUs" value={num(d.product_count)} />
        <Kpi label="Marketers" value={num(d.company_count)} />
        <Kpi label="Combinations" value={num(d.combo_count)} />
        <Kpi label="Concentration (HHI)" value={num(d.stats?.hhi)} />
        <Kpi label="Lowest NPPA ceiling" value={inr(d.nppa_ceiling)} />
        <Kpi label="NSQ batches" value={num(d.nsq.length)} tone={d.nsq.length ? "down" : undefined} />
        <Kpi label="Jan Aushadhi" value={d.jan_aushadhi.length ? inr(d.jan_aushadhi[0].mrp) : "—"} sub={d.jan_aushadhi[0]?.unit_size} />
      </div>
      <div className="grid cols-3">
        <Panel title="Market share" sub="by group/company, estimated value" className="span-2"><ShareTable rows={d.share} stats={d.stats} /></Panel>
        <div className="stack">
          <Panel title="Dosage forms">
            <table className="tt"><tbody>{d.forms.map((f: Row) => <tr key={f.dosage_form}><td>{f.dosage_form}</td><td className="num">{num(f.n)}</td><td className="num amb">{inr(f.median_mrp)}</td></tr>)}</tbody></table>
          </Panel>
          <Panel title="NPPA ceiling prices">
            {d.nppa_ceiling.length ? <table className="tt"><tbody>{d.nppa_ceiling.map((c: Row, i: number) => <tr key={i}><td className="mut">{c.form_strength}</td><td className="num amb">{inr(c.ceiling_price)}</td><td className="faint">{c.unit} · {c.year}</td></tr>)}</tbody></table> : <div className="empty">not a scheduled formulation</div>}
          </Panel>
          <Panel title="Jan Aushadhi generics">
            {d.jan_aushadhi.length ? <table className="tt"><tbody>{d.jan_aushadhi.map((j: Row) => <tr key={j.drug_code}><td title={j.name}>{j.name}</td><td>{j.unit_size}</td><td className="num amb">{inr(j.mrp)}</td></tr>)}</tbody></table> : <div className="empty">none listed</div>}
          </Panel>
        </div>
      </div>
      <div className="grid cols-2">
        <Panel title="Combinations containing this molecule" sub="click for brand ladder">
          <table className="tt">
            <thead><tr><th>Combination</th><th className="num">Brands</th><th className="num">Cos</th><th className="num">Min</th><th className="num">Median</th><th className="num">Max</th><th /></tr></thead>
            <tbody>{d.combos.map((k: Row) => (
              <tr key={k.id} onClick={() => nav(`/c/${k.id}`)}>
                <td title={k.label}>{k.label}</td><td className="num">{num(k.product_count)}</td><td className="num">{num(k.company_count)}</td>
                <td className="num">{inr(k.min_mrp)}</td><td className="num amb">{inr(k.median_mrp)}</td><td className="num">{inr(k.max_mrp)}</td>
                <td>{k.banned_skus > 0 && <span className="badge b-down">BAN {k.banned_skus}</span>}</td>
              </tr>
            ))}</tbody>
          </table>
        </Panel>
        <div className="stack">
          <Panel title="Quality failures (CDSCO NSQ/spurious)">
            {d.nsq.length ? <table className="tt"><tbody>{d.nsq.map((n: Row, i: number) => (
              <tr key={i}><td>{n.alert_month}</td><td title={n.product_text}>{n.product_text}</td><td className="amb">{n.batch_no}</td><td className="mut" title={n.manufacturer}>{n.manufacturer}</td><td className="mut" title={n.reason}>{n.reason}</td></tr>
            ))}</tbody></table> : <div className="empty">no NSQ listings</div>}
          </Panel>
          <Panel title="Prohibited combinations including this molecule">
            {d.bans.length ? <table className="tt"><tbody>{d.bans.map((b: Row, i: number) => <tr key={i}><td title={b.combo_text}>{b.combo_text}</td><td className="mut">{b.notification}</td><td>{day(b.notified_on)}</td></tr>)}</tbody></table> : <div className="empty">none</div>}
          </Panel>
          <Panel title="News">
            {d.news.length ? d.news.map((n: Row) => <div className="ev" key={n.id}><span className="ev-time">{day(n.published_at)}</span><a className="ev-title" href={n.url} target="_blank" rel="noreferrer">{n.title}</a></div>) : <div className="empty">no recent coverage</div>}
          </Panel>
        </div>
      </div>
      <Panel title={`Single-molecule brands — cheapest per unit first`} sub={prods.data ? `${num(prods.data.meta.total)} active SKUs` : ""}
        right={<Link to={`/screener?molecule_id=${d.id}`}>open in screener ›</Link>}>
        {prods.isLoading ? <Loading /> : <ProductTable rows={prods.data?.data ?? []} />}
        <Pager meta={prods.data?.meta} page={page} setPage={setPage} />
      </Panel>
    </div>
  );
}
