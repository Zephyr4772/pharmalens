import { useQuery } from "@tanstack/react-query";
import { ago, get, num, type Row } from "../lib/api";
import { Kpi, Loading, Panel } from "../components/ui";

// "How it works": the public face of the project. Everything here comes from the live server: the feed registry and
// its schedules, the run log, and row counts (cached ten minutes server-side).

const LABELS: [string, string][] = [
  ["products", "Catalog SKUs"], ["molecules", "Molecules"], ["combos", "Salt combinations"], ["companies", "Marketers"],
  ["parents", "Corporate groups"], ["makers", "Manufacturers"], ["sites", "Manufacturing sites"], ["entity_links", "Entity links"],
  ["reg_nsq", "NSQ / spurious batch records"], ["reg_approvals", "CDSCO approvals"], ["reg_banned_fdc", "Banned combinations"],
  ["sec_items", "Expert-committee decisions"], ["brand_registry", "Brand registry (Rule 84AB)"], ["cdci_brand", "CDCI brands"],
  ["price_observations", "Price observations"], ["mfr_prices", "Manufacturer price-list rows"], ["nppa_retail_prices", "NPPA launch prices"],
  ["nppa_ceiling", "NPPA ceiling prices"], ["procurement_rates", "State tender rates"], ["fda_inspections", "US FDA inspections"],
  ["fda_citations", "Form 483 citations"], ["fda_compliance_actions", "FDA warning letters and actions"], ["fda_import_refusals", "FDA import refusals (India)"],
  ["usfda_actions", "FDA recalls and import alerts"], ["us_applications", "US drug applications"], ["us_orange_book", "Orange Book entries"],
  ["us_ndc", "US NDC products"], ["us_patents", "US patents"], ["ema_medicines", "EMA medicines"], ["who_pq", "WHO prequalified"],
  ["trials", "Clinical trials in India"], ["quote_history", "Daily share prices"], ["corp_announcements", "NSE announcements"],
  ["fin_results", "Quarterly results"], ["news", "News items"], ["events", "Events raised"],
];

function hoursOf(h: unknown): number[] {
  if (typeof h === "number") return [h];
  if (typeof h !== "string") return [];
  return h.split(",").flatMap((part) => {
    const [range, step] = part.split("/");
    const s = step ? Number(step) : 1;
    const [a, b] = range === "*" ? [0, 23] : range.includes("-") ? range.split("-").map(Number) : [Number(range), Number(range)];
    const out: number[] = [];
    for (let x = a; x <= (step && !range.includes("-") && range !== "*" ? 23 : b); x += s) out.push(x);
    return out;
  });
}

function cadence(s: Row) {
  if (!s) return "";
  if (s.trigger === "interval") return `every ${s.minutes ?? s.hours} ${s.minutes ? "min" : "h"}`;
  const hrs = hoursOf(s.hour);
  const when = hrs.length > 3 ? `${hrs.length}× a day` : hrs.map((h) => `${String(h).padStart(2, "0")}:${String(s.minute ?? 0).padStart(2, "0")}`).join(", ");
  if (s.day !== undefined) return `monthly (day ${s.day}) ${when}`;
  if (s.day_of_week) return `${String(s.day_of_week).replace(/,/g, " & ")} ${when}`;
  return `daily ${when}`;
}

function istNow() {
  const p = new Intl.DateTimeFormat("en-GB", { timeZone: "Asia/Kolkata", hour: "2-digit", minute: "2-digit", hour12: false }).formatToParts(new Date());
  return Number(p.find((x) => x.type === "hour")?.value) + Number(p.find((x) => x.type === "minute")?.value) / 60;
}

