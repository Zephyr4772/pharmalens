import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ago, day, get, num, post, type Row } from "../lib/api";
import { Kpi, Loading, Panel } from "../components/ui";

function schedule(s: Row) {
  if (s.trigger === "interval") return `every ${s.minutes ?? s.hours} ${s.minutes ? "min" : "h"}`;
  const parts = [s.day_of_week && `${s.day_of_week}`, s.hour !== undefined && `${s.hour}:${String(s.minute ?? 0).padStart(2, "0")} IST`];
  return parts.filter(Boolean).join(" ");
}

export default function Feeds() {
  const qc = useQueryClient();
  const f = useQuery({ queryKey: ["feeds"], queryFn: () => get<{ data: Row[] }>("/meta/feeds"), refetchInterval: 15_000 });
  const b = useQuery({ queryKey: ["build"], queryFn: () => get<Record<string, string>>("/meta/build") });
  const run = useMutation({
    mutationFn: (name: string) => post(`/admin/connectors/${name}/run`, {}),
    onSettled: () => qc.invalidateQueries(),
  });
  if (f.isLoading) return <Loading />;
  const feeds = f.data?.data ?? [];
  return (
    <div className="stack">
      <div className="kpis">
        <Kpi label="Live connectors" value={feeds.length} />
        <Kpi label="Healthy" value={feeds.filter((x) => x.last_status === "ok").length} tone="up" />
        <Kpi label="Errors" value={feeds.filter((x) => x.last_status === "error").length} tone="down" />
        <Kpi label="Catalog build" value={day(b.data?.built_at_utc)} sub={`${num(Number(b.data?.products))} SKUs`} />
      </div>
      <Panel title="Data feeds" sub="each source is polled at its natural cadence; new rows become events on the tape">
        <table className="tt">
          <thead><tr><th>Feed</th><th>Agency</th><th>Schedule</th><th>Last run</th><th>Status</th><th className="num">New rows</th><th className="num">Events</th><th>Next</th><th>Note</th><th /></tr></thead>
          <tbody>{feeds.map((x) => (
            <tr key={x.name} title={x.description}>
              <td>{x.title}</td><td className="amb">{x.agency}</td><td className="mut">{schedule(x.schedule)}</td>
              <td>{x.last_run ? `${ago(x.last_run)} ago` : "never"}</td>
              <td>{x.running ? <span className="badge b-info">RUNNING</span> : x.last_status === "ok" ? <span className="badge b-up">OK</span> : x.last_status ? <span className="badge b-down">ERR</span> : <span className="badge b-mute">—</span>}</td>
              <td className="num">{num(x.rows_new)}</td><td className="num">{num(x.events_new)}</td>
              <td className="mut">{x.next_run ? new Date(x.next_run).toLocaleString("en-IN", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }) : "—"}</td>
              <td className="mut" title={x.message ?? ""}>{x.message}</td>
              <td><button disabled={x.running || (run.isPending && run.variables === x.name)} onClick={() => run.mutate(x.name)}>
                {run.isPending && run.variables === x.name ? "…" : "RUN"}</button></td>
            </tr>
          ))}</tbody>
        </table>
      </Panel>
      <div className="grid cols-2">
        <Panel title="Sources" bodyClass="prose">
          <p><b>Catalog spine:</b> Indian Medicine Master Dataset (Kaggle, Sept 2026; 17 merged datasets from 1mg, Apollo, Netmeds, NPPA), overlaid with a 2025 1mg scrape for newer MRPs and in-stock flags, and DrugSetu live records. Prices show their "as of" date everywhere.</p>
          <p><b>Government:</b> CDSCO (NSQ/spurious monthly lists, Section 26A prohibitions, gazette, alerts, circulars), NPPA (orders, draft price sheets, Authority minutes, ceiling prices), PMBI Jan Aushadhi product &amp; MRP list.</p>
          <p><b>Markets &amp; news:</b> NSE quotes via Yahoo Finance (~15 min delayed), openFDA recall enforcement reports for Indian firms, ET HealthWorld, Express Pharma and targeted Google News queries.</p>
          <p><b>Mirror:</b> CDSCO moved NSQ lists to a new portal in Aug 2025; later months are taken from The Health Master's republished CDSCO PDFs and labelled as mirrored.</p>
        </Panel>
        <Panel title="Methodology" bodyClass="prose">
          <div id="method" />
          <p><b>Market share (estimate).</b> No free sales data exists for India (AIOCD/IQVIA are paid). Each SKU gets a weight = √MRP × availability (1.0 in stock, 0.6 unknown, 0.25 out of stock, 0 discontinued) × reach (1 + ln(1 + independent listings)). A group's value share in a segment is its weight over the segment total; SKU share is plain count. Subsidiaries and acquired brand houses roll up to the parent. HHI is computed on value shares (&gt;2,500 concentrated, &lt;1,500 fragmented). The square root damps price: pure MRP weighting let a few very expensive biologics outrank the largest groups. Rankings track published market data well; absolute percentages are understated because thousands of small marketers list many low-volume SKUs.</p>
          <p><b>Ban matching.</b> A product is flagged only when its molecule set matches a prohibition notification <i>and</i> every strength and dosage-form qualifier in the notification (e.g. "suspension", "dispersible", "SR") also matches. If the product lacks the strength detail, it is marked "check pack" instead. Court stays won by individual manufacturers are not tracked — always confirm against the linked notification.</p>
          <p><b>NSQ matching.</b> Manufacturer text is resolved to catalog marketers and molecules are extracted from the product text; the SHELF check matches exact batch numbers.</p>
        </Panel>
      </div>
    </div>
  );
}
