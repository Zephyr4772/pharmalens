import { useQuery } from "@tanstack/react-query";
import { Procurement } from "../components/Depth";
import { Link, useParams } from "react-router-dom";
import { day, get, inr, num, type Row } from "../lib/api";
import { ShareTable } from "../components/Share";
import { ErrorBox, Kpi, Loading, Panel, Star } from "../components/ui";
import { ProductTable } from "./Screener";
import { BanLinks, Timeline, UsEuStatus } from "../components/Linked";

export default function ComboDetail() {
  const { id } = useParams();
  const c = useQuery({ queryKey: ["combo", id], queryFn: () => get(`/combos/${id}`) });
  if (c.isLoading) return <Loading />;
  if (c.error) return <ErrorBox e={c.error} />;
  const d = c.data;
  const ja = d.jan_aushadhi?.[0];
  return (
    <div className="stack">
      <div className="detail-head">
        <Star k={`c:${d.id}`} label={d.label} href={`/c/${d.id}`} />
        <span className="detail-title">{d.label}</span>
        <span className="muted">{d.therapeutic_class}</span>
        {d.molecules.map((m: Row) => <Link key={m.id} className="chip" to={`/m/${m.id}`}>{m.name} {m.strength}</Link>)}
        {d.banned_skus > 0 && <span className="badge b-down">{d.banned_skus} SKUs MATCH A BAN</span>}
      </div>
      <div className="kpis">
        <Kpi label="Brands" value={num(d.product_count)} />
        <Kpi label="Marketers" value={num(d.company_count)} />
        <Kpi label="Cheapest / unit" value={inr(d.min_unit)} tone="up" sub={`pack from ${inr(d.min_mrp)}`} />
        <Kpi label="Median / unit" value={inr(d.median_unit)} tone="amber" sub={`median pack ${inr(d.median_mrp)}`} />
        <Kpi label="Costliest / unit" value={inr(d.max_unit)} tone="down" />
        <Kpi label="Spread" value={d.min_unit ? `${(d.max_unit / d.min_unit).toFixed(1)}×` : "—"} sub={d.form_family} />
        <Kpi label="Jan Aushadhi" value={ja ? inr(ja.mrp) : "—"} sub={ja ? `${ja.unit_size} · ${ja.name}` : "no PMBI equivalent"} />
      </div>
      {d.ban?.length > 0 && (
        <Panel title="Prohibition notifications for these molecules" sub="SKUs are flagged only when strength and dosage form also match">
          <table className="tt"><tbody>{d.ban.map((b: Row, i: number) => <tr key={i}><td>{b.combo_text}</td><td className="mut">{b.notification}</td><td>{day(b.notified_on)}</td><td><span className="badge b-down">{b.status}</span></td><td><a href={b.source_url} target="_blank" rel="noreferrer">pdf</a></td></tr>)}</tbody></table>
        </Panel>
      )}
      <div className="grid cols-3">
        <Panel title="Brand ladder" sub="cheapest per unit first — every marketed brand of this exact composition" className="span-2">
          <ProductTable rows={d.brands} />
        </Panel>
        <div className="stack">
          <Panel title="Who owns this combination"><ShareTable rows={d.share} stats={d.stats} /></Panel>
          <Panel title="Other strengths">
            {d.related.length ? <table className="tt"><tbody>{d.related.map((r: Row) => <tr key={r.id}><td><Link to={`/c/${r.id}`}>{r.label}</Link></td><td className="num">{num(r.product_count)}</td><td className="num amb">{inr(r.median_mrp)}</td></tr>)}</tbody></table> : <div className="empty">only strength marketed</div>}
          </Panel>
        </div>
      </div>
      <Procurement rows={d.procurement} sub="state tender rates for these molecules (all strengths) — compare against the brand ladder" />
      <BanLinks rows={d.ban_links} />
      <div className="grid cols-2">
        <Timeline rows={d.timeline} sub="events about exactly this combination of ingredients (complete ingredient match only)" />
        <UsEuStatus s={d.us_eu} what="combination" />
      </div>
    </div>
  );
}
