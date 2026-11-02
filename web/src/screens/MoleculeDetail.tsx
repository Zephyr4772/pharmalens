import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";
import { day, get, inr, num, type Row } from "../lib/api";
import { ShareTable } from "../components/Share";
import { ErrorBox, Kpi, Loading, Pager, Panel, Star } from "../components/ui";
import { ProductTable } from "./Screener";
import { Outcome } from "./Pipeline";
import { CeilingHistory, Debarments, GlobalRegs, Pharmacology, Procurement, PvpiAlerts } from "../components/Depth";
import { MoleculeLinks } from "../components/Linked";

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
        {d.nlem?.length > 0 && <span className="badge b-up" title={d.nlem.map((n: Row) => `${n.section} · ${n.level} · ${n.dosage}`).join(" | ")}>NLEM 2022 · {d.nlem[0].level}</span>}
        {d.nppa_ceiling?.length > 0 && <span className="badge b-info">NPPA PRICE-CONTROLLED</span>}
        {d.bans?.length > 0 && <span className="badge b-down">{d.bans.length} PROHIBITED FDCs</span>}
      </div>
      <div className="kpis">
        <Kpi label="SKUs" value={num(d.product_count)} />
        <Kpi label="Marketers" value={num(d.company_count)} />
        <Kpi label="Combinations" value={num(d.combo_count)} />
        <Kpi label="Concentration (HHI)" value={num(d.stats?.hhi)} />
        <Kpi label="Lowest NPPA ceiling" value={d.nppa_ceiling.length ? inr(Math.min(...d.nppa_ceiling.map((c: Row) => c.ceiling_price).filter((x: number) => x != null))) : "—"} />
        <Kpi label="NSQ batches" value={num(d.nsq.length)} tone={d.nsq.length ? "down" : undefined} />
        <Kpi label="Jan Aushadhi" value={d.jan_aushadhi.length ? inr(d.jan_aushadhi[0].mrp) : "—"} sub={d.jan_aushadhi[0]?.unit_size} />
        <Kpi label="Registered brands" value={num(d.brand_registry_count?.n)} sub={d.brand_registry_count?.firms ? `${num(d.brand_registry_count.firms)} licensed firms` : undefined} />
        <Kpi label="US FDA applications" value={num(d.global?.us_applications?.length)} sub={d.global?.us_ndc?.n ? `${num(d.global.us_ndc.n)} NDCs` : undefined} />
      </div>
      <Pharmacology e={d.pharmacology} />
      <PvpiAlerts rows={d.pvpi} />
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
      <div className="grid cols-3">
        <Panel title="Regulatory pipeline — SEC" sub="CDSCO expert committee agenda items for this molecule">
          {d.sec.length ? <table className="tt"><tbody>{d.sec.map((x: Row, i: number) => (
            <tr key={i}><td>{day(x.meeting_date)}</td><td title={x.drug_text}>{x.drug_text}</td><td className="mut" title={x.firm}>{x.firm}</td><td><Outcome o={x.outcome} /></td></tr>
          ))}</tbody></table> : <div className="empty">no SEC items</div>}
        </Panel>
        <Panel title="CDSCO new drug approvals">
          {d.approvals.length ? <table className="tt"><tbody>{d.approvals.map((a: Row, i: number) => (
            <tr key={i}><td>{day(a.approved_on)}</td><td title={a.drug_text}>{a.drug_text}</td><td className="mut" title={a.indication}>{a.indication}</td></tr>
          ))}</tbody></table> : <div className="empty">no new-drug approvals listed</div>}
        </Panel>
        <Panel title="Clinical trials in India">
          {d.trials.length ? <table className="tt"><tbody>{d.trials.map((t: Row) => (
            <tr key={t.nct_id}><td><a href={`https://clinicaltrials.gov/study/${t.nct_id}`} target="_blank" rel="noreferrer">{t.nct_id}</a></td>
              <td title={t.title}>{t.title}</td><td className="mut">{t.phase?.replace(/PHASE/g, "P")}</td><td className="mut">{t.status?.toLowerCase().replace(/_/g, " ")}</td></tr>
          ))}</tbody></table> : <div className="empty">no trials with Indian sites</div>}
        </Panel>
      </div>
      <div className="grid cols-2">
        <Procurement rows={d.procurement} />
        <GlobalRegs g={d.global} />
      </div>
      {d.cdci?.length > 0 && (
        <div className="grid cols-3">
          <Panel title="National drug terminology (CDCI)" sub="NRCeS / C-DAC Common Drug Codes for India · CC BY 4.0">
            <table className="tt"><tbody>{[["Substance", "substance_name"], ["CDCI code", "identifier"], ["CAS", "cas_number"], ["UNII", "unii"], ["Formula", "molecular_formula"], ["IUPAC", "iupac_name"]]
              .filter(([, k]) => d.cdci[0][k]).map(([l, k]) => <tr key={k}><td className="mut">{l}</td><td style={{ whiteSpace: "normal" }}>{String(d.cdci[0][k])}</td></tr>)}</tbody></table>
            {d.cdci[0].substance_description && <div className="label-text">{d.cdci[0].substance_description}</div>}
            {d.cdci[0].toxicity && <div className="label-text"><span className="neg">Toxicity · </span>{d.cdci[0].toxicity}</div>}
          </Panel>
          <Panel title="CDCI generic monographs" sub="indication · contraindications · interactions (hover)" className="span-2">
            {d.cdci_generics?.length ? <table className="tt"><tbody>{d.cdci_generics.map((g: Row, i: number) => (
              <tr key={i}><td title={g.generic_name}>{g.generic_name}</td><td className="mut" title={g.indication}>{g.indication}</td>
                <td className="neg" title={g.contra_indication}>{g.contra_indication}</td><td className="faint" title={g.interaction_with_drugs}>{g.interaction_with_drugs}</td></tr>))}</tbody></table>
              : <div className="empty">no generic entries</div>}
          </Panel>
        </div>
      )}
      <MoleculeLinks links={d.links} />
      <CeilingHistory rows={d.ceiling_history} />
      <Debarments rows={d.debarments} showFirm />
      <Panel title={`Single-molecule brands — cheapest per unit first`} sub={prods.data ? `${num(prods.data.meta.total)} active SKUs` : ""}
        right={<Link to={`/screener?molecule_id=${d.id}`}>open in screener ›</Link>}>
        {prods.isLoading ? <Loading /> : <ProductTable rows={prods.data?.data ?? []} />}
        <Pager meta={prods.data?.meta} page={page} setPage={setPage} />
      </Panel>
    </div>
  );
}
