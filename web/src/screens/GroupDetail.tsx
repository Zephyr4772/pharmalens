import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { crore, day, get, num, signed, type Row } from "../lib/api";
import { Dossier } from "../components/Dossier";
import { ErrorBox, Kpi, LineChart, Loading, Panel, Star } from "../components/ui";

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
        {d.price != null && <span className="price-big">₹{d.price.toLocaleString("en-IN", { maximumFractionDigits: 2 })}</span>}
        {d.change_pct != null && <span className={d.change_pct >= 0 ? "pos" : "neg"}>{signed(d.change_pct)}</span>}
      </div>
      <div className="kpis">
        <Kpi label="SKUs (India retail)" value={num(skus)} />
        <Kpi label="Legal entities" value={num(d.subsidiaries.length)} />
        <Kpi label="Market cap" value={d.market_cap ? crore(d.market_cap) : "—"} />
        <Kpi label="52w range" value={d.week52_low ? `${d.week52_low.toFixed(0)} – ${d.week52_high.toFixed(0)}` : "—"} />
        <Kpi label="NSQ listings" value={num(d.nsq.length)} tone={d.nsq.length ? "down" : undefined} />
        <Kpi label="USFDA recalls" value={num(d.usfda.length)} tone={d.usfda.length ? "down" : undefined} />
      </div>
      {d.history?.length > 1 && (
        <Panel title="Share price" sub="1 year, daily close (NSE)"><LineChart data={d.history} x="d" y="close" fmt={(v) => `₹${v.toFixed(0)}`} /></Panel>
      )}
      <div className="grid cols-3">
        <Panel title="Entities in group">
          <table className="tt"><tbody>{d.subsidiaries.map((s: Row) => (
            <tr key={s.id}><td><Link to={`/co/${s.slug}`}>{s.name}</Link></td><td className="num">{num(s.product_count)}</td><td className="num mut">{num(s.molecule_count)} mol</td></tr>
          ))}</tbody></table>
        </Panel>
        <Panel title="USFDA actions" sub="recalls of India-made products">
          {d.usfda.length ? d.usfda.map((u: Row, i: number) => <div className="ev" key={i}><span className="ev-time">{day(u.issued_on)}</span><span className="ev-title" title={u.subject}>{u.subject}</span></div>) : <div className="empty">none on record</div>}
        </Panel>
        <Panel title="News">
          {d.news.length ? d.news.map((n: Row) => <div className="ev" key={n.id}><span className="ev-time">{day(n.published_at)}</span><span className={`ev-kind topic-${n.topic}`}>{n.topic}</span><a className="ev-title" href={n.url} target="_blank" rel="noreferrer">{n.title}</a></div>) : <div className="empty">no recent coverage</div>}
        </Panel>
      </div>
      <Dossier d={d} />
    </div>
  );
}
