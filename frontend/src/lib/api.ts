// Klient API SCAM DNA. Kontrakt: docs/api.md, schemat OpenAPI: /api/schema/.
// Frontend niczego nie liczy sam. Każda wartość na ekranie pochodzi z tych wywołań.

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type Family = "infra" | "track" | "tmpl" | "crea" | "narr" | "pers" | "beh";
export type Relation = "same_campaign" | "similar";
export type Verdict = "" | "confirmed" | "rejected" | "unsure";

export const FAMILY_LABELS: Record<Family, string> = {
  infra: "Infrastruktura",
  track: "Tracking i lejek",
  tmpl: "Szablon strony",
  crea: "Kreacja",
  narr: "Narracja",
  pers: "Osoby i marki",
  beh: "Zachowanie",
};

export const RELATION_LABELS: Record<Relation, string> = {
  same_campaign: "Ta sama kampania",
  similar: "Podobna koncepcja",
};

export interface Analysis {
  id: string;
  ad: number | null;
  input_kind: "url" | "text" | "ad";
  input_value: string;
  status: "queued" | "running" | "done" | "failed";
  result: Record<string, unknown>;
  error: string;
  created_at: string;
  finished_at: string | null;
  events_url: string;
}

export interface AnalysisEvent {
  seq: number;
  stage: "ingest" | "crawl" | "extract" | "enrich" | "fuse" | "cluster" | "end";
  status: "started" | "done" | "info" | "error";
  message: string;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface AdSummary {
  id: number;
  source: string;
  external_id: string;
  title: string;
  landing_url: string;
  first_seen: string | null;
  last_seen: string | null;
  labels: Record<string, unknown>;
  campaign: string | null;
}

export interface Marker {
  kind: string;
  label: string;
  value: string;
  ad_count: number;
  artifact: string | null;
}

export interface AdDetail extends AdSummary {
  text: string;
  display_url: string;
  creative_url: string;
  advertiser: { id: number; external_id: string; name: string; payer: string } | null;
  genome: { family: Family; label: string; markers: Marker[] }[];
}

export interface Edge {
  id: number;
  ad_a: number;
  ad_b: number;
  relation: Relation;
  bits: number;
  probability: number;
  decisive: boolean;
  families: Partial<Record<Family, number>>;
  model_version: string;
  verdict: Verdict;
  updated_at: string;
}

export interface Evidence {
  family: Family;
  family_label: string;
  kind: string;
  label: string;
  value_a: string;
  value_b: string;
  similarity: number;
  df: number;
  corpus_n: number;
  raw_bits: number;
  weight_bits: number;
  decisive: boolean;
  artifact_a: string | null;
  artifact_b: string | null;
}

export interface EdgeDetail extends Edge {
  verdict_note: string;
  verdict_at: string | null;
  ads: AdSummary[];
  evidence: Evidence[];
}

export interface Campaign {
  id: number;
  key: string;
  label: string;
  size: number;
  created_at: string;
}

export interface CampaignDetail extends Campaign {
  ads: AdSummary[];
  edges: Edge[];
  core_markers: { kind: string; label: string; family: Family; value: string; in_campaign: number; ad_count: number }[];
}

export interface Graph {
  nodes: { id: number; label: string; source: string; campaign: string | null; listed: boolean }[];
  edges: { id: number; source: number; target: number; relation: Relation; probability: number; family: Family | null; verdict: Verdict }[];
}

export interface Page<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`API ${response.status}: ${body.slice(0, 300)}`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  createAnalysis: (kind: "url" | "text", value: string) =>
    request<Analysis>("/api/analyses", { method: "POST", body: JSON.stringify({ kind, value }) }),
  analysis: (id: string) => request<Analysis>(`/api/analyses/${id}`),
  ads: (query = "") => request<Page<AdSummary>>(`/api/ads${query}`),
  ad: (id: number) => request<AdDetail>(`/api/ads/${id}`),
  adEdges: (id: number) => request<Edge[]>(`/api/ads/${id}/edges`),
  edge: (id: number) => request<EdgeDetail>(`/api/edges/${id}`),
  setVerdict: (id: number, verdict: Exclude<Verdict, "">, note = "") =>
    request<EdgeDetail>(`/api/edges/${id}/verdict`, { method: "POST", body: JSON.stringify({ verdict, note }) }),
  campaigns: () => request<Page<Campaign>>("/api/campaigns"),
  campaign: (id: number) => request<CampaignDetail>(`/api/campaigns/${id}`),
  graph: (query = "") => request<Graph>(`/api/graph${query}`),
};

// Strumień postępu analizy. Zdarzenia przychodzą w kolejności, w jakiej backend je zapisał.
export function streamAnalysis(
  analysis: Pick<Analysis, "events_url">,
  onEvent: (event: AnalysisEvent) => void,
  onClose: () => void,
): () => void {
  const source = new EventSource(`${API_URL}${analysis.events_url}`);
  const stages: AnalysisEvent["stage"][] = ["ingest", "crawl", "extract", "enrich", "fuse", "cluster", "end"];
  for (const stage of stages) {
    source.addEventListener(stage, (message) => onEvent(JSON.parse((message as MessageEvent).data)));
  }
  const finish = () => {
    source.close();
    onClose();
  };
  source.addEventListener("close", finish);
  source.onerror = finish;
  return () => source.close();
}
