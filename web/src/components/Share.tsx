import { Link } from "react-router-dom";
import { hhiLabel, num, share, type Row } from "../lib/api";

export function ShareTable({ rows, stats }: { rows: Row[]; stats?: Row | null }) {
  if (!rows?.length) return <div className="empty">no priced SKUs in this segment</div>;
  const max = rows[0]?.value_share ?? 1;
  return (
    <>
      {stats && (
        <div className="note">
          {num(stats.owners)} marketers · {num(stats.skus)} active SKUs · HHI <b>{num(stats.hhi)}</b> ({hhiLabel(stats.hhi)})
        </div>
      )}
      <table className="tt">
        <thead><tr><th>#</th><th>Group / company</th><th className="num">SKUs</th><th>Est. value share</th><th className="num">SKU share</th></tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.owner_type + r.owner_id}>
              <td className="mut">{r.rank}</td>
              <td>
                <Link to={r.owner_type === "parent" ? `/g/${r.slug}` : `/co/${r.slug}`}>{r.name}</Link>
                {r.owner_type === "parent" && <span className="chip">GROUP{r.ticker ? ` · ${r.ticker}` : ""}</span>}
              </td>
              <td className="num">{num(r.skus)}</td>
              <td style={{ minWidth: 160 }}>
                <span className="inline-bar"><span style={{ width: `${(r.value_share / max) * 100}%` }} /></span>
                <span className="amb"> {share(r.value_share)}</span>
              </td>
              <td className="num mut">{share(r.breadth_share)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
