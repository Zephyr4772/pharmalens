import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { api, inr } from "../lib/api";

export default function MoleculeDetail() {
  const { id } = useParams();
  const mol = useQuery({ queryKey: ["molecule", id], queryFn: () => api.molecule(id!) });

  if (mol.isLoading) return <div className="loading">loading molecule…</div>;
  if (mol.isError || !mol.data) return <div className="err">not found</div>;
  const m = mol.data;
  const s = m.stats;

  return (
    <>
      <div className="detail-head">
        <div>
          <div className="detail-title">{m.display}</div>
          <div className="faint">MOLECULE · {s?.brand_count ?? 0} BRANDS · {s?.companies ?? 0} MAKERS</div>
        </div>
        <div style={{ marginLeft: "auto", display: "flex", gap: 22, textAlign: "right" }}>
          <Stat label="Floor" value={inr(s?.cheapest)} color="var(--up)" />
          <Stat label="Median" value={inr(s?.median)} />
          <Stat label="Ceiling" value={inr(s?.priciest)} color="var(--down)" />
          <Stat label="Spread" value={`${s?.spread_pct ?? "—"}%`} color="var(--amber)" />
          <Stat label="Avg" value={inr(s?.avg)} />
        </div>
      </div>

      <section className="panel">
        <div className="panel-head"><span>Brand Ladder</span><span className="sub">price ascending · floor-to-ceiling</span></div>
        <div className="panel-body" style={{ padding: 0, maxHeight: "calc(100vh - 220px)", overflow: "auto" }}>
          <table className="tt">
            <thead>
              <tr><th>#</th><th>Brand</th><th>Maker</th><th>Price Bar</th><th className="num">MRP</th><th className="num">Δ Floor</th><th className="num">Rating</th></tr>
            </thead>
            <tbody>
              {m.ladder.map((b) => (
                <tr key={b.id}>
                  <td className="mut">{b.rank}</td>
                  <td><Link to={`/drugs/${b.id}`}>{b.name}</Link></td>
                  <td><Link to={`/companies/${b.company.slug}`} className="mut">{b.company.name}</Link></td>
                  <td style={{ minWidth: 220 }}>
                    <span className="bar-track" style={{ display: "inline-flex", width: "100%" }}>
                      <span
                        className={"bar-fill " + (b.rank === 1 ? "green" : "")}
                        style={{ width: `${Math.max(2, (b.mrp / (s?.priciest ?? b.mrp)) * 100)}%` }}
                      />
                    </span>
                  </td>
                  <td className="num">{inr(b.mrp)}</td>
                  <td className="num">+{(b.mrp - (s?.cheapest ?? b.mrp)).toFixed(0)}</td>
                  <td className="num mut">{b.rating ? b.rating.toFixed(1) : "—"}</td>
                </tr>
              ))}
              {m.ladder.length === 0 && (
                <tr><td colSpan={7}><div className="empty">no priced brands in class</div></td></tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
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
