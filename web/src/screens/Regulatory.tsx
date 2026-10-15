import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { csvUrl, day, get, inr, num, type Row } from "../lib/api";
import { Bar, Empty, ErrorBox, Kpi, Loading, Pager, Panel, Tabs } from "../components/ui";

type Tab = "nsq" | "bans" | "docs" | "usfda" | "ja" | "ceiling" | "shortage";

export default function Regulatory() {
  const [sp, setSp] = useSearchParams();
  const tab = (sp.get("tab") as Tab) || "nsq";
  const s = useQuery({ queryKey: ["reg-summary"], queryFn: () => get("/reg/summary"), refetchInterval: 300_000 });
  if (s.isLoading) return <Loading />;
  if (s.error) return <ErrorBox e={s.error} />;
  const sm = s.data.summary;
  const maxM = Math.max(...s.data.by_month.map((m: Row) => m.nsq + m.spurious), 1);
  const maxR = Math.max(...s.data.reasons.map((r: Row) => r.n), 1);
  return (
    <div className="stack">
      <div className="kpis">
        <Kpi label="NSQ batch records" value={num(sm.nsq)} sub={`latest list ${sm.nsq_latest}`} tone="down" />
        <Kpi label="Spurious" value={num(sm.spurious)} tone="down" />
        <Kpi label="Prohibited FDC notifications" value={num(sm.banned)} sub={`${sm.restricted} restricted · last ${day(sm.last_ban)}`} />
        <Kpi label="Catalog SKUs matching a ban" value={num(sm.banned_skus_in_catalog)} sub={`${num(sm.ban_review_skus)} need pack check`} tone="down" />
        <Kpi label="Regulator documents" value={num(sm.documents)} sub={`latest ${day(sm.last_document)}`} />
        <Kpi label="USFDA recalls (India)" value={num(sm.usfda)} />
        <Kpi label="Jan Aushadhi" value={num(sm.jan_aushadhi)} sub="generics with MRP" />
      </div>
      <div className="grid cols-3">
        <Panel title="NSQ / spurious batches by month" sub="CDSCO central + state labs" className="span-2">
          <div className="hist">
            {s.data.by_month.map((m: Row) => (
              <div className="hist-col" key={m.alert_month} title={`${m.alert_month}: ${m.nsq} NSQ, ${m.spurious} spurious`}
                onClick={() => setSp({ tab: "nsq", month: m.alert_month })} style={{ cursor: "pointer" }}>
                <span className="hist-y">{m.nsq + m.spurious}</span>
                <div className="hist-bar" style={{ height: `${((m.nsq + m.spurious) / maxM) * 100}px` }} />
                <span className="hist-x">{m.alert_month.slice(2)}</span>
              </div>
            ))}
          </div>
        </Panel>
        <Panel title="Failure reasons">
          {s.data.reasons.map((r: Row) => <Bar key={r.reason} label={r.reason} value={r.n} max={maxR} text={num(r.n)} tone="cyan" />)}
        </Panel>
      </div>
      <Tabs<Tab> value={tab} onChange={(t) => setSp({ tab: t })} tabs={[
        ["nsq", "NSQ & SPURIOUS BATCHES"], ["bans", "PROHIBITED FDCs"], ["docs", "CDSCO / NPPA DOCUMENTS"],
        ["usfda", "USFDA RECALLS"], ["ja", "JAN AUSHADHI"], ["ceiling", "NPPA CEILING PRICES"], ["shortage", "SHORTAGES"],
      ]} />
      {tab === "nsq" && <NsqTab month={sp.get("month") ?? undefined} offenders={s.data.repeat_offenders} />}
      {tab === "bans" && <BansTab />}
      {tab === "docs" && <DocsTab />}
      {tab === "usfda" && <UsfdaTab />}
      {tab === "ja" && <JaTab />}
      {tab === "ceiling" && <CeilingTab />}
      {tab === "shortage" && <ShortageTab />}
    </div>
  );
}

