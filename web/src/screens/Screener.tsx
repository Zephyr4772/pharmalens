import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { csvUrl, get, inr, num, type Row } from "../lib/api";
import { ErrorBox, Loading, Pager, Panel, Star, Csv } from "../components/ui";

export function ProductTable({ rows, showCompany = true }: { rows: Row[]; showCompany?: boolean }) {
  const nav = useNavigate();
  return (
    <table className="tt">
      <thead><tr><th /><th>Brand / SKU</th><th>Composition</th><th>Form</th>{showCompany && <th>Marketer</th>}{showCompany && <th>Group</th>}
        <th className="num">MRP</th><th className="num">₹/unit</th><th>Pack</th><th>As of</th><th>Flags</th></tr></thead>
      <tbody>
        {rows.map((p) => (
          <tr key={p.id} onClick={() => nav(`/p/${p.id}`)}>
            <td><Star k={`p:${p.id}`} label={p.name} href={`/p/${p.id}`} /></td>
            <td>{p.name}</td>
            <td className="mut" title={p.composition}>{p.composition}</td>
            <td className="mut">{p.dosage_form}</td>
            {showCompany && <td onClick={(e) => e.stopPropagation()}>{p.company_slug ? <Link to={`/co/${p.company_slug}`}>{p.company}</Link> : "—"}</td>}
            {showCompany && <td onClick={(e) => e.stopPropagation()}>{p.parent_slug ? <Link to={`/g/${p.parent_slug}`}>{p.parent}</Link> : <span className="faint">—</span>}</td>}
            <td className="num amb">{inr(p.mrp)}</td>
            <td className="num">{p.unit_price != null ? p.unit_price.toFixed(2) : "—"}</td>
            <td className="mut">{p.pack_size}</td>
            <td className="faint">{p.mrp_asof}</td>
            <td>
              {p.ban_level === "exact" && <span className="badge b-down">BANNED</span>}
              {p.ban_level === "review" && <span className="badge b-warn">BAN?</span>}
              {p.is_discontinued && <span className="badge b-mute">DISC</span>}
              {p.in_stock === false && <span className="badge b-mute">OOS</span>}
              {p.rx_required && <span className="chip">Rx</span>}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default function Screener() {
  const [sp, setSp] = useSearchParams();
  const f = Object.fromEntries(sp.entries());
  const page = Number(f.page || 1);
  const meta = useQuery({ queryKey: ["classes"], queryFn: () => get("/market/classes"), staleTime: 3600_000 });
  const params = { ...f, page, limit: 60 };
  const r = useQuery({ queryKey: ["products", params], queryFn: () => get("/products", params) });
  const set = (k: string, v: string) => { const n = { ...f, [k]: v, page: "1" }; if (!v) delete n[k]; setSp(n); };
  const [q, setQ] = useState(f.q ?? "");
  return (
    <div className="stack">
      <div className="filterbar">
        <label>search</label>
        <input value={q} placeholder="brand name" onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === "Enter" && set("q", q)} />
        <label>class</label>
        <select value={f.therapeutic_class ?? ""} onChange={(e) => set("therapeutic_class", e.target.value)}>
          <option value="">all</option>{meta.data?.data.map((c: string) => <option key={c}>{c}</option>)}
        </select>
        <label>form</label>
        <select value={f.dosage_form ?? ""} onChange={(e) => set("dosage_form", e.target.value)}>
          <option value="">all</option>{meta.data?.forms.map((c: string) => <option key={c}>{c}</option>)}
        </select>
        <label>type</label>
        <select value={f.mono ?? ""} onChange={(e) => set("mono", e.target.value)}>
          <option value="">single + FDC</option><option value="true">single molecule</option><option value="false">FDC</option>
        </select>
        <label>MRP</label>
        <input type="number" placeholder="min" value={f.min_mrp ?? ""} onChange={(e) => set("min_mrp", e.target.value)} />
        <input type="number" placeholder="max" value={f.max_mrp ?? ""} onChange={(e) => set("max_mrp", e.target.value)} />
        <label>status</label>
        <select value={f.banned ?? f.in_stock ?? ""} onChange={(e) => {
          const v = e.target.value; const n = { ...f, page: "1" } as Record<string, string>; delete n.banned; delete n.in_stock;
          if (v === "banned") n.banned = "true"; if (v === "in") n.in_stock = "true"; setSp(n);
        }}>
          <option value="">any</option><option value="banned">matches a ban</option><option value="in">in stock (2025)</option>
        </select>
        <label><input type="checkbox" checked={f.active_only === "true"} onChange={(e) => set("active_only", e.target.checked ? "true" : "")} /> active only</label>
        <label>sort</label>
        <select value={f.sort ?? "reach"} onChange={(e) => set("sort", e.target.value)}>
          <option value="reach">market reach</option><option value="mrp_asc">MRP ↑</option><option value="mrp_desc">MRP ↓</option>
          <option value="unit_asc">₹/unit ↑</option><option value="unit_desc">₹/unit ↓</option><option value="name">name</option>
        </select>
        <span className="spacer" />
        <Csv href={csvUrl("/products", f)} />
      </div>
      <Panel title="Product screener" sub={r.data ? `${num(r.data.meta.total)} SKUs · ${r.data.took_ms}ms` : ""}>
        {r.isLoading ? <Loading /> : r.error ? <ErrorBox e={r.error} /> : <ProductTable rows={r.data.data} />}
        <Pager meta={r.data?.meta} page={page} setPage={(p) => setSp({ ...f, page: String(p) })} />
      </Panel>
    </div>
  );
}
