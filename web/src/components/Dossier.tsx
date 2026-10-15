import { useNavigate, Link } from "react-router-dom";
import { inr, num, share, type Row } from "../lib/api";
import { Bar, Panel } from "./ui";
import { ProductTable } from "../screens/Screener";

// Shared portfolio / market-position / quality blocks for company and group pages.
export function Dossier({ d }: { d: Row }) {
  const nav = useNavigate();
  const maxSku = Math.max(...(d.portfolio ?? []).map((p: Row) => p.skus), 1);
  return (
    <>
      <div className="grid cols-3">
        <Panel title="Portfolio by therapy" sub="active SKUs">
          {d.portfolio.map((p: Row) => (
            <Bar key={p.therapeutic_class ?? "x"} label={p.therapeutic_class ?? "unclassified"} value={p.skus} max={maxSku}
              text={`${num(p.skus)} · ${inr(p.median_mrp)}`} />
          ))}
        </Panel>
        <Panel title="Position in each therapy segment" sub="est. value share · rank among marketers" className="span-2">
          <table className="tt">
            <thead><tr><th>Segment</th><th className="num">SKUs</th><th className="num">Value share</th><th className="num">SKU share</th><th className="num">Rank</th><th className="num">of</th><th className="num">Segment HHI</th></tr></thead>
            <tbody>{d.class_share.map((c: Row) => (
              <tr key={c.segment} onClick={() => nav(`/screener?therapeutic_class=${encodeURIComponent(c.segment)}`)}>
                <td>{c.segment}</td><td className="num">{num(c.skus)}</td><td className="num amb">{share(c.value_share, 2)}</td><td className="num">{share(c.breadth_share, 2)}</td>
                <td className={`num ${c.rank <= 3 ? "pos" : ""}`}>#{c.rank}</td><td className="num mut">{num(c.owners)}</td><td className="num mut">{num(c.hhi)}</td>
              </tr>
            ))}</tbody>
          </table>
        </Panel>
      </div>
      <div className="grid cols-2">
        <Panel title="Top molecules" sub="by estimated value">
          <table className="tt">
            <thead><tr><th>Molecule</th><th className="num">SKUs</th><th className="num">Share</th><th className="num">Rank</th><th className="num">of</th></tr></thead>
            <tbody>{d.top_molecules.map((m: Row) => (
              <tr key={m.id} onClick={() => nav(`/m/${m.id}`)}><td>{m.name}</td><td className="num">{num(m.skus)}</td><td className="num amb">{share(m.value_share)}</td>
                <td className={`num ${m.rank === 1 ? "pos" : ""}`}>#{m.rank}</td><td className="num mut">{num(m.owners)}</td></tr>
            ))}</tbody>
          </table>
        </Panel>
        <Panel title="Category leadership" sub="combinations where this owner is #1 (≥5 competitors)">
          {d.leadership.length ? (
            <table className="tt">
              <thead><tr><th>Composition</th><th className="num">Own SKUs</th><th className="num">Share</th><th className="num">Competitors</th></tr></thead>
              <tbody>{d.leadership.map((k: Row) => (
                <tr key={k.id} onClick={() => nav(`/c/${k.id}`)}><td title={k.label}>{k.label}</td><td className="num">{num(k.skus)}</td><td className="num amb">{share(k.value_share)}</td><td className="num mut">{num(k.owners - 1)}</td></tr>
              ))}</tbody>
            </table>
          ) : <div className="empty">no category leadership in contested combinations</div>}
        </Panel>
      </div>
      <div className="grid cols-2">
        <Panel title="Quality record — CDSCO NSQ / spurious listings">
          {d.nsq.length ? (
            <table className="tt"><tbody>{d.nsq.map((n: Row, i: number) => (
              <tr key={i}><td>{n.alert_month}</td><td><span className={`badge ${n.category === "SPURIOUS" ? "b-down" : "b-warn"}`}>{n.category}</span></td>
                <td title={n.product_text}>{n.product_text}</td><td className="amb">{n.batch_no}</td><td className="mut" title={n.reason}>{n.reason}</td>
                <td><a href={n.source_url} target="_blank" rel="noreferrer">pdf</a></td></tr>
            ))}</tbody></table>
          ) : <div className="empty">no NSQ listings matched to this marketer</div>}
        </Panel>
        <Panel title="SKUs matching prohibited FDCs" sub="still listed as active">
          {d.banned_skus.length ? (
            <table className="tt"><tbody>{d.banned_skus.map((p: Row) => (
              <tr key={p.id} onClick={() => nav(`/p/${p.id}`)}><td>{p.name}</td><td className="mut">{p.label}</td><td className="num">{inr(p.mrp)}</td>
                <td><span className={`badge ${p.ban_level === "exact" ? "b-down" : "b-warn"}`}>{p.ban_level === "exact" ? "match" : "check"}</span></td></tr>
            ))}</tbody></table>
          ) : <div className="empty">none</div>}
        </Panel>
      </div>
      <Panel title="Most widely listed brands" right={d.slug && <Link to={`/screener?${d.subsidiaries ? "parent_id" : "company_id"}=${d.id}`}>all SKUs in screener ›</Link>}>
        <ProductTable rows={d.top_brands} showCompany={!!d.subsidiaries} />
      </Panel>
    </>
  );
}
