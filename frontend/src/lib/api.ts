// Klient API SCAM DNA. Kontrakt: docs/api.md, schemat OpenAPI: /api/schema/.
// Frontend niczego nie liczy sam. Każda wartość na ekranie pochodzi z tych wywołań.

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type Family = "infra" | "track" | "tmpl" | "crea" | "narr" | "pers" | "beh";
export type Relation = "same_campaign" | "same_operator" | "similar";
export type Verdict = "" | "confirmed" | "rejected" | "unsure";
export type Source = "manual" | "meta" | "google" | "tiktok" | "microsoft" | "native" | "capture";

export const FAMILY_LABELS: Record<Family, string> = {
  infra: "Infrastruktura",
  track: "Tracking i lejek",
  tmpl: "Szablon strony",
  crea: "Kreacja",
  narr: "Narracja",
  pers: "Osoby i marki",
  beh: "Zachowanie",
};

// same_campaign: to samo źródło i ta sama opowieść. same_operator: to samo zaplecze, inna opowieść.
// similar: podobna koncepcja bez dowodu wspólnego zaplecza.
export const RELATION_LABELS: Record<Relation, string> = {
  same_campaign: "Ta sama kampania",
  same_operator: "Ten sam operator",
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

// Ocena nowego materiału względem korpusu. Przychodzi w zdarzeniu `cluster` / `done` i w `analysis.result.cluster`.
export type Assessment = "duplicate" | "known_campaign" | "known_operator" | "similar_only" | "new_pattern";

export interface ClusterResult {
  campaign: string | null;
  campaign_id?: number;
  size?: number;
  operator: string | null;
  operator_id?: number;
  operator_size?: number;
  assessment: Assessment;
  assessment_label: string;
}

// Ładunek zdarzenia `fuse` / `info`: jedno znalezione powiązanie. Graf dorysowuje krawędź przy każdym takim zdarzeniu.
export interface FuseEventPayload {
  edge: number;
  other_ad: number;
  relation: Relation;
  probability: number;
  bits: number;
  families: Partial<Record<Family, number>>;
  top_evidence: { family: Family; kind: string; label: string; value: string; bits: number }[];
}

export interface AdSummary {
  id: number;
  source: Source;
  external_id: string;
  title: string;
  landing_url: string;
  first_seen: string | null;
  last_seen: string | null;
  labels: {
    case?: string;
    bundle?: string;
    keywords?: string[];
    topics?: string[]; // inwestycje | zdrowie | hazard | sensacja | sklep
    cert_pl?: { domain: string; added_at: string | null; removed_at: string | null };
  };
  campaign: string | null; // np. "K-0033"
  operator: string | null; // np. "O-0001"
  case: string | null; // numer sprawy z paczki przechwyceń
}

export interface Marker {
  kind: string;
  label: string;
  value: string;
  ad_count: number;
  decisive: boolean;
  artifact: string | null;
  detail: Record<string, unknown>;
}

export interface AdDetail extends AdSummary {
  text: string;
  display_url: string;
  creative_url: string;
  advertiser: { id: number | null; external_id: string; name: string; payer: string } | null;
  creatives: string[]; // sha256 zrzutów reklamy, obraz: artifactImageUrl(sha)
  genome: { family: Family; label: string; markers: Marker[] }[];
}

export interface Edge {
  id: number;
  ad_a: number;
  ad_b: number;
  relation: Relation;
  duplicate: boolean; // ta sama strona przechwycona ponownie
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
  df: number; // w ilu niezależnych źródłach występuje wartość; 0 dla markerów miękkich
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

export interface Group {
  id: number;
  key: string;
  label: string;
  size: number;
  created_at: string;
}

export interface CoreMarker {
  kind: string;
  label: string;
  family: Family;
  decisive: boolean;
  value: string;
  in_group: number;
  ad_count: number;
}

export interface GroupDetail extends Group {
  ads: AdSummary[];
  edges: Edge[];
  core_markers: CoreMarker[];
}

export interface OperatorDetail extends GroupDetail {
  campaigns: string[];
}

// Oś czasu kampanii albo operatora. Zdarzenie bez daty w bazie się nie pojawia.
export type TimelineEventType =
  | "domain_registered"
  | "cert_issued"
  | "ad_first_seen"
  | "snapshot"
  | "ad_last_seen"
  | "cert_pl_added"
  | "cert_pl_removed";

export interface TimelineEvent {
  type: TimelineEventType;
  label: string;
  at: string;
  ads: number[];
  value: string;
  detail: {
    registrar?: string;
    issuer?: string;
    domains?: string[];
    active?: boolean;
  };
}

export interface Timeline {
  group: string;
  events: TimelineEvent[];
}

export interface Graph {
  nodes: { id: number; label: string; source: Source; campaign: string | null; operator: string | null; case: string | null; listed: boolean }[];
  edges: {
    id: number;
    source: number;
    target: number;
    relation: Relation;
    duplicate: boolean;
    probability: number;
    bits: number;
    family: Family | null;
    families: Partial<Record<Family, number>>;
    verdict: Verdict;
  }[];
}

export interface Stats {
  ads: number;
  campaigns: number;
  operators: number;
  edges: Partial<Record<Relation, number>>;
  by_source: Partial<Record<Source, number>>;
  cert_pl_listed: number;
  last_analysis: string | null;
}

export interface Kinds {
  families: { code: Family; label: string }[];
  kinds: { code: string; family: Family; label: string; decisive: boolean; soft: boolean }[];
}

export interface Page<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = init?.body instanceof FormData ? init.headers : { "Content-Type": "application/json", ...init?.headers };
  const response = await fetch(`${API_URL}${path}`, { ...init, headers });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`API ${response.status}: ${body.slice(0, 300)}`);
  }
  return response.json() as Promise<T>;
}

