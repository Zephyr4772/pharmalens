import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { api, inr, pct } from "../lib/api";
import { useWatchlist } from "../state/watchlist";

export default function DrugDetail() {
  const { id } = useParams();
  const watch = useWatchlist();
  const drug = useQuery({ queryKey: ["drug", id], queryFn: () => api.drug(id!) });

  if (drug.isLoading) return <div className="loading">loading security…</div>;
  if (drug.isError || !drug.data) return <div className="err">not found</div>;
  const d = drug.data;
  const starred = watch.ids.includes(d.id);

  return (
    <>
      <div className="detail-head">
        <span
          className={"star" + (starred ? " on" : "")}
          style={{ fontSize: 18, alignSelf: "center" }}
          onClick={() => watch.toggle(d.id)}
        >
          ★
        </span>
        <div>
          <div className="detail-title">{d.name}</div>
          <div className="faint">
            {d.category} ·{" "}
            <Link to={`/companies/${d.company.slug}`}>{d.company.name}</Link> ·{" "}
            <Link to={`/molecules/${d.salt.id}`}>{d.salt.display ?? d.salt.comp}</Link>
          </div>
        </div>
        <div style={{ marginLeft: "auto", textAlign: "right" }}>
          <div className="price-big">{inr(d.mrp)}</div>
          <div className="faint">MRP · PACK PRICE</div>
        </div>
        {d.peer_stats && (
          <div style={{ textAlign: "right" }}>
            <div className={"price-big " + ((d.vs_priciest_pct ?? 0) > 40 ? "pos" : "")} style={{ color: "var(--up)", fontSize: 17 }}>
              −{pct(d.vs_priciest_pct)}
            </div>
            <div className="faint">VS CEILING · #{d.peers.find((p) => p.is_subject)?.rank ?? "?"} OF {d.peer_stats.brand_count}</div>
          </div>
        )}
        <div>
          {d.rating && <span className="badge b-info">{d.rating.toFixed(1)}/10</span>}
          <span className="badge b-warn">{d.review_count} REVIEWS</span>
          {d.compliance === "flagged" && <span className="badge b-down">FLAGGED</span>}
        </div>
      </div>

      <div className="grid cols-2">
        <section className="panel">
          <div className="panel-head"><span>Class Ladder</span><span className="sub">{d.salt.comp}</span></div>
          <div className="panel-body" style={{ maxHeight: 340, padding: 0 }}>
            <table className="tt">
              <thead>
                <tr><th>#</th><th>Brand</th><th>Maker</th><th className="num">MRP</th><th className="num">Δ Floor</th></tr>
              </thead>
              <tbody>
                {(d.peers ?? []).map((p) => (
                  <tr key={p.id} className={p.is_subject ? "subject" : ""}>
                    <td className="mut">{p.rank}</td>
                    <td><Link to={`/drugs/${p.id}`}>{p.name}</Link></td>
                    <td className="mut">{p.company.name}</td>
                    <td className="num">{inr(p.mrp)}</td>
                    <td className="num pos">+{((p.mrp - d.peer_stats!.cheapest)).toFixed(0)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <div className="grid" style={{ alignContent: "start" }}>
          {d.peer_stats && (
            <Panel title="Class Stats">
              <div className="kpis" style={{ marginBottom: 0 }}>
                <Kpi label="Brands" value={String(d.peer_stats.brand_count)} />
                <Kpi label="Floor" value={inr(d.peer_stats.cheapest)} amber />
                <Kpi label="Median" value={inr(d.peer_stats.median)} />
                <Kpi label="Spread" value={`${d.peer_stats.spread_pct}%`} />
              </div>
            </Panel>
          )}
          <Panel title="Description">
            <p className="prose">{d.description ?? "—"}</p>
          </Panel>
          {d.side_effects.length > 0 && (
            <Panel title="Side Effects">
              <div>{d.side_effects.slice(0, 24).map((s) => <span className="chip" key={s}>{s}</span>)}</div>
            </Panel>
          )}
          {d.conditions.length > 0 && (
            <Panel title="Indications (patient-reported)">
              <div>{d.conditions.map((s) => <span className="chip" key={s}>{s}</span>)}</div>
            </Panel>
          )}
        </div>
      </div>

      <div style={{ height: 10 }} />

      <div className="grid cols-2">
        {d.interactions && (d.interactions.drug?.length || d.interactions.brand?.length) ? (
          <Panel title="Interaction Matrix" sub={`drugs: ${d.interactions.drug?.length ?? 0} · brands: ${d.interactions.brand?.length ?? 0}`}>
            <div className="panel-body-scroll" style={{ maxHeight: 260, overflow: "auto" }}>
              {d.interactions.drug?.slice(0, 60).map((x, i) => (
                <div key={"dg" + i} className="bar-row"><span className="bar-label">DRUG</span><span>{x}</span></div>
              ))}
              {d.interactions.brand?.slice(0, 30).map((x, i) => (
                <div key={"br" + i} className="bar-row"><span className="bar-label">BRAND</span><span>{x}</span></div>
              ))}
            </div>
          </Panel>
        ) : (
          <Panel title="Interaction Matrix"><div className="empty">no interaction data</div></Panel>
        )}

        <Panel title="Same Maker" sub={d.company.name}>
          <table className="tt">
            <thead><tr><th>Product</th><th>Molecule</th><th className="num">MRP</th></tr></thead>
            <tbody>
              {d.company_siblings.map((s) => (
                <tr key={s.id}>
                  <td><Link to={`/drugs/${s.id}`}>{s.name}</Link></td>
                  <td className="mut">{s.salt}</td>
                  <td className="num">{inr(s.mrp)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
      </div>
    </>
  );
}

function Panel({ title, sub, children }: { title: string; sub?: string; children: React.ReactNode }) {
  return (
    <section className="panel">
      <div className="panel-head">
        <span>{title}</span>
        {sub && <span className="sub">{sub}</span>}
      </div>
      <div className="panel-body">{children}</div>
    </section>
  );
}

function Kpi({ label, value, amber }: { label: string; value: string; amber?: boolean }) {
  return (
    <div className="kpi">
      <div className="k-label">{label}</div>
      <div className={"k-value" + (amber ? " amber" : "")} style={{ fontSize: 15 }}>{value}</div>
    </div>
  );
}
