import { useEffect, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { inr, post, type Row } from "../lib/api";
import { ErrorBox, Kpi, Panel } from "../components/ui";

const SAMPLE = `name,batch,qty,expiry,manufacturer
Dolo 650 Tablet,DOBS3975,200,08/2027,Micro Labs
Cofton Sf,CF2231,24,03/2027,
Pan 40 Tablet,,60,11/2026,Alkem
Augmentin 625 Duo Tablet,,30,02/2028,GSK
Corex Dx Syrup,,12,06/2027,
`;
const STORE = "pharmalens.shelf.v1";

function load(): { csv: string; result: Row | null } {
  try { return JSON.parse(localStorage.getItem(STORE) || "") } catch { return { csv: SAMPLE, result: null } }
}

export default function Shelf() {
  const saved = load();
  const [csv, setCsv] = useState<string>(saved.csv ?? SAMPLE);
  const [filter, setFilter] = useState<string>("");
  const check = useMutation({ mutationFn: (text: string) => post("/shelf/check", { csv: text }) });
  const result: Row | null = check.data ?? saved.result;

  useEffect(() => {
    if (check.data) {
      try { localStorage.setItem(STORE, JSON.stringify({ csv, result: check.data })); } catch { /* storage unavailable */ }
    }
  }, [check.data]); // eslint-disable-line react-hooks/exhaustive-deps

  const onFile = async (f: File | undefined) => {
    if (!f) return;
    setCsv(await f.text());
  };
  const rows: Row[] = (result?.results ?? []).filter((r: Row) => !filter || r.level === filter);
  return (
    <div className="stack">
      <div className="grid cols-3">
        <Panel title="Inventory" sub="paste CSV or load a file — name, batch, qty, expiry, manufacturer (any order, header row)">
          <textarea className="code" rows={14} value={csv} onChange={(e) => setCsv(e.target.value)} spellCheck={false} />
          <div className="row-gap">
            <button className="active" onClick={() => check.mutate(csv)} disabled={check.isPending}>{check.isPending ? "CHECKING…" : "RUN CHECK ▸"}</button>
            <label className="filebtn">LOAD CSV<input type="file" accept=".csv,.txt" onChange={(e) => onFile(e.target.files?.[0])} /></label>
            <button onClick={() => setCsv(SAMPLE)}>SAMPLE</button>
          </div>
          <p className="faint" style={{ marginTop: 8 }}>
            Checked against: prohibited/restricted FDC notifications (strength- and form-aware), every CDSCO NSQ/spurious batch since 2022,
            discontinued status, expiry, the maker's NSQ history, USFDA recalls of the parent group, cheaper same-composition brands and Jan Aushadhi prices.
            Your list stays in this browser; re-run daily — new regulator lists land automatically.
          </p>
        </Panel>
        <div className="span-2 stack">
          {check.error && <ErrorBox e={check.error} />}
          {result ? (
            <>
              <div className="kpis">
                <Kpi label="Stop sale / remove" value={result.counts.critical} tone="down" sub="bans · NSQ/spurious batch · expired" />
                <Kpi label="Review" value={result.counts.warning} tone="amber" sub="pack check · discontinued · expiring" />
                <Kpi label="Info" value={result.counts.info} sub="savings · maker history" />
                <Kpi label="Clean" value={result.counts.ok} tone="up" />
                <Kpi label="Unmatched" value={result.counts.unmatched} sub="not found in catalog" />
              </div>
              <Panel title="Results" sub={`checked ${new Date(result.checked_at).toLocaleString("en-IN")}`}
                right={<select value={filter} onChange={(e) => setFilter(e.target.value)}>
                  <option value="">all</option><option value="critical">stop sale</option><option value="warning">review</option>
                  <option value="info">info</option><option value="ok">clean</option><option value="unmatched">unmatched</option></select>}>
                {rows.map((r, i) => (
                  <div key={i} className={`shelf-row lvl-${r.level}`}>
                    <div className="shelf-head">
                      <span className={`badge ${r.level === "critical" ? "b-down" : r.level === "warning" ? "b-warn" : r.level === "ok" ? "b-up" : "b-mute"}`}>
                        {r.level === "critical" ? "STOP SALE" : r.level.toUpperCase()}
                      </span>
                      <b>{r.input.name}</b>
                      {r.input.batch && <span className="mut">batch {r.input.batch}</span>}
                      {r.input.qty != null && <span className="mut">qty {r.input.qty}</span>}
                      {r.input.expiry && <span className="mut">exp {r.input.expiry}</span>}
                      <span className="spacer" />
                      {r.match ? <span className="mut">→ <Link to={`/p/${r.match.id}`}>{r.match.name}</Link> · {r.match.company} · {inr(r.match.mrp)} <span className="faint">({r.match_score}%)</span></span>
                        : <span className="faint">no catalog match</span>}
                    </div>
                    {r.flags.map((f: Row, j: number) => (
                      <div key={j} className={`flag flag-${f.level}`}>
                        <span className="flag-code">{f.code}</span> {f.message}
                        {f.source && <> <a href={f.source} target="_blank" rel="noreferrer">source</a></>}
                        {f.product_id && <> <Link to={`/p/${f.product_id}`}>view</Link></>}
                      </div>
                    ))}
                  </div>
                ))}
              </Panel>
            </>
          ) : <Panel title="Results"><div className="empty">Run a check to see flags.</div></Panel>}
        </div>
      </div>
    </div>
  );
}
