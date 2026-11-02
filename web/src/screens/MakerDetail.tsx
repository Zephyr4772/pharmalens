import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useLocation } from "react-router-dom";
import { day, get, inr, num, type Row } from "../lib/api";
import { Empty, ErrorBox, Kpi, Loading, Panel, Tabs } from "../components/ui";
import { Inferred, useShowInferred } from "../components/Linked";

const ROLE: Record<string, string> = {
  batch_manufacturer: "NSQ batches", brand_licensee: "84AB brand registrations", us_fda_firm: "US FDA actions",
  approval_applicant: "CDSCO approvals", cdci_supplier: "CDCI supplier", tender_supplier: "state tenders", debarred_firm: "debarments",
};
const REL: Record<string, [string, string]> = { own: ["b-up", "OWN"], same_group: ["b-info", "SAME GROUP"], contract: ["b-flag", "CONTRACT"] };

export const makerHref = (key: string) => `/mk/${encodeURIComponent(key)}`;

// A manufacturing firm across every source that names it (plant stage 1): role counts, who it makes for, its records.
export default function MakerDetail() {
  const key = decodeURIComponent(useLocation().pathname.replace(/^\/mk\//, ""));
  const q = useQuery({ queryKey: ["maker", key], queryFn: () => get(`/makers/${encodeURIComponent(key)}`) });
  const [tab, setTab] = useState("nsq");
  const { on, toggle, keep } = useShowInferred();
  if (q.isLoading) return <Loading />;
  if (q.error) return <ErrorBox e={q.error} />;
  const m = q.data;
  const tabs: [string, string][] = [["nsq", `NSQ ${m.nsq.length}`], ["fda", `US FDA ${m.usfda.length}`], ["appr", `approvals ${m.approvals.length}`],
    ["brands", `brand regs ${m.brand_registrations.length}`], ["tenders", `tenders ${m.tenders.length}`], ["debar", `debarments ${m.debarments.length}`]];
  const regs = (m.brand_registrations as Row[]).filter((r) => !r.product_id || !r.sku_inferred || on);
  return (
    <div className="stack">
      <div className="detail-head">
        <span className="badge b-mute">MAKER</span>
        <span className="detail-title">{m.name}</span>
        {m.country && <span className="muted">{m.country}</span>}
        {!m.distinctive && <span className="badge b-warn" title="the firm key is only generic words and initials: several firms may share it">GENERIC NAME</span>}
        {m.company && <span>catalog company <Link to={`/co/${m.company_slug}`}>{m.company}</Link></span>}
        {m.parent && <span>group <Link to={`/g/${m.parent_slug}`}>{m.parent}</Link></span>}
        {!m.parent && m.auto_group_name && <span className="faint">auto-group {m.auto_group_name}</span>}
      </div>
      <div className="kpis">
        {Object.entries(m.roles as Record<string, number>).map(([r, n]) => <Kpi key={r} label={ROLE[r] ?? r} value={num(n)} />)}
        <Kpi label="Makes for (registered brands)" value={num(m.makes_for.length)} sub={`${m.makes_for.filter((f: Row) => f.relation === "contract").length} contract`} tone="amber" />
      </div>
      <Panel title="Makes for" sub="marketers whose SKUs carry a brand this firm registered under Rule 84AB (brand word + exact ingredients)">
        {m.makes_for.length ? <table className="tt"><thead><tr><th>Marketer</th><th>Group</th><th>Relation</th><th className="num">SKUs</th><th className="num">Brands</th><th>Example</th></tr></thead><tbody>
          {m.makes_for.map((f: Row) => <tr key={f.company_id}><td><Link to={`/co/${f.company_slug}`}>{f.company}</Link></td>
            <td>{f.parent_slug ? <Link to={`/g/${f.parent_slug}`}>{f.parent}</Link> : <span className="faint">—</span>}</td>
            <td><span className={`badge ${REL[f.relation][0]}`}>{REL[f.relation][1]}</span></td><td className="num">{f.skus}</td><td className="num">{f.brands}</td>
            <td className="mut">{f.example}</td></tr>)}</tbody></table>
          : <Empty>no brand registrations matched to catalog SKUs</Empty>}
      </Panel>
      <Panel title="Records naming this firm" sub="matched on the firm name (exact firm key); hover ⓘ for the method" right={<div style={{ display: "flex", gap: 10 }}>{toggle}<Tabs value={tab} onChange={setTab} tabs={tabs} /></div>}>
        {tab === "nsq" && (keep(m.nsq).length ? <table className="tt"><tbody>{keep(m.nsq).map((n: Row, i: number) => <tr key={i}><td>{n.alert_month}</td>
          <td><span className={`badge ${n.category === "SPURIOUS" ? "b-down" : "b-warn"}`}>{n.category}</span></td><td title={n.product_text}>{n.product_text}</td>
          <td className="amb">{n.batch_no}</td><td className="mut" title={n.reason}>{n.reason}</td><td><a href={n.source_url} target="_blank" rel="noreferrer">pdf</a></td><td><Inferred r={n} /></td></tr>)}</tbody></table> : <Empty>none</Empty>)}
        {tab === "fda" && (keep(m.usfda).length ? <table className="tt"><tbody>{keep(m.usfda).map((a: Row, i: number) => <tr key={i}><td>{day(a.issued_on)}</td><td>{a.kind}</td>
          <td className="mut" title={a.subject}>{a.subject}</td><td><Inferred r={a} /></td></tr>)}</tbody></table> : <Empty>none</Empty>)}
        {tab === "appr" && (keep(m.approvals).length ? <table className="tt"><tbody>{keep(m.approvals).map((a: Row, i: number) => <tr key={i}><td>{day(a.approved_on)}</td>
          <td title={a.drug_text}>{a.drug_text}</td><td className="mut">{String(a.approval_type ?? "").replace(/_/g, " ")}</td><td><Inferred r={a} /></td></tr>)}</tbody></table> : <Empty>none</Empty>)}
        {tab === "brands" && (regs.length ? <table className="tt"><thead><tr><th>Brand</th><th>Declared generic</th><th>Licence</th><th>Catalog SKU</th><th>Marketer</th></tr></thead><tbody>
          {regs.map((r: Row, i: number) => <tr key={i}><td>{r.brand_name}</td><td className="mut" title={r.generic_name}>{r.generic_name}</td><td className="faint">{r.license_number}</td>
            <td>{r.product_id ? <Link to={`/p/${r.product_id}`}>{r.product}</Link> : <span className="faint">—</span>} {r.product_id && r.sku_inferred && <span className="badge b-mute">INFERRED</span>}</td>
            <td>{r.marketer_slug ? <Link to={`/co/${r.marketer_slug}`}>{r.marketer}</Link> : ""}</td></tr>)}</tbody></table> : <Empty>none</Empty>)}
        {tab === "tenders" && (keep(m.tenders).length ? <table className="tt"><tbody>{keep(m.tenders).map((t: Row, i: number) => <tr key={i}><td className="mut">{t.buyer}</td>
          <td title={t.item}>{t.item}</td><td className="num amb">{inr(t.rate)}</td><td className="faint">{t.level}</td><td><Inferred r={t} /></td></tr>)}</tbody></table> : <Empty>none</Empty>)}
        {tab === "debar" && (keep(m.debarments).length ? <table className="tt"><tbody>{keep(m.debarments).map((d: Row, i: number) => <tr key={i}><td>{d.state}</td>
          <td title={d.drug_text}>{d.drug_text}</td><td className="mut">{d.reason}</td><td>{day(d.ordered_on)}</td><td><Inferred r={d} /></td></tr>)}</tbody></table> : <Empty>none</Empty>)}
        {m.cdci_suppliers > 0 && <div className="faint" style={{ marginTop: 6 }}>Also a CDCI supplier ({m.cdci_suppliers} supplier record{m.cdci_suppliers > 1 ? "s" : ""}).</div>}
      </Panel>
    </div>
  );
}
