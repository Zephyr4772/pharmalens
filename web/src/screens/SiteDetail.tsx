import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useLocation } from "react-router-dom";
import { day, get, num, type Row } from "../lib/api";
import { Empty, ErrorBox, Kpi, Loading, Panel, Tabs } from "../components/ui";
import { Inferred, Plants, useShowInferred } from "../components/Linked";

// One plant of one firm (plant stage 2): every record that carries its address.
export default function SiteDetail() {
  const key = decodeURIComponent(useLocation().pathname.replace(/^\/st\//, ""));
  const q = useQuery({ queryKey: ["site", key], queryFn: () => get(`/sites/${encodeURIComponent(key)}`) });
  const [tab, setTab] = useState("nsq");
  const { toggle, keep } = useShowInferred();
  if (q.isLoading) return <Loading />;
  if (q.error) return <ErrorBox e={q.error} />;
  const s = q.data;
  const where = s.kind === "pin" ? `PIN ${s.pin}` : s.kind === "district" ? `${key.split("|")[1].replace(":", " · ")} (district-level: no PIN in the records)` : `${s.country}`;
  return (
    <div className="stack">
      <div className="detail-head">
        <span className="badge b-mute">SITE</span>
        <span className="detail-title">{s.maker_name}</span>
        <span className="amb">{where}</span>
        {s.state && <span className="muted">{s.state}</span>}
        {s.units && <span className="faint">{s.units}</span>}
        <Link to={`/mk/${encodeURIComponent(s.maker_key)}`}>firm profile ›</Link>
        {s.company && <span>company <Link to={`/co/${s.company_slug}`}>{s.company}</Link></span>}
        {s.parent && <span>group <Link to={`/g/${s.parent_slug}`}>{s.parent}</Link></span>}
      </div>
      <div className="faint" title="the most frequent address text for this site">{s.address}</div>
      <div className="kpis">
        <Kpi label="Approvals naming this site" value={num(s.approvals.length)} />
        <Kpi label="NSQ / spurious batches" value={num(s.nsq.length)} tone={s.nsq.length ? "down" : undefined} />
        <Kpi label="US FDA actions" value={num(s.usfda.length)} tone={s.usfda.length ? "down" : undefined} />
        <Kpi label="Debarments" value={num(s.debarments.length)} tone={s.debarments.length ? "down" : undefined} />
      </div>
      <Panel title="Records at this site" sub="matched on the address (PIN code); without a PIN, on the firm's locality words; hover ⓘ for the method"
        right={<div style={{ display: "flex", gap: 10 }}>{toggle}<Tabs value={tab} onChange={setTab} tabs={[["nsq", `NSQ ${s.nsq.length}`], ["fda", `US FDA ${s.usfda.length}`],
          ["appr", `approvals ${s.approvals.length}`], ["debar", `debarments ${s.debarments.length}`]]} /></div>}>
        {tab === "nsq" && (keep(s.nsq).length ? <table className="tt"><tbody>{keep(s.nsq).map((n: Row, i: number) => <tr key={i}><td>{n.alert_month}</td>
          <td><span className={`badge ${n.category === "SPURIOUS" ? "b-down" : "b-warn"}`}>{n.category}</span></td><td title={n.product_text}>{n.product_text}</td>
          <td className="amb">{n.batch_no}</td><td className="mut" title={n.reason}>{n.reason}</td><td><Inferred r={n} /></td></tr>)}</tbody></table> : <Empty>none</Empty>)}
        {tab === "fda" && (keep(s.usfda).length ? <table className="tt"><tbody>{keep(s.usfda).map((a: Row, i: number) => <tr key={i}><td>{day(a.issued_on)}</td>
          <td>{a.kind}</td><td className="mut" title={a.subject}>{a.subject}</td><td><Inferred r={a} /></td></tr>)}</tbody></table> : <Empty>none</Empty>)}
        {tab === "appr" && (keep(s.approvals).length ? <table className="tt"><tbody>{keep(s.approvals).map((a: Row, i: number) => <tr key={i}><td>{day(a.approved_on)}</td>
          <td title={a.drug_text}>{a.drug_text}</td><td className="mut">{a.applicant}</td><td><Inferred r={a} /></td></tr>)}</tbody></table> : <Empty>none</Empty>)}
        {tab === "debar" && (keep(s.debarments).length ? <table className="tt"><tbody>{keep(s.debarments).map((d: Row, i: number) => <tr key={i}><td>{d.state}</td>
          <td title={d.drug_text}>{d.drug_text}</td><td className="mut">{d.reason}</td><td>{day(d.ordered_on)}</td><td><Inferred r={d} /></td></tr>)}</tbody></table> : <Empty>none</Empty>)}
      </Panel>
      <Plants rows={s.other_sites} title="Other sites of this firm" />
    </div>
  );
}