function Timeline({ areas, feeds }: { areas: Record<string, string[]>; feeds: Record<string, Row> }) {
  const L = 150, R = 950, rowH = 26, top = 22;
  const X = (h: number) => L + (h / 24) * (R - L);
  const rows = Object.entries(areas);
  const H = top + rows.length * rowH + 8;
  const now = istNow();
  return (
    <svg viewBox={`0 0 960 ${H}`} style={{ width: "100%", height: "auto", fontFamily: "var(--mono)" }} role="img" aria-label="Timed jobs across a day, IST">
      {Array.from({ length: 25 }, (_, h) => (
        <g key={h}>
          <line x1={X(h)} x2={X(h)} y1={top - 6} y2={H - 6} stroke="var(--line)" strokeWidth={h % 6 ? 1 : 1.5} />
          {h % 3 === 0 && <text x={X(h)} y={12} fill="var(--faint)" fontSize="10" textAnchor="middle">{String(h).padStart(2, "0")}:00</text>}
        </g>
      ))}
      <line x1={X(now)} x2={X(now)} y1={top - 8} y2={H - 4} stroke="var(--up)" strokeWidth={1.5} strokeDasharray="3 3"><title>now (IST)</title></line>
      {rows.map(([area, names], i) => {
        const y = top + i * rowH + rowH / 2;
        return (
          <g key={area}>
            <text x={8} y={y + 4} fill="var(--dim)" fontSize="11">{area}</text>
            {names.map((n) => {
              const f = feeds[n];
              const s = f?.schedule;
              if (!s) return null;
              if (s.trigger === "interval")
                return <line key={n} x1={L} x2={R} y1={y + 7} y2={y + 7} stroke="var(--info)" strokeWidth={1.2} strokeDasharray="2 4" opacity={0.8}><title>{`${f.title}: ${cadence(s)}`}</title></line>;
              const weekly = s.day_of_week !== undefined || s.day !== undefined;
              return hoursOf(s.hour).map((h) => (
                <circle key={`${n}-${h}`} cx={X(h + (s.minute ?? 0) / 60)} cy={y} r={4}
                  fill={weekly ? "none" : "var(--amber)"} stroke="var(--amber)" strokeWidth={1.5}>
                  <title>{`${f.title}: ${String(h).padStart(2, "0")}:${String(s.minute ?? 0).padStart(2, "0")} IST${weekly ? ` (${s.day_of_week ?? "monthly"})` : ""}`}</title>
                </circle>
              ));
            })}
          </g>
        );
      })}
    </svg>
  );
}

