import { useEffect, useState } from "react";
import { useQuery, keepPreviousData } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, num } from "../lib/api";

export default function Molecules() {
  const [term, setTerm] = useState("");
  const [debounced, setDebounced] = useState("");
  const [sort, setSort] = useState("brands_desc");
  const [page, setPage] = useState(1);

  useEffect(() => {
    const t = setTimeout(() => {
      setDebounced(term);
      setPage(1);
    }, 250);
    return () => clearTimeout(t);
  }, [term]);

  const res = useQuery({
    queryKey: ["molecules", { debounced, sort, page }],
    queryFn: () => api.molecules({ q: debounced, sort, page, size: 60 }),
    placeholderData: keepPreviousData,
  });

  return (
    <>
      <div className="filterbar">
        <label>Molecule</label>
        <input style={{ width: 280 }} value={term} onChange={(e) => setTerm(e.target.value)} placeholder="salt composition…" />
        <label>Sort</label>
        <select value={sort} onChange={(e) => { setSort(e.target.value); setPage(1); }}>
          <option value="brands_desc">BRANDS ↓</option>
          <option value="spread_desc">SPREAD ↓</option>
          <option value="name_asc">NAME A-Z</option>
        </select>
        <span className="faint" style={{ marginLeft: "auto" }}>{res.data ? `${num(res.data.meta.total)} molecules` : "…"}</span>
      </div>

      <section className="panel" style={{ borderTop: "none" }}>
        <div className="panel-body" style={{ padding: 0 }}>
          <table className="tt">
            <thead>
              <tr>
                <th>Molecule</th>
                <th className="num">Brands</th>
                <th className="num">Floor</th>
                <th className="num">Median</th>
                <th className="num">Ceiling</th>
                <th className="num">Spread</th>
              </tr>
            </thead>
            <tbody>
              {(res.data?.data ?? []).map((m) => (
                <tr key={m.id}>
                  <td><Link to={`/molecules/${m.id}`}>{m.comp}</Link></td>
                  <td className="num mut">{m.brands}</td>
                  <td className="num pos">{m.cheapest != null ? "₹" + m.cheapest.toFixed(2) : "—"}</td>
                  <td className="num">{m.avg_mrp != null ? "₹" + m.avg_mrp.toFixed(0) : "—"}</td>
                  <td className="num">{m.priciest != null ? "₹" + m.priciest.toFixed(2) : "—"}</td>
                  <td className={"num " + ((m.spread_pct ?? 0) > 80 ? "amb" : "")}>{m.spread_pct ?? "—"}%</td>
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
