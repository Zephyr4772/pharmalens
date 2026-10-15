import { useEffect, useState } from "react";
import { useQuery, keepPreviousData } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, inr, num } from "../lib/api";

export default function Companies() {
  const [term, setTerm] = useState("");
  const [debounced, setDebounced] = useState("");
  const [sort, setSort] = useState("products_desc");
  const [page, setPage] = useState(1);

  useEffect(() => {
    const t = setTimeout(() => {
      setDebounced(term);
      setPage(1);
    }, 250);
    return () => clearTimeout(t);
  }, [term]);

  const res = useQuery({
    queryKey: ["companies", { debounced, sort, page }],
    queryFn: () => api.companies({ q: debounced, sort, page, size: 60 }),
    placeholderData: keepPreviousData,
  });

  return (
    <>
      <div className="filterbar">
        <label>Issuer</label>
        <input style={{ width: 280 }} value={term} onChange={(e) => setTerm(e.target.value)} placeholder="company name…" />
        <label>Sort</label>
        <select value={sort} onChange={(e) => { setSort(e.target.value); setPage(1); }}>
          <option value="products_desc">PORTFOLIO ↓</option>
          <option value="avg_price_desc">AVG MRP ↓</option>
          <option value="avg_price_asc">AVG MRP ↑</option>
          <option value="name_asc">NAME A-Z</option>
        </select>
        <span className="faint" style={{ marginLeft: "auto" }}>{res.data ? `${num(res.data.meta.total)} issuers` : "…"}</span>
      </div>

      <section className="panel" style={{ borderTop: "none" }}>
        <div className="panel-body" style={{ padding: 0 }}>
          <table className="tt">
            <thead>
              <tr>
                <th>Company</th>
                <th className="num">Products</th>
                <th className="num">Molecules</th>
                <th>Top Therapy</th>
                <th className="num">Avg MRP</th>
                <th className="num">Min</th>
                <th className="num">Max</th>
                <th className="num">Rating</th>
              </tr>
            </thead>
            <tbody>
              {(res.data?.data ?? []).map((c) => (
                <tr key={c.id}>
                  <td><Link to={`/companies/${c.slug}`}>{c.name}</Link></td>
                  <td className="num">{num(c.products)}</td>
                  <td className="num mut">{num(c.molecules)}</td>
                  <td className="mut">{c.top_category}</td>
                  <td className="num">{inr(c.avg_mrp)}</td>
                  <td className="num pos">{inr(c.min_mrp)}</td>
                  <td className="num">{inr(c.max_mrp)}</td>
                  <td className="num mut">{c.avg_rating?.toFixed(2) ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <div style={{ padding: "8px 2px", display: "flex", gap: 8, alignItems: "center" }}>
        <button disabled={page <= 1} onClick={() => setPage(page - 1)}>◀ PREV</button>
        <span className="mut">PAGE {res.data?.meta.page ?? "-"} / {res.data?.meta.pages ?? "-"}</span>
        <button disabled={(res.data?.meta.pages ?? 1) <= page} onClick={() => setPage(page + 1)}>NEXT ▶</button>
      </div>
    </>
  );
}
