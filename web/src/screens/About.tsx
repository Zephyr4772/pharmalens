import { useEffect, useRef, useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { ago, get, type Row } from "../lib/api";
import { Loading } from "../components/ui";

// "How it works": the public face of the project, told one idea per screen. Everything comes from the live server:
// the feed registry and its schedules, the run log, and row counts (cached ten minutes server-side).

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

// international digit grouping (543,274): this page is for readers outside India too
const num = (v: unknown) => (v == null || Number.isNaN(Number(v)) ? "—" : Number(v).toLocaleString("en-US"));

const SECTIONS = ["Intro", "Sources", "Schedule", "Flow", "Linking", "Reliability", "Data", "Engineering"];

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
  const L = 150, R = 950, rowH = 30, top = 24;
  const X = (h: number) => L + (h / 24) * (R - L);
  const rows = Object.entries(areas);
  const H = top + rows.length * rowH + 8;
  const now = istNow();
  return (
    <svg viewBox={`0 0 960 ${H}`} className="story-timeline" role="img" aria-label="Timed jobs across a day, IST">
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
                return <line key={n} x1={L} x2={R} y1={y + 8} y2={y + 8} stroke="var(--info)" strokeWidth={1.2} strokeDasharray="2 4" opacity={0.8}><title>{`${f.title}: ${cadence(s)}`}</title></line>;
              const weekly = s.day_of_week !== undefined || s.day !== undefined;
              return hoursOf(s.hour).map((h) => (
                <circle key={`${n}-${h}`} cx={X(h + (s.minute ?? 0) / 60)} cy={y} r={4.5}
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

function Sec({ id, n, eyebrow, title, lead, children }: { id: string; n?: string; eyebrow: string; title: ReactNode; lead?: ReactNode; children?: ReactNode }) {
  return (
    <section className="story-sec" id={`about-${id}`} data-sec={id}>
      <div className="story-copy">
        <div className="story-eyebrow">{n && <b>{n}</b>}{eyebrow}</div>
        <h2 className="story-title">{title}</h2>
        {lead && <p className="story-lead">{lead}</p>}
      </div>
      {children && <div className="story-body">{children}</div>}
    </section>
  );
}

const Big = ({ value, label, sub }: { value: ReactNode; label: string; sub?: ReactNode }) => (
  <div className="story-big"><div className="v">{value}</div><div className="l">{label}</div>{sub && <div className="s">{sub}</div>}</div>
);

export default function About() {
  const sc = useQuery({ queryKey: ["showcase"], queryFn: () => get<Row>("/meta/showcase"), refetchInterval: 600_000 });
  const fd = useQuery({ queryKey: ["feeds"], queryFn: () => get<{ data: Row[] }>("/meta/feeds"), refetchInterval: 30_000 });
  const box = useRef<HTMLDivElement>(null);
  const [active, setActive] = useState("Intro");
  const [allJobs, setAllJobs] = useState(false);

  // which section is on screen: drives the dots and the fade-in
  useEffect(() => {
    const root = box.current;
    if (!root) return;
    const secs = [...root.querySelectorAll<HTMLElement>(".story-sec")];
    const io = new IntersectionObserver((entries) => {
      root.classList.add("anim");   // fade-ins only once the observer is known to run; content is visible without it
      for (const e of entries) {
        if (e.isIntersecting) {
          // reveal this section and any skipped over on a fast jump
          secs.slice(0, secs.indexOf(e.target as HTMLElement) + 1).forEach((el) => el.classList.add("in"));
          setActive((e.target as HTMLElement).dataset.sec ?? "Intro");
        }
      }
    }, { root, rootMargin: "-40% 0px -40% 0px" });   // a band across the middle of the screen: works for sections taller than it
    root.querySelectorAll(".story-sec").forEach((el) => io.observe(el));
    return () => io.disconnect();
  }, [sc.isLoading, fd.isLoading]);

  if (sc.isLoading || fd.isLoading) return <Loading />;
  const s = sc.data ?? {};
  const feeds: Record<string, Row> = Object.fromEntries((fd.data?.data ?? []).map((f) => [f.name, f]));
  const c = s.counts ?? {};
  const runs = Object.values(s.runs14 ?? {}) as { runs: number; ok: number }[];
  const total = runs.reduce((a, r) => a + r.runs, 0), ok = runs.reduce((a, r) => a + r.ok, 0);
  const pct = total ? `${((ok / total) * 100).toFixed(ok === total ? 0 : 2)}%` : "—";
  const areas: Record<string, string[]> = s.areas ?? {};
  const internal = (areas["Internal jobs"] ?? []).length;
  const external = Object.keys(feeds).length - internal;
  const upcoming = Object.values(feeds).filter((f) => f.next_run).sort((a, b) => String(a.next_run).localeCompare(String(b.next_run))).slice(0, 5);
  const range = (t: string) => (s.ranges?.[t] ? `${s.ranges[t][0]} → ${s.ranges[t][1]}` : "");
  // scroll only the story (scrollIntoView would also scroll the page shell around it)
  const go = (id: string) => {
    const el = box.current?.querySelector<HTMLElement>(`#about-${id}`);
    if (el) box.current?.scrollTo({ top: el.offsetTop, behavior: "smooth" });
  };
  const jobRows = Object.entries(areas).flatMap(([area, names]) => names.map((n, i) => ({ area: i === 0 ? area : "", n, f: feeds[n] ?? {}, r: s.runs14?.[n] })));

  return (
    <div className="story-wrap">
      <nav className="story-dots" aria-label="Sections">
        {SECTIONS.map((x) => <button key={x} className={active === x ? "on" : ""} onClick={() => go(x)} title={x} aria-label={x} />)}
      </nav>
      <div className="story" ref={box}>
        <Sec id="Intro" eyebrow="Portfolio project · live system" title={<>PharmaLens <span>A live intelligence terminal for the Indian pharmaceutical market</span></>}
          lead={<>{external} fetchers pull from Indian regulators, price authorities, state tenders, the stock exchange, news wires and the US FDA.
            {" "}{internal} internal jobs turn that into linked, searchable records. Every number on this page is read from the running server.</>}>
          <div className="story-bigs">
            <Big value={num(c.products)} label="Catalog SKUs" sub={`${num(c.molecules)} molecules`} />
            <Big value={num(c.entity_links)} label="Entity links" sub="each with method, confidence and evidence" />
            <Big value={num(total)} label="Runs in the last 14 days" sub={`${pct} succeeded`} />
          </div>
          <p className="story-note">A portfolio project by Sinhal Joshi · <a href="https://github.com/Zephyr4772" target="_blank" rel="noreferrer">GitHub</a> ·{" "}
            <a href="https://zephyr4772.github.io/" target="_blank" rel="noreferrer">blog</a> · This public view is read-only: the data stays on the server, with no exports and no API.</p>
          <button className="story-next" onClick={() => go("Sources")}>Scroll ↓</button>
        </Sec>

        <Sec id="Sources" n="01" eyebrow="Where the data comes from" title={<>{external} fetchers, each on its own clock</>}
          lead="Each source is polled at the pace it changes: share prices every 5 minutes, regulator lists daily, the drug compendium monthly. One government site blocks cloud servers, so a relay on a home laptop fetches it and uploads it over the private network.">
          <div className="story-cards">
            {Object.entries(areas).filter(([a]) => a !== "Internal jobs").map(([area, names]) => {
              const agencies = [...new Set(names.map((n) => feeds[n]?.agency).filter(Boolean))];
              return (
                <div key={area} className="story-card">
                  <div className="h"><span>{area}</span><b>{names.length}</b></div>
                  <div className="t">{agencies.join(" · ")}</div>
                </div>
              );
            })}
          </div>
        </Sec>

        <Sec id="Schedule" n="02" eyebrow="A day of timed jobs" title="What runs when, in IST"
          lead="Every dot is a scheduled run. Filled dots run daily, hollow ones weekly or monthly, dotted lines repeat every few minutes, and the green line is now. Hover a dot to see the job.">
          <div className="story-scroll-x"><Timeline areas={areas} feeds={feeds} /></div>
          <div className="story-next-runs">
            <span className="lbl">Next up</span>
            {upcoming.map((f) => (
              <span key={f.name} className="run"><b>{new Date(f.next_run).toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata", hour: "2-digit", minute: "2-digit" })}</b> {f.title}</span>
            ))}
          </div>
        </Sec>

        <Sec id="Flow" n="03" eyebrow="How data flows" title="Fetch, store, link, use">
          <div className="story-steps">
            {[
              ["Fetch", "Each source on its own schedule, from every 5 minutes to monthly. A home relay covers the one site that blocks cloud servers."],
              ["Store", "One DuckDB database on a small Azure VM (1 vCPU, 2 GB), capped at 600 MB of memory and spilling to disk."],
              ["Link", "Every morning at 05:10 the entity linker ties free-text records to molecules, manufacturers, plants and corporate groups."],
              ["Use", "The terminal, a Telegram analyst bot, alert subscriptions and results-day previews all read the same tables."],
            ].map(([t, d], i) => (
              <div key={t} className="story-step"><div className="k">{i + 1}</div><div className="h">{t}</div><div className="t">{d}</div></div>
            ))}
          </div>
        </Sec>

        <Sec id="Linking" n="04" eyebrow="The hard part" title="Turning free text into linked records"
          lead="Regulators publish firm and product names as typed text, spelled differently in every list. The linker resolves batch failures, approvals, inspections, news and tenders to the right molecule, manufacturer, plant and group, and records why.">
          <div className="story-bigs">
            <Big value={num(c.entity_links)} label="Links" sub={s.links_high ? `${num(s.links_high)} at high confidence` : undefined} />
            <Big value={num(c.sites)} label="Manufacturing sites" sub={`${num(c.makers)} manufacturers`} />
            <Big value={num(c.fda_inspections)} label="US FDA inspections" sub={`${num(c.fda_citations)} Form 483 citations`} />
          </div>
          <ul className="story-points">
            <li>Every link stores its method, a confidence score, the evidence that matched and the licence class of its inputs.</li>
            <li>Only links at 0.85 confidence or above are shown by default; weaker ones are labelled as inferred.</li>
            <li>US FDA records are placed on Indian plants by FDA establishment ID first, then by firm and place, and the place must agree.</li>
            <li>Precision is checked by hand on random 50-link samples.</li>
          </ul>
        </Sec>

        <Sec id="Reliability" n="05" eyebrow="Does it keep running?" title={<>{num(total)} runs in 14 days, {pct} succeeded</>}
          lead="A health watcher messages Telegram when a feed fails twice, goes stale or the nightly backup stops. A linker step that runs out of memory is rolled back and retried with more headroom, and the rest still run.">
          <div className={`story-jobs ${allJobs ? "open" : ""}`}>
            <table className="tt">
              <thead><tr><th>Area</th><th>Job</th><th>Source</th><th>Schedule (IST)</th><th>Last run</th><th>Status</th><th className="num">14 days</th></tr></thead>
              <tbody>{jobRows.map(({ area, n, f, r }) => (
                <tr key={n} title={f.description}>
                  <td className="mut">{area}</td><td>{f.title ?? n}</td><td className="amb">{f.agency}</td>
                  <td className="mut">{cadence(f.schedule)}</td>
                  <td>{f.last_run ? `${ago(f.last_run)} ago` : "never"}</td>
                  <td>{f.running ? <span className="badge b-info">RUNNING</span> : f.last_status === "ok" ? <span className="badge b-up">OK</span> : f.last_status ? <span className="badge b-down">ERR</span> : <span className="badge b-mute">—</span>}</td>
                  <td className="num">{r ? `${r.ok}/${r.runs}` : "—"}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
          <button className="story-toggle" onClick={() => setAllJobs((v) => !v)}>{allJobs ? "Show fewer" : `Show all ${jobRows.length} jobs`}</button>
        </Sec>

        <Sec id="Data" n="06" eyebrow="What has been collected" title="Years of records, refreshed on schedule"
          lead={s.asof ? `Row counts read from the database at ${s.asof.replace("T", " ")} IST, with the period each dataset covers.` : undefined}>
          <div className="story-counts">
            {LABELS.filter(([t]) => c[t] != null).map(([t, label]) => (
              <div key={t} className="story-count"><div className="v">{num(c[t])}</div><div className="l">{label}</div>{range(t) && <div className="s">{range(t)}</div>}</div>
            ))}
          </div>
        </Sec>

        <Sec id="Engineering" n="07" eyebrow="Under the hood" title="A small server, run carefully">
          <div className="story-steps">
            <div className="story-step"><div className="h">Stack</div><div className="t">Python (FastAPI, APScheduler, DuckDB, pandas), React and TypeScript, Docker on an Azure VM. The server sits on a private Tailscale network; this view is shared through Tailscale Funnel.</div></div>
            <div className="story-step"><div className="h">Recovery</div><div className="t">Nightly backups kept for 7 days, plus a weekly copy pulled to a separate machine.</div></div>
            <div className="story-step"><div className="h">Licences</div><div className="t">Every table and link carries the licence class of its sources ({Object.entries(s.licence_mix ?? {}).map(([k, v]) => `${v} ${k}`).join(", ")}). That is why the data is viewable here but not downloadable.</div></div>
          </div>
          <div className="story-cta">
            <span>Explore the terminal:</span>
            <Link to="/">Today</Link><Link to="/companies">Companies</Link><Link to="/reg">Regulatory desk</Link><Link to="/pipeline">Pipeline</Link><Link to="/feeds">Feeds</Link>
          </div>
        </Sec>
      </div>
    </div>
  );
}
