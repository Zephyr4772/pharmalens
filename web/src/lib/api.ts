async function J<T>(r: Response): Promise<T> {
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return (await r.json()) as T;
}

const q = (params: Record<string, unknown>) => {
  const u = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "" && v !== false) u.set(k, String(v));
  }
  const s = u.toString();
  return s ? `?${s}` : "";
};

export const api = {
  overview: () => fetch("/api/v1/markets/overview").then(J<import("./types").Overview>),
  arbitrage: (limit = 15) =>
    fetch(`/api/v1/markets/arbitrage${q({ limit })}`).then(J<{ data: import("./types").ArbitrageRow[] }>),
  premium: (limit = 12) =>
    fetch(`/api/v1/markets/premium${q({ limit })}`).then(J<{ data: Record<string, unknown>[] }>),
  build: () => fetch("/api/v1/meta/build").then(J<import("./types").BuildInfo>),
  healthz: () =>
    fetch("/api/v1/healthz").then(J<{ ok: boolean; probe_ms: number }>),
  search: (query: string, limit = 14) =>
    fetch(
      `/api/v1/search${q({ q: query, limit })}`
    ).then(J<{ results: import("./types").SearchResult[]; took_ms: number }>),
  drugs: (f: Record<string, unknown>) =>
    fetch(`/api/v1/drugs${q(f)}`).then(
      J<{ meta: { total: number; page: number; pages: number }; took_ms: number; data: import("./types").DrugListItem[] }>
    ),
  drug: (id: number | string) => fetch(`/api/v1/drugs/${id}`).then(J<import("./types").DrugDetail>),
  molecules: (f: Record<string, unknown>) =>
    fetch(`/api/v1/molecules${q(f)}`).then(
      J<{ meta: { total: number; page: number; pages: number }; data: import("./types").MoleculeSummary[] }>
    ),
  molecule: (id: number | string) => fetch(`/api/v1/molecules/${id}`).then(J<import("./types").MoleculeDetail>),
  companies: (f: Record<string, unknown>) =>
    fetch(`/api/v1/companies${q(f)}`).then(
      J<{ meta: { total: number; page: number; pages: number }; data: import("./types").CompanySummary[] }>
    ),
  company: (slug: string, page = 1) =>
    fetch(`/api/v1/companies/${slug}${q({ page })}`).then(J<import("./types").CompanyDetail>),
  alerts: (f: Record<string, unknown>) =>
    fetch(`/api/v1/alerts${q(f)}`).then(
      J<{
        meta: { total: number };
        reason_breakdown: { reason: string; count: number }[];
        data: import("./types").NsqAlert[];
      }>
    ),
};

export const inr = (n: number | null | undefined, dash = "—") =>
  n === null || n === undefined
    ? dash
    : "₹" + n.toLocaleString("en-IN", { maximumFractionDigits: n < 100 ? 2 : 0 });

export const pct = (n: number | null | undefined, dash = "—") =>
  n === null || n === undefined ? dash : `${n > 0 ? "" : ""}${n.toFixed(1)}%`;

export const num = (n: number | null | undefined) =>
  n === null || n === undefined ? "—" : n.toLocaleString("en-IN");

export const ageDays = (iso: string) =>
  Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 86_400_000));
