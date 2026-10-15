import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, inr } from "../lib/api";
import { useWatchlist } from "../state/watchlist";

export default function Watchlist() {
  const watch = useWatchlist();
  const ids = watch.ids;

  const queries = useQuery({
    queryKey: ["watch", ids.join(",")],
    queryFn: async () => {
      const rows = await Promise.all(
        ids.map(async (id) => {
          try {
            return await api.drug(id);
          } catch {
            return null;
          }
        })
      );
      return rows.filter(Boolean);
    },
    enabled: ids.length > 0,
  });

  if (ids.length === 0)
    return (
      <div className="empty">
        watchlist empty — hit <kbd>★</kbd> in the <Link to="/screener">screener</Link> to pin securities
      </div>
    );
  if (queries.isLoading) return <div className="loading">loading pinned securities…</div>;

  const rows = (queries.data ?? []) as NonNullable<Awaited<ReturnType<typeof api.drug>>>[];

  return (
    <section className="panel">
      <div className="panel-head">
        <span>Watchlist</span>
        <button onClick={watch.clear}>CLEAR ALL</button>
      </div>
      <div className="panel-body" style={{ padding: 0 }}>
        <table className="tt">
          <thead>
            <tr><th></th><th>Product</th><th>Molecule</th><th>Maker</th><th className="num">MRP</th><th className="num">Class Floor</th><th className="num">Spread</th><th className="num">Rating</th></tr>
          </thead>
          <tbody>
            {rows.map((d) => (
              <tr key={d.id}>
                <td>
                  <span className="star on" onClick={() => watch.toggle(d.id)}>★</span>
                </td>
                <td><Link to={`/drugs/${d.id}`}>{d.name}</Link></td>
                <td className="mut"><Link to={`/molecules/${d.salt.id}`}>{d.salt.comp}</Link></td>
                <td className="mut">{d.company.name}</td>
                <td className="num">{inr(d.mrp)}</td>
                <td className="num pos">{inr(d.peer_stats?.cheapest)}</td>
                <td className="num amb">{d.peer_stats ? `${d.peer_stats.spread_pct}%` : "—"}</td>
                <td className="num mut">{d.rating?.toFixed(1) ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
