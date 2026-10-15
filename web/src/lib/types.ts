export interface CompanyRef {
  id?: number;
  name?: string;
  slug?: string;
}
export interface SaltRef {
  id: number;
  comp: string;
  display?: string;
}

export interface DrugListItem {
  id: number;
  name: string;
  category: string | null;
  mrp: number | null;
  rating: number | null;
  review_count: number;
  company: { name: string; slug: string };
  salt: { id: number; comp: string; display?: string };
  class_min?: number | null;
  savings_pct?: number | null;
}

export interface LadderRow {
  rank: number;
  id: number;
  name: string;
  mrp: number;
  rating?: number | null;
  company: { name: string; slug: string };
  is_subject?: boolean;
}

export interface PeerStats {
  brand_count: number;
  cheapest: number;
  priciest: number;
  median: number;
  avg: number;
  spread_pct: number;
  companies?: number;
}

export interface DrugDetail extends DrugListItem {
  description: string | null;
  side_effects: string[];
  conditions: string[];
  compliance: string | null;
  interactions: { drug?: string[]; brand?: string[]; effect?: string[] } | null;
  peers: LadderRow[];
  peer_stats: PeerStats | null;
  vs_priciest_pct?: number;
  company_siblings: { id: number; name: string; mrp: number | null; salt: string }[];
}

export interface MoleculeSummary {
  id: number;
  comp: string;
  display?: string;
  brands: number;
  cheapest: number | null;
  priciest: number | null;
  avg_mrp?: number | null;
  spread_pct?: number | null;
  companies?: number;
}

export interface MoleculeDetail {
  id: number;
  comp: string;
  display: string;
  stats: PeerStats | null;
  ladder: LadderRow[];
}

export interface CompanySummary {
  id: number;
  name: string;
  slug: string;
  products: number;
  molecules: number;
  avg_mrp: number | null;
  min_mrp: number | null;
  max_mrp: number | null;
  avg_rating: number | null;
  top_category: string | null;
}

export interface CompanyDetail {
  company: { id: number; name: string; slug: string };
  stats: {
    products: number;
    molecules: number;
    categories: number;
    avg_mrp: number | null;
    min_mrp: number | null;
    max_mrp: number | null;
    median_mrp: number | null;
    avg_rating: number | null;
    reviewed: number;
    flagged: number;
  };
  top_categories: { category: string; count: number }[];
  price_bands: { band: string; count: number }[];
  portfolio: {
    id: number;
    name: string;
    mrp: number | null;
    rating: number | null;
    review_count: number;
    salt: string;
    category: string | null;
  }[];
}

export interface Overview {
  kpis: {
    drugs: number;
    priced_drugs: number;
    reviewed_drugs: number;
    price_coverage_pct: number;
    review_coverage_pct: number;
    companies: number;
    molecules: number;
    nsq_alerts: number;
    avg_mrp: number | null;
    median_mrp: number | null;
    min_mrp: number | null;
    max_mrp: number | null;
    avg_rating: number | null;
  };
  price_histogram: { band: string; count: number }[];
  top_categories: { category: string; count: number; avg_mrp: number; spread_pct: number }[];
  top_companies: { name: string; slug: string; products: number; avg_mrp: number; avg_rating: number }[];
  rating_distribution: { rating: number; count: number }[];
}

export interface ArbitrageRow {
  salt: { id: number; comp: string; display: string };
  brands: number;
  companies: number;
  cheapest: number;
  priciest: number;
  savings_pct: number;
  cheapest_brand: { id: number; name: string };
  priciest_brand: { id: number; name: string };
}

export interface NsqAlert {
  id: number;
  drug_name: string;
  batch_detail: string;
  reason: string;
  drawn_by: string;
  lab: string;
  recorded_at: string | null;
}

export interface SearchResult {
  type: "drug" | "molecule" | "company";
  id: number;
  label: string;
  sub: string;
  slug?: string;
  company?: CompanyRef;
  salt?: SaltRef;
  mrp?: number | null;
}

export interface BuildInfo {
  schema_version: string;
  built_at_utc: string;
  source_file: string;
  records: string;
  duplicates_removed: string;
  drugs: number;
  companies: number;
  molecules: number;
  nsq_alerts: number;
  [k: string]: unknown;
}
