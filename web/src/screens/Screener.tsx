import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery, keepPreviousData } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { api, inr, num } from "../lib/api";
import { useWatchlist } from "../state/watchlist";

const SORTS = [
  ["relevance", "RELEVANCE"],
  ["price_asc", "PRICE ↑"],
  ["price_desc", "PRICE ↓"],
  ["rating_desc", "RATING ↓"],
  ["reviews_desc", "REVIEWS ↓"],
  ["name_asc", "NAME A-Z"],
] as const;

export default function Screener() {
  const nav = useNavigate();
  const watch = useWatchlist();
  const [term, setTerm] = useState("");
  const [debounced, setDebounced] = useState("");
  const [sort, setSort] = useState<string>("relevance");
  const [minPrice, setMinPrice] = useState("");
  const [maxPrice, setMaxPrice] = useState("");
  const [minRating, setMinRating] = useState("");
  const [page, setPage] = useState(1);
  const [cursor, setCursor] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const t = setTimeout(() => {
      setDebounced(term);
      setPage(1);
      setCursor(0);
    }, 250);
    return () => clearTimeout(t);
  }, [term]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "/" && document.activeElement?.tagName !== "INPUT") {
        e.preventDefault();
        inputRef.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const res = useQuery({
    queryKey: ["screener", { debounced, sort, minPrice, maxPrice, minRating, page }],
    queryFn: () =>
      api.drugs({
        q: debounced,
        sort,
        min_price: minPrice || undefined,
        max_price: maxPrice || undefined,
        min_rating: minRating || undefined,
        page,
        size: 100,
      }),
    placeholderData: keepPreviousData,
  });

  const rows = useMemo(() => res.data?.data ?? [], [res.data]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (document.activeElement?.tagName === "INPUT" || document.activeElement?.tagName === "SELECT") return;
      if (rows.length === 0) return;
      if (e.key === "j") setCursor((c) => Math.min(c + 1, rows.length - 1));
      if (e.key === "k") setCursor((c) => Math.max(c - 1, 0));
      if (e.key === "Enter" && rows[cursor]) nav(`/drugs/${rows[cursor].id}`);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [rows, cursor, nav]);

  const meta = res.data?.meta;

  return (
    <>
      <div className="filterbar">
        <label>Query</label>
        <input
          ref={inputRef}
          autoFocus
          style={{ width: 260 }}
          value={term}
          onChange={(e) => setTerm(e.target.value)}
          placeholder="brand or molecule…"
        />
        <label>Sort</label>
        <select value={sort} onChange={(e) => { setSort(e.target.value); setPage(1); }}>
          {SORTS.map(([v, l]) => (
            <option key={v} value={v}>{l}</option>
          ))}
        </select>
        <label>MRP ≥</label>
        <input type="number" value={minPrice} onChange={(e) => { setMinPrice(e.target.value); setPage(1); }} />
        <label>≤</label>
        <input type="number" value={maxPrice} onChange={(e) => { setMaxPrice(e.target.value); setPage(1); }} />
        <label>Rating ≥</label>
        <select value={minRating} onChange={(e) => { setMinRating(e.target.value); setPage(1); }}>
          <option value="">any</option>
          {[5, 6, 7, 8, 9].map((r) => (
            <option key={r} value={r}>{r}+</option>
          ))}
        </select>
        <span className="faint" style={{ marginLeft: "auto" }}>
          {meta ? `${num(meta.total)} matches · ${res.data?.took_ms}ms` : "…"}
          {" · "}
          <kbd>j</kbd>/<kbd>k</kbd> rows · <kbd>ENTER</kbd> open
        </span>
      </div>

      <section className="panel" style={{ borderTop: "none" }}>
        <div className="panel-body" style={{ padding: 0 }}>
          <table className="tt">
            <thead>
              <tr>
                <th style={{ width: 26 }}></th>
                <th>Product</th>
                <th>Molecule</th>
                <th>Manufacturer</th>
                <th>Category</th>
                <th className="num">MRP</th>
                <th className="num">Class Floor</th>
                <th className="num">Savings</th>
                <th className="num">Rating</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((d, i) => (
                <tr
                  key={d.id}
                  className={i === cursor ? "sel" : ""}
                  onClick={() => nav(`/drugs/${d.id}`)}
                  onMouseEnter={() => setCursor(i)}
                >
                  <td>
                    <span
                      className={"star" + (watch.ids.includes(d.id) ? " on" : "")}
                      onClick={(e) => { e.stopPropagation(); watch.toggle(d.id); }}
                    >
                      ★
                    </span>
                  </td>
                  <td>{d.name}</td>
                  <td className="mut">{d.salt.comp}</td>
                  <td>
                    <Link to={`/companies/${d.company.slug}`} onClick={(e) => e.stopPropagation()}>
                      {d.company.name}
                    </Link>
                  </td>
                  <td className="mut">{d.category}</td>
                  <td className="num">{inr(d.mrp)}</td>
                  <td className="num pos">{inr(d.class_min)}</td>
                  <td className={"num " + ((d.savings_pct ?? 0) > 50 ? "amb" : "")}>
                    {d.savings_pct != null ? `−${d.savings_pct.toFixed(0)}%` : "—"}
                  </td>
                  <td className="num mut">{d.rating ? d.rating.toFixed(1) : "—"}</td>
                </tr>
              ))}
              {rows.length === 0 && !res.isLoading && (
                <tr><td colSpan={9}><div className="empty">no products match</div></td></tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <div style={{ display: "flex", gap: 8, alignItems: "center", padding: "8px 2px" }}>
        <button disabled={(page ?? 1) <= 1} onClick={() => { setPage((p) => p - 1); setCursor(0); }}>◀ PREV</button>
        <span className="mut">
          PAGE {meta?.page ?? "-"} / {meta?.pages ?? "-"}
        </span>
        <button disabled={(page ?? 1) >= (meta?.pages ?? 1)} onClick={() => { setPage((p) => p + 1); setCursor(0); }}>NEXT ▶</button>
      </div>
    </>
  );
}
