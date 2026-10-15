import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";

export default function Alerts() {
  const res = useQuery({ queryKey: ["alerts"], queryFn: () => api.alerts({ size: 100 }) });

  if (res.isLoading) return <div className="loading">loading CDSCO feed…</div>;
  if (res.isError || !res.data) return <div className="err">feed unavailable</div>;

  return (
    <>
      <section className="panel" style={{ marginBottom: 10 }}>
        <div className="panel-head">
          <span>CDSCO · Not-of-Standard-Quality Register</span>
          <span className="sub">{res.data.meta.total} notices · seed provenance: cdsco_nsq_seed</span>
        </div>
        <div className="panel-body">
          {res.data.reason_breakdown.map((r) => (
            <span className="chip" key={r.reason}>
              {r.reason} · {r.count}
            </span>
          ))}
        </div>
      </section>

      <section className="panel">
        <div className="panel-head"><span>Batch Failure Ledger</span></div>
        <div className="panel-body" style={{ padding: 0 }}>
          <table className="tt">
            <thead>
              <tr><th>Drug / Device</th><th>Reason</th><th>Batch Detail</th><th>Drawn By</th><th>Lab</th></tr>
            </thead>
            <tbody>
              {res.data.data.map((a) => (
                <tr key={a.id}>
                  <td style={{ color: "var(--warn)" }}>{a.drug_name}</td>
                  <td className="mut">{a.reason}</td>
                  <td className="faint" style={{ maxWidth: 420, whiteSpace: "normal", fontSize: 10.5 }}>{a.batch_detail}</td>
                  <td className="mut">{a.drawn_by}</td>
                  <td className="mut">{a.lab}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}
