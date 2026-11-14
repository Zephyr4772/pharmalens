import { ReactNode, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { SEV_CLASS, ago, type Row } from "../lib/api";
import { useWatchlist } from "../state/watchlist";
import { useMe } from "../state/me";

export function Panel({ title, sub, right, children, className = "", bodyClass = "", style }: {
  title: ReactNode; sub?: ReactNode; right?: ReactNode; children: ReactNode; className?: string; bodyClass?: string; style?: React.CSSProperties;
}) {
  return (
    <section className={`panel ${className}`} style={style}>
      <div className="panel-head">
        <span>{title} {sub && <span className="sub">{sub}</span>}</span>
        {right && <span className="panel-right">{right}</span>}
      </div>
      <div className={`panel-body ${bodyClass}`}>{children}</div>
    </section>
  );
}

export function Kpi({ label, value, sub, tone }: { label: string; value: ReactNode; sub?: ReactNode; tone?: "amber" | "down" | "up" }) {
  return (
    <div className={`kpi ${tone ? "kpi-" + tone : ""}`}>
      <div className="k-label">{label}</div>
      <div className={`k-value ${tone ?? ""}`}>{value}</div>
      {sub && <div className="k-sub">{sub}</div>}
    </div>
  );
}

export const Loading = ({ what = "loading" }: { what?: string }) => <div className="loading">{what}…</div>;
export const ErrorBox = ({ e }: { e: unknown }) => <div className="err">⚠ {String((e as Error)?.message ?? e)}</div>;
export const Empty = ({ children = "nothing here yet" }: { children?: ReactNode }) => <div className="empty">{children}</div>;

export function Sev({ s }: { s: string }) {
  return <span className={`badge ${SEV_CLASS[s] ?? "b-mute"}`}>{s}</span>;
}

export function Bar({ label, value, max, text, tone = "", to }: { label: ReactNode; value: number; max: number; text: ReactNode; tone?: string; to?: string }) {
  const w = max > 0 ? Math.max(0.5, (value / max) * 100) : 0;
  const lab = to ? <Link to={to}>{label}</Link> : label;
  return (
    <div className="bar-row">
      <span className="bar-label" title={typeof label === "string" ? label : undefined}>{lab}</span>
      <span className="bar-track"><span className={`bar-fill ${tone}`} style={{ width: `${w}%`, display: "block" }} /></span>
      <span className="bar-val">{text}</span>
    </div>
  );
}

export function Spark({ data, w = 90, h = 22 }: { data: number[]; w?: number; h?: number }) {
  if (!data || data.length < 2) return <span className="faint">—</span>;
  const min = Math.min(...data), max = Math.max(...data);
  const pts = data.map((v, i) => `${(i / (data.length - 1)) * w},${h - ((v - min) / (max - min || 1)) * (h - 2) - 1}`).join(" ");
  const up = data[data.length - 1] >= data[0];
  return (
    <svg width={w} height={h} className="spark" aria-hidden>
      <polyline points={pts} fill="none" stroke={up ? "var(--up)" : "var(--down)"} strokeWidth="1.3" />
    </svg>
  );
}

export function LineChart({ data, x, y, h = 180, fmt = (v: number) => v.toFixed(0) }: {
  data: Row[]; x: string; y: string; h?: number; fmt?: (v: number) => string;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const W = 800;
  const vals = data.map((d) => Number(d[y])).filter((v) => !Number.isNaN(v));
  if (vals.length < 2) return <Empty>no history yet</Empty>;
  const min = Math.min(...vals), max = Math.max(...vals);
  const px = (i: number) => (i / (data.length - 1)) * (W - 50) + 4;
  const py = (v: number) => h - 18 - ((v - min) / (max - min || 1)) * (h - 30);
  const path = data.map((d, i) => `${i ? "L" : "M"}${px(i)},${py(Number(d[y]))}`).join(" ");
  const up = vals[vals.length - 1] >= vals[0];
  const hv = hover != null ? data[hover] : null;
  return (
    <svg viewBox={`0 0 ${W} ${h}`} width="100%" height={h} className="linechart"
      onMouseLeave={() => setHover(null)}
      onMouseMove={(e) => {
        const r = (e.currentTarget as SVGSVGElement).getBoundingClientRect();
        const i = Math.round(((e.clientX - r.left) / r.width * W - 4) / (W - 50) * (data.length - 1));
        setHover(Math.max(0, Math.min(data.length - 1, i)));
      }}>
      {[0, 0.5, 1].map((t) => {
        const v = min + (max - min) * t;
        return (
          <g key={t}>
            <line x1={0} x2={W - 46} y1={py(v)} y2={py(v)} stroke="var(--line)" strokeDasharray="2 3" />
            <text x={W - 42} y={py(v) + 3} fontSize="10" fill="var(--faint)">{fmt(v)}</text>
          </g>
        );
      })}
      <path d={path} fill="none" stroke={up ? "var(--up)" : "var(--down)"} strokeWidth="1.6" />
      {hv && (
        <g>
          <line x1={px(hover!)} x2={px(hover!)} y1={4} y2={h - 16} stroke="var(--line-2)" />
          <circle cx={px(hover!)} cy={py(Number(hv[y]))} r="3" fill="var(--amber)" />
          <text x={Math.min(px(hover!) + 6, W - 200)} y={14} fontSize="11" fill="var(--text)">
            {String(hv[x]).slice(0, 10)} · {fmt(Number(hv[y]))}
          </text>
        </g>
      )}
      <text x={4} y={h - 3} fontSize="10" fill="var(--faint)">{String(data[0][x]).slice(0, 10)}</text>
      <text x={W - 120} y={h - 3} fontSize="10" fill="var(--faint)">{String(data[data.length - 1][x]).slice(0, 10)}</text>
    </svg>
  );
}

export function Star({ k, label, href }: { k: string; label: string; href: string }) {
  const { has, toggle } = useWatchlist();
  const on = has(k);
  return (
    <span className={`star ${on ? "on" : ""}`} title={on ? "remove from watchlist" : "add to watchlist"}
      onClick={(e) => { e.stopPropagation(); toggle({ key: k, label, href }); }}>
      {on ? "★" : "☆"}
    </span>
  );
}

export function Tabs<T extends string>({ tabs, value, onChange }: { tabs: [T, ReactNode][]; value: T; onChange: (t: T) => void }) {
  return (
    <div className="tabs">
      {tabs.map(([k, label]) => (
        <button key={k} className={value === k ? "active" : ""} onClick={() => onChange(k)}>{label}</button>
      ))}
    </div>
  );
}

export function Pager({ meta, page, setPage }: { meta?: { total: number; pages: number }; page: number; setPage: (p: number) => void }) {
  if (!meta) return null;
  return (
    <div className="pager">
      <button disabled={page <= 1} onClick={() => setPage(page - 1)}>◀</button>
      <span>page {page} / {meta.pages} · {meta.total.toLocaleString("en-IN")} rows</span>
      <button disabled={page >= meta.pages} onClick={() => setPage(page + 1)}>▶</button>
    </div>
  );
}

export function EventRow({ e, compact = false }: { e: Row; compact?: boolean }) {
  const href = e.entity_type === "parent" ? null : null;
  void href;
  return (
    <div className={`ev ev-${e.severity}`}>
      <span className="ev-time" title={e.ts}>{ago(e.ts)}</span>
      <span className="ev-kind">{String(e.kind).toUpperCase()}</span>
      {e.url ? <a href={e.url} target="_blank" rel="noreferrer" className="ev-title">{e.title}</a> : <span className="ev-title">{e.title}</span>}
      {!compact && <span className="ev-src">{e.source}</span>}
    </div>
  );
}

export function useSort<T extends Row>(rows: T[] | undefined, initial: string, desc = true) {
  const [key, setKey] = useState(initial);
  const [d, setD] = useState(desc);
  const sorted = useMemo(() => {
    const r = [...(rows ?? [])];
    r.sort((a, b) => {
      const x = a[key], y = b[key];
      if (x == null) return 1;
      if (y == null) return -1;
      return (x > y ? 1 : x < y ? -1 : 0) * (d ? -1 : 1);
    });
    return r;
  }, [rows, key, d]);
  const th = (k: string, label: ReactNode, cls = "") => (
    <th className={`${cls} sortable`} onClick={() => (k === key ? setD(!d) : (setKey(k), setD(true)))}>
      {label}{k === key ? (d ? " ▾" : " ▴") : ""}
    </th>
  );
  return { sorted, th };
}

// CSV download link; exports are off in the public view, so visitors do not see it.
export function Csv({ href, label = "CSV ⤓" }: { href: string; label?: string }) {
  const me = useMe();
  return me.loaded && !me.public ? <a href={href}>{label}</a> : null;
}