function NsqTab({ month, offenders }: { month?: string; offenders: Row[] }) {
  const [q, setQ] = useState("");
  const [batch, setBatch] = useState("");
  const [cat, setCat] = useState("");
  const [page, setPage] = useState(1);
  const params = { q, batch, category: cat, month, page, limit: 60 };
  const r = useQuery({ queryKey: ["nsq", params], queryFn: () => get("/reg/nsq", params) });
  return (
    <div className="grid cols-4">
      <Panel title="Batch ledger" sub={month ? `month ${month}` : "all months"} className="span-3"
        right={<a href={csvUrl("/reg/nsq", { q, batch, category: cat, month })}>CSV ⤓</a>}>
        <div className="filterbar inline">
          <input placeholder="product / manufacturer" value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} />
          <input placeholder="exact batch no." value={batch} onChange={(e) => { setBatch(e.target.value); setPage(1); }} />
          <select value={cat} onChange={(e) => { setCat(e.target.value); setPage(1); }}>
            <option value="">NSQ + spurious</option><option value="NSQ">NSQ</option><option value="SPURIOUS">Spurious</option>
          </select>
        </div>
        {r.isLoading ? <Loading /> : (
          <table className="tt">
            <thead><tr><th>Month</th><th>Type</th><th>Product</th><th>Batch</th><th>Mfg/Exp</th><th>Manufacturer</th><th>Failure</th><th>Lab</th><th /></tr></thead>
            <tbody>
              {r.data?.data.map((n: Row) => (
                <tr key={n.id}>
                  <td>{n.alert_month}</td>
                  <td><span className={`badge ${n.category === "SPURIOUS" ? "b-down" : "b-warn"}`}>{n.category}</span></td>
                  <td title={n.product_text}>{n.product_text}</td>
                  <td className="amb">{n.batch_no}</td>
                  <td className="mut">{n.mfg_date} / {n.exp_date}</td>
                  <td title={n.manufacturer}>{n.company_slug ? <Link to={`/co/${n.company_slug}`}>{n.manufacturer}</Link> : n.manufacturer}</td>
                  <td title={n.reason} className="mut">{n.reason}</td>
                  <td className="mut">{n.lab}</td>
                  <td><a href={n.source_url} target="_blank" rel="noreferrer">pdf</a></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <Pager meta={r.data?.meta} page={page} setPage={setPage} />
      </Panel>
      <Panel title="Repeat offenders" sub="NSQ listings by marketer">
        {offenders.map((o) => <Bar key={o.slug} label={o.name} to={`/co/${o.slug}`} value={o.n} max={offenders[0]?.n ?? 1} text={`${o.n} · ${o.latest}`} />)}
      </Panel>
    </div>
  );
}

function BansTab() {
  const [q, setQ] = useState("");
  const [sel, setSel] = useState<number | null>(null);
  const [page, setPage] = useState(1);
  const r = useQuery({ queryKey: ["bans", q, page], queryFn: () => get("/reg/bans", { q, page, limit: 80 }) });
  const prods = useQuery({ queryKey: ["ban-products", sel], queryFn: () => get(`/reg/bans/${sel}/products`), enabled: sel != null });
  return (
    <div className="grid cols-2">
      <Panel title="Prohibited & restricted FDCs" sub="Section 26A, Drugs & Cosmetics Act — every notification since 1983"
        right={<a href={csvUrl("/reg/bans", { q })}>CSV ⤓</a>}>
        <div className="filterbar inline"><input placeholder="search combination" value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} /></div>
        <table className="tt">
          <thead><tr><th>Combination</th><th>Notification</th><th>Date</th><th>Status</th><th className="num">SKUs hit</th><th className="num">Check</th></tr></thead>
          <tbody>
            {r.data?.data.map((b: Row) => (
              <tr key={b.id} className={sel === b.id ? "sel" : ""} onClick={() => setSel(b.id)}>
                <td title={b.combo_text} style={{ maxWidth: 380 }}>{b.combo_text}</td>
                <td className="mut">{b.notification}</td>
                <td>{day(b.notified_on)}</td>
                <td><span className={`badge ${b.status === "banned" ? "b-down" : "b-warn"}`}>{b.status}</span></td>
                <td className={`num ${b.catalog_skus ? "neg" : "mut"}`}>{num(b.catalog_skus)}</td>
                <td className="num mut">{num(b.review_skus)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <Pager meta={r.data?.meta} page={page} setPage={setPage} />
      </Panel>
      <Panel title="Catalog SKUs matching the selected notification" sub="matched on molecules + stated strength + dosage form">
        {sel == null ? <Empty>select a notification</Empty> : prods.isLoading ? <Loading /> : (
          <>
            {prods.data?.ban && <div className="note">{prods.data.ban.combo_text} — {prods.data.ban.notification} <a href={prods.data.ban.source_url} target="_blank" rel="noreferrer">source pdf</a></div>}
            {!prods.data?.data.length ? <Empty>No catalog SKU matches this notification's composition/strength/form.</Empty> : (
              <table className="tt">
                <thead><tr><th>SKU</th><th>Form</th><th>Marketer</th><th className="num">MRP</th><th>Match</th><th>Status</th></tr></thead>
                <tbody>
                  {prods.data.data.map((p: Row) => (
                    <tr key={p.id}>
                      <td><Link to={`/p/${p.id}`}>{p.name}</Link></td>
                      <td className="mut">{p.dosage_form}</td>
                      <td>{p.company_slug ? <Link to={`/co/${p.company_slug}`}>{p.company}</Link> : p.company}</td>
                      <td className="num">{inr(p.mrp)}</td>
                      <td><span className={`badge ${p.ban_level === "exact" ? "b-down" : "b-warn"}`}>{p.ban_level === "exact" ? "match" : "check pack"}</span></td>
                      <td className="mut">{p.is_discontinued ? "discontinued" : p.in_stock ? "in stock (2025)" : ""}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </>
        )}
        <div className="faint" style={{ marginTop: 8 }}>Court stays obtained by individual manufacturers are not tracked; always confirm against the notification.</div>
      </Panel>
    </div>
  );
}

function DocsTab() {
  const [agency, setAgency] = useState("");
  const [type, setType] = useState("");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const r = useQuery({ queryKey: ["docs", agency, type, q, page], queryFn: () => get("/reg/documents", { agency, doc_type: type, q, page, limit: 60 }) });
  return (
    <Panel title="Regulator documents" sub="CDSCO gazette · alerts · circulars · public notices · NPPA orders & Authority minutes">
      <div className="filterbar inline">
        <input placeholder="search title" value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} />
        <select value={`${agency}|${type}`} onChange={(e) => { const [a, t] = e.target.value.split("|"); setAgency(a); setType(t); setPage(1); }}>
          <option value="|">all types</option>
          {r.data?.types?.map((t: Row) => <option key={t.agency + t.doc_type} value={`${t.agency}|${t.doc_type}`}>{t.agency} · {t.doc_type} ({t.n})</option>)}
        </select>
      </div>
      <table className="tt">
        <thead><tr><th>Date</th><th>Agency</th><th>Type</th><th>Title</th><th /></tr></thead>
        <tbody>
          {r.data?.data.map((d: Row) => (
            <tr key={d.id}><td>{day(d.published_on)}</td><td className="amb">{d.agency}</td><td className="mut">{d.doc_type}</td>
              <td title={d.title} style={{ maxWidth: 800 }}>{d.title}</td><td><a href={d.url} target="_blank" rel="noreferrer">open</a></td></tr>
          ))}
        </tbody>
      </table>
      <Pager meta={r.data?.meta} page={page} setPage={setPage} />
    </Panel>
  );
}

function UsfdaTab() {
  const [page, setPage] = useState(1);
  const r = useQuery({ queryKey: ["usfda", page], queryFn: () => get("/reg/usfda", { page, limit: 60 }) });
  return (
    <Panel title="US FDA recalls of India-made drugs" sub="openFDA enforcement reports">
      <table className="tt">
        <thead><tr><th>Date</th><th>Firm</th><th>Group</th><th>Detail</th></tr></thead>
        <tbody>
          {r.data?.data.map((u: Row) => (
            <tr key={u.id}><td>{day(u.issued_on)}</td><td>{u.firm}</td>
              <td>{u.parent_slug ? <Link to={`/g/${u.parent_slug}`}>{u.parent}</Link> : <span className="mut">—</span>}</td>
              <td title={u.subject} style={{ maxWidth: 820 }} className={u.subject?.startsWith("Class I:") ? "neg" : ""}>{u.subject}</td></tr>
          ))}
        </tbody>
      </table>
      <Pager meta={r.data?.meta} page={page} setPage={setPage} />
    </Panel>
  );
}

function JaTab() {
  const [q, setQ] = useState("");
  const [group, setGroup] = useState("");
  const [page, setPage] = useState(1);
  const r = useQuery({ queryKey: ["ja", q, group, page], queryFn: () => get("/reg/jan-aushadhi", { q, group, page, limit: 80 }) });
  return (
    <Panel title="PMBI Jan Aushadhi product & MRP list" sub="official generic prices — the floor for any brand comparison">
      <div className="filterbar inline">
        <input placeholder="generic name" value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} />
        <select value={group} onChange={(e) => { setGroup(e.target.value); setPage(1); }}>
          <option value="">all groups</option>
          {r.data?.groups?.map((g: Row) => <option key={g.group_name} value={g.group_name}>{g.group_name} ({g.n})</option>)}
        </select>
      </div>
      <table className="tt">
        <thead><tr><th>Code</th><th>Generic</th><th>Unit</th><th className="num">MRP</th><th>Group</th></tr></thead>
        <tbody>{r.data?.data.map((j: Row) => <tr key={j.drug_code}><td className="mut">{j.drug_code}</td><td>{j.name}</td><td>{j.unit_size}</td><td className="num amb">{inr(j.mrp)}</td><td className="mut">{j.group_name}</td></tr>)}</tbody>
      </table>
      <Pager meta={r.data?.meta} page={page} setPage={setPage} />
    </Panel>
  );
}

function CeilingTab() {
  const [q, setQ] = useState("");
  const r = useQuery({ queryKey: ["ceiling", q], queryFn: () => get("/reg/nppa-ceiling", { q, limit: 500 }) });
  return (
    <Panel title="NPPA ceiling prices (DPCO 2013 scheduled formulations)" sub="statutory maximum price per unit">
      <div className="filterbar inline"><input placeholder="molecule" value={q} onChange={(e) => setQ(e.target.value)} /></div>
      <table className="tt">
        <thead><tr><th>Molecule</th><th>Form / strength</th><th className="num">Ceiling</th><th>Unit</th><th>Notification</th><th>Year</th><th className="num">Catalog SKUs</th></tr></thead>
        <tbody>{r.data?.data.map((c: Row) => (
          <tr key={c.id}><td>{c.molecule_id ? <Link to={`/m/${c.molecule_id}`}>{c.molecule_name}</Link> : c.molecule_name}</td><td className="mut">{c.form_strength}</td>
            <td className="num amb">{inr(c.ceiling_price)}</td><td className="mut">{c.unit}</td><td className="mut">{c.notification}</td><td>{c.year}</td><td className="num">{num(c.product_count)}</td></tr>
        ))}</tbody>
      </table>
    </Panel>
  );
}

function ShortageTab() {
  const r = useQuery({ queryKey: ["shortages"], queryFn: () => get("/reg/shortages", { limit: 500 }) });
  return (
    <Panel title="Shortage signals" sub="US FDA shortage list (API supply-chain risk for Indian exporters); Indian shortage news is in NEWS › supply">
      <table className="tt">
        <thead><tr><th>Region</th><th>Product</th><th>Company</th><th>Status</th><th>Category</th><th>Updated</th></tr></thead>
        <tbody>{r.data?.data.map((s: Row) => <tr key={s.id}><td>{s.region}</td><td title={s.molecule_text}>{s.molecule_text}</td><td className="mut">{s.company}</td><td>{s.status}</td><td className="mut">{s.category}</td><td>{day(s.updated_on)}</td></tr>)}</tbody>
      </table>
    </Panel>
  );
}
