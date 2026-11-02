// Thin typed fetch layer over /api/v1. Rows are loosely typed: the API is the schema.
export type Row = Record<string, any>;
export interface Paged<T = Row> {
  meta: { total: number; page: number; limit: number; pages: number };
  data: T[];
  [k: string]: any;
}

const BASE = "/api/v1";

export function qs(params: Record<string, unknown> = {}) {
  const u = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "" && !(typeof v === "number" && Number.isNaN(v))) u.set(k, String(v));
  }
  const s = u.toString();
  return s ? `?${s}` : "";
}

export async function get<T = any>(path: string, params?: Record<string, unknown>): Promise<T> {
  const r = await fetch(`${BASE}${path}${qs(params)}`);
  if (!r.ok) throw new Error(`${r.status} ${(await r.text()).slice(0, 200)}`);
  return r.json();
}

export async function post<T = any>(path: string, body: unknown): Promise<T> {
  const r = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`${r.status} ${(await r.text()).slice(0, 200)}`);
  return r.json();
}

export async function send<T = any>(method: "PUT" | "DELETE", path: string, body?: unknown): Promise<T> {
  const r = await fetch(`${BASE}${path}`, {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`${r.status} ${(await r.text()).slice(0, 200)}`);
  return r.json();
}

export const csvUrl =(path: string, params?: Record<string, unknown>) => `${BASE}${path}${qs({ ...params, format: "csv" })}`;

// ---------- formatting
export const inr = (n: number | null | undefined, dash = "—") =>
  n === null || n === undefined || Number.isNaN(n)
    ? dash
    : "₹" + n.toLocaleString("en-IN", { maximumFractionDigits: n < 100 ? 2 : 0 });

export const crore = (n: number | null | undefined) =>
  n == null ? "—" : n >= 1e12 ? `₹${(n / 1e12).toFixed(2)}L Cr` : `₹${(n / 1e7).toLocaleString("en-IN", { maximumFractionDigits: 0 })} Cr`;

export const pct = (n: number | null | undefined, digits = 1, dash = "—") =>
  n === null || n === undefined || Number.isNaN(n) ? dash : `${n.toFixed(digits)}%`;

export const share = (n: number | null | undefined, digits = 1) => (n == null ? "—" : `${(n * 100).toFixed(digits)}%`);

export const signed = (n: number | null | undefined, digits = 2) =>
  n == null ? "—" : `${n > 0 ? "+" : ""}${n.toFixed(digits)}%`;

export const num = (n: number | null | undefined) => (n === null || n === undefined ? "—" : Number(n).toLocaleString("en-IN"));

export const ago = (iso: string | null | undefined) => {
  if (!iso) return "—";
  const t = new Date(iso.replace(" ", "T")).getTime();
  const s = Math.max(0, (Date.now() - t) / 1000);
  if (s < 90) return `${Math.round(s)}s`;
  if (s < 5400) return `${Math.round(s / 60)}m`;
  if (s < 129600) return `${Math.round(s / 3600)}h`;
  return `${Math.round(s / 86400)}d`;
};

export const day = (iso: string | null | undefined) =>
  iso ? new Date(iso.replace(" ", "T")).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "2-digit" }) : "—";

export const hhiLabel = (h: number | null | undefined) =>
  h == null ? "—" : h >= 2500 ? "CONCENTRATED" : h >= 1500 ? "MODERATE" : "FRAGMENTED";

export const SEV_CLASS: Record<string, string> = { critical: "b-down", high: "b-warn", medium: "b-info", info: "b-mute" };