export default function About() {
  const sc = useQuery({ queryKey: ["showcase"], queryFn: () => get<Row>("/meta/showcase"), refetchInterval: 600_000 });
  const fd = useQuery({ queryKey: ["feeds"], queryFn: () => get<{ data: Row[] }>("/meta/feeds"), refetchInterval: 30_000 });
  if (sc.isLoading || fd.isLoading) return <Loading />;
  const s = sc.data ?? {};
  const feeds: Record<string, Row> = Object.fromEntries((fd.data?.data ?? []).map((f) => [f.name, f]));
  const c = s.counts ?? {};
  const runs = Object.values(s.runs14 ?? {}) as { runs: number; ok: number }[];
  const total = runs.reduce((a, r) => a + r.runs, 0), ok = runs.reduce((a, r) => a + r.ok, 0);
  const areas: Record<string, string[]> = s.areas ?? {};
  const external = Object.entries(areas).filter(([a]) => a !== "Internal jobs").reduce((a, [, v]) => a + v.length, 0);
  const upcoming = Object.values(feeds).filter((f) => f.next_run).sort((a, b) => String(a.next_run).localeCompare(String(b.next_run))).slice(0, 8);
  const range = (t: string) => (s.ranges?.[t] ? `${s.ranges[t][0]} → ${s.ranges[t][1]}` : "");
  return (
    <div className="stack">
      <Panel title="How PharmaLens works" sub="live from the server" bodyClass="prose">
        <p>PharmaLens is a live intelligence terminal for the Indian pharmaceutical market. {external} timed fetchers pull from Indian regulators,
          price authorities, state procurement agencies, the stock exchange, news wires and the US FDA; {Object.keys(feeds).length - external} internal jobs
          link the records, raise events, watch the feeds and send briefings. Everything on this page is read from the running system.</p>
        <p>A portfolio project by Sinhal Joshi (<a href="https://github.com/Zephyr4772" target="_blank" rel="noreferrer">GitHub</a>,{" "}
          <a href="https://zephyr4772.github.io/" target="_blank" rel="noreferrer">blog</a>). This public view is read-only: the data stays on the
          server, with no exports and no API.</p>
      </Panel>

      <div className="kpis">
        <Kpi label="Fetchers" value={external} sub={`+ ${Object.keys(feeds).length - external} internal jobs`} tone="amber" />
        <Kpi label="Runs, last 14 days" value={num(total)} sub={total ? `${((ok / total) * 100).toFixed(1)}% succeeded` : ""} tone="up" />
        <Kpi label="Catalog SKUs" value={num(c.products)} sub={`${num(c.molecules)} molecules`} />
        <Kpi label="Entity links" value={num(c.entity_links)} sub={s.links_high ? `${num(s.links_high)} high confidence` : ""} />
        <Kpi label="Manufacturing sites" value={num(c.sites)} sub={`${num(c.makers)} manufacturers`} />
        <Kpi label="US FDA inspections" value={num(c.fda_inspections)} sub={`${num(c.fda_citations)} Form 483 citations`} />
      </div>

      <Panel title="A day of timed jobs" sub="IST · filled = daily, hollow = weekly or monthly, dotted line = runs every few minutes, green = now">
        <Timeline areas={areas} feeds={feeds} />
      </Panel>

      <div className="grid cols-2">
        <Panel title="How data flows" bodyClass="prose">
          <p><b>1. Fetch.</b> Each source is polled at its own cadence, from every 5 minutes (share prices) to monthly (drug compendium). One government site blocks cloud servers, so a relay on a home laptop fetches it and
            uploads it over the private network.</p>
          <p><b>2. Store.</b> One DuckDB database on a small Azure VM (1 vCPU, 2 GB), capped at 600 MB of memory and spilling to disk.</p>
          <p><b>3. Link.</b> Every morning at 05:10 the entity linker resolves free-text records (batch failures, approvals, inspections,
            news, tenders) to molecules, manufacturers, plants and corporate groups. Each link stores its method, a confidence score, the
            evidence that matched and the licence class of its inputs; only links at 0.85 or above are shown by default. Precision is
            checked by hand on random 50-link samples.</p>
          <p><b>4. Use.</b> The terminal, a Telegram analyst bot, alert subscriptions and a results-day preview all read the same tables. A
            health watcher messages Telegram when a feed fails twice, goes stale or the nightly backup stops.</p>
        </Panel>
        <Panel title="Next runs" sub="from the live scheduler">
          <table className="tt">
            <thead><tr><th>Job</th><th>Source</th><th>When (IST)</th></tr></thead>
            <tbody>{upcoming.map((f) => (
              <tr key={f.name}><td>{f.title}</td><td className="amb">{f.agency}</td>
                <td className="mut">{new Date(f.next_run).toLocaleString("en-IN", { timeZone: "Asia/Kolkata", day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" })}</td></tr>
            ))}</tbody>
          </table>
        </Panel>
      </div>

      <Panel title="Every job" sub="schedule from the code, last run and 14-day record from the run log">
        <table className="tt">
          <thead><tr><th>Area</th><th>Job</th><th>Source</th><th>Schedule (IST)</th><th>Last run</th><th>Status</th><th className="num">14 days</th></tr></thead>
          <tbody>{Object.entries(areas).flatMap(([area, names]) => names.map((n, i) => {
            const f = feeds[n] ?? {};
            const r = s.runs14?.[n];
            return (
              <tr key={n} title={f.description}>
                <td className="mut">{i === 0 ? area : ""}</td><td>{f.title ?? n}</td><td className="amb">{f.agency}</td>
                <td className="mut">{cadence(f.schedule)}</td>
                <td>{f.last_run ? `${ago(f.last_run)} ago` : "never"}</td>
                <td>{f.running ? <span className="badge b-info">RUNNING</span> : f.last_status === "ok" ? <span className="badge b-up">OK</span> : f.last_status ? <span className="badge b-down">ERR</span> : <span className="badge b-mute">—</span>}</td>
                <td className="num">{r ? `${r.ok}/${r.runs}` : "—"}</td>
              </tr>
            );
          }))}</tbody>
        </table>
      </Panel>

      <div className="grid cols-2">
        <Panel title="What has been collected" sub={s.asof ? `row counts, ${s.asof.replace("T", " ")}` : ""}>
          <table className="tt">
            <thead><tr><th>Dataset</th><th className="num">Rows</th><th>Covers</th></tr></thead>
            <tbody>{LABELS.filter(([t]) => c[t] != null).map(([t, label]) => (
              <tr key={t}><td>{label}</td><td className="num">{num(c[t])}</td><td className="mut">{range(t)}</td></tr>
            ))}</tbody>
          </table>
        </Panel>
        <Panel title="Built to keep running" bodyClass="prose">
          <p><b>Stack.</b> Python (FastAPI, APScheduler, DuckDB, pandas), React and TypeScript, Docker on an Azure VM. The server sits on a
            private Tailscale network; this page is shared through Tailscale Funnel.</p>
          <p><b>Recovery.</b> Nightly backups kept for 7 days, plus a weekly copy pulled to a separate machine. A linker step that runs out
            of memory is rolled back, retried once with more headroom, and the rest still run.</p>
          <p><b>US FDA depth.</b> Inspections, Form 483 citations, warning letters and import refusals are placed on Indian manufacturing
            plants by FDA establishment ID first, then by firm and place, with a guard that the place must agree.</p>
          <p><b>Licences.</b> Every table and link carries the licence class of its sources ({Object.entries(s.licence_mix ?? {}).map(([k, v]) => `${v} ${k}`).join(", ")}).
            That is why the data is viewable here but not downloadable.</p>
        </Panel>
      </div>
    </div>
  );
}
