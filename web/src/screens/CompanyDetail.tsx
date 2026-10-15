import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { api, inr, num } from "../lib/api";

export default function CompanyDetail() {
  const { slug } = useParams();
  const [page, setPage] = useState(1);
  const comp = useQuery({ queryKey: ["company", slug, page], queryFn: () => api.company(slug!, page) });

  if (comp.isLoading) return <div className="loading">loading issuer…</div>;
  if (comp.isError || !comp.data) return <div className="err">not found</div>;
  const c = comp.data;
  const s = c.stats;
  const maxBand = Math.max(...c.price_bands.map((b) => b.count), 1);

  return (
    <>
      <div className="detail-head">
        <div>
          <div className="detail-title">{c.company.name}</div>
          <div className="faint">
            ISSUER · {num(s.products)} PRODUCTS · {num(s.molecules)} MOLECULES · {s.flagged > 0 ? (
              <span style={{ color: "var(--down)" }}>{s.flagged} FLAGGED</span>
            ) : (
              "no flags"
            )}
          </div>
        </div>
        <div style={{ marginLeft: "auto", display: "flex", gap: 22, textAlign: "right" }}>
          <Stat label="Median MRP" value={inr(s.median_mrp)} color="var(--amber)" />
          <Stat label="Avg Rating" value={s.avg_rating?.toFixed(2) ?? "—"} />
          <Stat label="Reviewed" value={`${Math.round((s.reviewed / Math.max(s.products, 1)) * 100)}%`} />
        </div>
      </div>

      <div className="grid cols-3">
        <section className="panel">
          <div className="panel-head"><span>Price Bands</span></div>
          <div className="panel-body">
            {c.price_bands.map((b) => (
              <div className="bar-row" key={b.band}>
                <span className="bar-label">{b.band}</span>
                <span className="bar-track"><span className="bar-fill cyan" style={{ width: `${(b.count / maxBand) * 100}%` }} /></span>
                <span className="bar-val">{num(b.count)}</span>
              </div>
            ))}
          </div>
        </section>

        <section className="panel">
          <div className="panel-head"><span>Therapy Mix</span></div>
          <div className="panel-body">
            {c.top_categories.map((t) => (
              <div className="bar-row" key={t.category}>
                <span className="bar-label">{t.category}</span>
                <span className="bar-track"><span className="bar-fill" style={{ width: `${(t.count / c.top_categories[0].count) * 100}%` }} /></span>
                <span className="bar-val">{t.count}</span>
              </div>
            ))}
          </div>
        </section>

        <section className="panel">
          <div className="panel-head"><span>Facts</span></div>
          <div className="panel-body" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
            <Fact k="Products" v={num(s.products)} />
            <Fact k="Molecules" v={num(s.molecules)} />
            <Fact k="Categories" v={num(s.categories)} />
            <Fact k="Min MRP" v={inr(s.min_mrp)} />
            <Fact k="Max MRP" v={inr(s.max_mrp)} />
            <Fact k="Avg MRP" v={inr(s.avg_mrp)} />
          </div>
        </section>
      </div>

      <div style={{ height: 10 }} />

      <section className="panel">
        <div className="panel-head"><span>Portfolio</span><span className="sub">page {page}</span></div>
        <div className="panel-body" style={{ padding: 0 }}>
          <table className="tt">
            <thead><tr><th>Product</th><th>Molecule</th><th>Category</th><th className="num">MRP</th><th className="num">Rating</th></tr></thead>
            <tbody>
              {c.portfolio.map((p) => (
                <tr key={p.id}>
                  <td><Link to={`/drugs/${p.id}`}>{p.name}</Link></td>
                  <td className="mut">{p.salt}</td>
                  <td className="mut">{p.category}</td>
                  <td className="num">{inr(p.mrp)}</td>
                  <td className="num mut">{p.rating ? p.rating.toFixed(1) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <div style={{ padding: "8px 2px", display: "flex", gap: 8 }}>
        <button disabled={page <= 1} onClick={() => setPage(page - 1)}>◀ PREV</button>
        <button disabled={c.portfolio.length < 50} onClick={() => setPage(page + 1)}>NEXT ▶</button>
      </div>
    </>
  );
}

function Stat({ label, value, color }: { label: string; value?: string; color?: string }) {
  return (
    <div>
      <div style={{ fontSize: 16, fontWeight: 600, color: color ?? "var(--text)" }}>{value ?? "—"}</div>
      <div className="faint">{label}</div>
    </div>
  );
}

function Fact({ k, v }: { k: string; v: string }) {
  return (
    <div>
      <div className="faint">{k.toUpperCase()}</div>
      <div>{v}</div>
    </div>
  );
}
