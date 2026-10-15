import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { crore, get, num, signed, type Row } from "../lib/api";
import { Loading, Pager, Panel, Star, Tabs, useSort } from "../components/ui";

type Mode = "groups" | "companies";

export default function Groups() {
  const nav = useNavigate();
  const [mode, setMode] = useState<Mode>("groups");
  const [q, setQ] = useState("");
  const [sort, setSort] = useState("products");
  const [page, setPage] = useState(1);
  const groups = useQuery({ queryKey: ["parents"], queryFn: () => get("/parents") });
  const comps = useQuery({ queryKey: ["companies", q, sort, page], enabled: mode === "companies", queryFn: () => get("/companies", { q, sort, page, limit: 80 }) });
  const { sorted, th } = useSort(groups.data?.data, "products");
  return (
    <div className="stack">
      <Tabs<Mode> value={mode} onChange={setMode} tabs={[["groups", "PHARMA GROUPS (consolidated)"], ["companies", "ALL MARKETERS / MANUFACTURERS"]]} />
      {mode === "groups" ? (
        <Panel title="Corporate groups" sub="subsidiaries and acquired brand houses rolled up (e.g. Sun = Sun Pharma + Sun Pharma Labs + Ranbaxy)">
          {groups.isLoading ? <Loading /> : (
            <table className="tt">
              <thead><tr><th />{th("name", "Group")}{th("ticker", "NSE")}{th("ownership", "Ownership")}{th("products", "SKUs", "num")}{th("active", "Active", "num")}
                {th("companies", "Entities", "num")}{th("price", "Price", "num")}{th("change_pct", "Chg", "num")}{th("market_cap", "Mkt cap", "num")}{th("nsq_count", "NSQ", "num")}{th("usfda_count", "USFDA", "num")}</tr></thead>
              <tbody>{sorted.map((g: Row) => (
                <tr key={g.id} onClick={() => nav(`/g/${g.slug}`)}>
                  <td><Star k={`g:${g.slug}`} label={g.name} href={`/g/${g.slug}`} /></td>
                  <td>{g.name}</td><td className="amb">{g.ticker ?? ""}</td><td className="mut">{g.ownership?.replace("_", " ")}</td>
                  <td className="num">{num(g.products)}</td><td className="num">{num(g.active)}</td><td className="num">{num(g.companies)}</td>
                  <td className="num">{g.price ? g.price.toLocaleString("en-IN", { maximumFractionDigits: 1 }) : "—"}</td>
                  <td className={`num ${g.change_pct >= 0 ? "pos" : "neg"}`}>{g.change_pct != null ? signed(g.change_pct) : ""}</td>
                  <td className="num">{g.market_cap ? crore(g.market_cap) : "—"}</td>
                  <td className={`num ${g.nsq_count ? "neg" : "mut"}`}>{num(g.nsq_count)}</td><td className={`num ${g.usfda_count ? "neg" : "mut"}`}>{num(g.usfda_count)}</td>
                </tr>
              ))}</tbody>
            </table>
          )}
        </Panel>
      ) : (
        <>
          <div className="filterbar">
            <label>search</label><input value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} placeholder="company name" />
            <label>sort</label>
            <select value={sort} onChange={(e) => setSort(e.target.value)}>
              <option value="products">SKUs</option><option value="molecules">molecules</option><option value="median">median MRP</option><option value="name">name</option>
            </select>
          </div>
          <Panel title="Marketers & manufacturers" sub={comps.data ? `${num(comps.data.meta.total)} companies` : ""}>
            {comps.isLoading ? <Loading /> : (
              <table className="tt">
                <thead><tr><th /><th>Company</th><th>Group</th><th className="num">SKUs</th><th className="num">Active</th><th className="num">Molecules</th><th className="num">Median MRP</th><th>Main therapy</th><th className="num">NSQ</th></tr></thead>
                <tbody>{comps.data?.data.map((c: Row) => (
                  <tr key={c.id} onClick={() => nav(`/co/${c.slug}`)}>
                    <td><Star k={`co:${c.slug}`} label={c.name} href={`/co/${c.slug}`} /></td>
                    <td>{c.name}</td><td className="mut">{c.parent ?? ""}</td><td className="num">{num(c.product_count)}</td><td className="num">{num(c.active_count)}</td>
                    <td className="num">{num(c.molecule_count)}</td><td className="num amb">₹{c.median_mrp?.toFixed(0) ?? "—"}</td><td className="mut">{c.top_class}</td>
                    <td className={`num ${c.nsq_count ? "neg" : "mut"}`}>{num(c.nsq_count)}</td>
                  </tr>
                ))}</tbody>
              </table>
            )}
            <Pager meta={comps.data?.meta} page={page} setPage={setPage} />
          </Panel>
        </>
      )}
    </div>
  );
}
