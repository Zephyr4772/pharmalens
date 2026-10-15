import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { api, inr, num, pct } from "../lib/api";

function Panel({ title, sub, children, className }: { title: string; sub?: string; children: React.ReactNode; className?: string }) {
  return (
    <section className={"panel " + (className ?? "")}>
      <div className="panel-head">
        <span>{title}</span>
        {sub && <span className="sub">{sub}</span>}
      </div>
      <div className="panel-body">{children}</div>
    </section>
  );
}

function BarList({ rows, color }: { rows: { label: string; value: number; display: string; to?: string }[]; color?: string }) {
  const max = Math.max(...rows.map((r) => r.value), 1);
  return (
    <div>
      {rows.map((r) => (
        <div className="bar-row" key={r.label}>
          <span className="bar-label">{r.to ? <Link to={r.to}>{r.label}</Link> : r.label}</span>
          <span className="bar-track">
            <span className={"bar-fill " + (color ?? "")} style={{ width: `${(r.value / max) * 100}%` }} />
          </span>
          <span className="bar-val">{r.display}</span>
        </div>
      ))}
    </div>
  );
}

function Histogram({ data }: { data: { band: string; count: number }[] }) {
  const max = Math.max(...data.map((d) => d.count), 1);
  return (
    <div className="hist">
      {data.map((d) => (
        <div className="hist-col" key={d.band} title={`${d.band}: ${num(d.count)}`}>
          <span className="hist-y">{d.count > max * 0.25 ? num(d.count) : ""}</span>
          <div className="hist-bar" style={{ height: `${(d.count / max) * 100}%` }} />
          <span className="hist-x">{d.band}</span>
        </div>
      ))}
    </div>
  );
}

export default function Market() {
  const nav = useNavigate();
  const ov = useQuery({ queryKey: ["overview"], queryFn: api.overview });
  const arb = useQuery({ queryKey: ["arbitrage", 15], queryFn: () => api.arbitrage(15) });
  const prem = useQuery({ queryKey: ["premium"], queryFn: () => api.premium(10) });

  if (ov.isLoading) return <div className="loading">loading market feed…</div>;
  if (ov.isError || !ov.data) return <div className="err">feed unavailable — is the API on :8000?</div>;
  const k = ov.data.kpis;

  return (
    <>
      <div className="kpis">
        <Kpi label="Products" value={num(k.drugs)} sub={`${k.price_coverage_pct}% priced`} amber />
        <Kpi label="Companies" value={num(k.companies)} sub="manufacturers" />
        <Kpi label="Molecules" value={num(k.molecules)} sub="salt compositions" />
        <Kpi label="Median MRP" value={inr(k.median_mrp)} sub={`avg ${inr(k.avg_mrp)}`} />
        <Kpi label="Avg Rating" value={k.avg_rating?.toFixed(2) ?? "—"} sub={`${k.review_coverage_pct}% reviewed`} />
        <Kpi label="NSQ Alerts" value={String(k.nsq_alerts)} sub="CDSCO batch failures" warn />
        <Kpi label="Max MRP" value={inr(k.max_mrp)} sub={`min ${inr(k.min_mrp)}`} />
      </div>

      <div className="grid cols-3">
        <Panel title="Price Distribution" sub="MRP bands · all products">
          <Histogram data={ov.data.price_histogram} />
        </Panel>
        <Panel title="Top Categories" sub="by product count">
          <BarList
            rows={ov.data.top_categories.slice(0, 9).map((c) => ({
              label: c.category,
              value: c.count,
              display: num(c.count),
            }))}
          />
        </Panel>
        <Panel title="Top Companies" sub="by portfolio size">
          <BarList
            color="cyan"
            rows={ov.data.top_companies.slice(0, 9).map((c) => ({
              label: c.name,
              value: c.products,
              display: num(c.products),
              to: `/companies/${c.slug}`,
            }))}
          />
        </Panel>
      </div>

      <div style={{ height: 10 }} />

      <div className="grid cols-2">
        <Panel title="Arbitrage Leaders" sub="max generic-vs-brand spread">
          <table className="tt">
            <thead>
              <tr>
                <th>Molecule</th>
                <th className="num">Brands</th>
                <th className="num">Floor</th>
                <th className="num">Ceiling</th>
                <th>Ceiling Brand</th>
                <th className="num">Spread</th>
              </tr>
            </thead>
            <tbody>
              {(arb.data?.data ?? []).map((r) => (
                <tr key={r.salt.id} onClick={() => nav(`/molecules/${r.salt.id}`)}>
                  <td>{r.salt.comp}</td>
                  <td className="num mut">{r.brands}</td>
                  <td className="num pos">{inr(r.cheapest)}</td>
                  <td className="num">{inr(r.priciest)}</td>
                  <td className="mut">{r.priciest_brand.name}</td>
                  <td className="num amb">−{pct(r.savings_pct)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>

        <Panel title="Premium Desk" sub="high-MRP products · review-weighted">
          <table className="tt">
            <thead>
              <tr>
                <th>Product</th>
                <th>Molecule</th>
                <th className="num">MRP</th>
                <th className="num">Generic From</th>
                <th className="num">Rating</th>
              </tr>
            </thead>
            <tbody>
              {(prem.data?.data as { name: string; salt: string; mrp: number; generic_from: number; rating: number }[] ?? []).map(
                (r) => (
                  <tr key={r.name}>
                    <td>{r.name}</td>
                    <td className="mut">{r.salt}</td>
                    <td className="num">{inr(r.mrp)}</td>
                    <td className="num pos">{inr(r.generic_from)}</td>
                    <td className="num mut">{r.rating?.toFixed(1)}</td>
                  </tr>
                )
              )}
            </tbody>
          </table>
        </Panel>
      </div>
    </>
  );
}

function Kpi({ label, value, sub, amber, warn }: { label: string; value: string; sub?: string; amber?: boolean; warn?: boolean }) {
  return (
    <div className="kpi" style={warn ? { borderTopColor: "var(--warn)" } : undefined}>
      <div className="k-label">{label}</div>
      <div className={"k-value" + (amber ? " amber" : "")}>{value}</div>
      {sub && <div className="k-sub">{sub}</div>}
    </div>
  );
}