export const artifactImageUrl = (sha256: string) => `${API_URL}/api/artifacts/${sha256}/image`;
export const artifactDownloadUrl = (sha256: string) => `${API_URL}/api/artifacts/${sha256}`;

export const api = {
  createAnalysis: (kind: "url" | "text", value: string) =>
    request<Analysis>("/api/analyses", { method: "POST", body: JSON.stringify({ kind, value }) }),
  // Zrzut ekranu reklamy, zapisana strona, HAR albo ZIP z całą sprawą. Jedna analiza na każdą znalezioną stronę.
  uploadCase: (files: File[]) => {
    const form = new FormData();
    for (const file of files) form.append("files", file);
    return request<Analysis[]>("/api/analyses/upload", { method: "POST", body: form });
  },
  analysis: (id: string) => request<Analysis>(`/api/analyses/${id}`),
  ads: (query = "") => request<Page<AdSummary>>(`/api/ads${query}`),
  ad: (id: number) => request<AdDetail>(`/api/ads/${id}`),
  adEdges: (id: number) => request<Edge[]>(`/api/ads/${id}/edges`),
  edge: (id: number) => request<EdgeDetail>(`/api/edges/${id}`),
  setVerdict: (id: number, verdict: Exclude<Verdict, "">, note = "") =>
    request<EdgeDetail>(`/api/edges/${id}/verdict`, { method: "POST", body: JSON.stringify({ verdict, note }) }),
  campaigns: () => request<Page<Group>>("/api/campaigns"),
  campaign: (id: number) => request<GroupDetail>(`/api/campaigns/${id}`),
  operators: () => request<Page<Group>>("/api/operators"),
  operator: (id: number) => request<OperatorDetail>(`/api/operators/${id}`),
  campaignTimeline: (id: number) => request<Timeline>(`/api/campaigns/${id}/timeline`),
  operatorTimeline: (id: number) => request<Timeline>(`/api/operators/${id}/timeline`),
  // Filtry: ?campaign=ID, ?operator=ID, ?ad=ID, ?relation=same_campaign,same_operator, ?limit=
  graph: (query = "") => request<Graph>(`/api/graph${query}`),
  kinds: () => request<Kinds>("/api/kinds"),
  stats: () => request<Stats>("/api/stats"),
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
