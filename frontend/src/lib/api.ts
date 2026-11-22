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
  display_value: string; // do pokazania: nazwisko zamiast person:ID; dla pozostałych typów równe value
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
  videos: VideoMaterial[];
  genome: { family: Family; label: string; markers: Marker[] }[];
}

// Nagranie reklamy albo ekranu. Pola, których nie da się ustalić, są null; powód jest w `missing`.
export interface VideoMaterial {
  sha256: string;
  name: string;
  size: number | null;
  playable: boolean; // false: plik ponad limit magazynu, nie da się go odtworzyć
  url: string | null; // ścieżka API do <video>, obsługuje zakresy bajtów
  duration_s: number | null;
  fps: number | null;
  frames: number | null;
  width: number | null;
  height: number | null;
  // klatka poglądowa: sekunda według dekodera i jej położenie w nagraniu (0..1)
  poster: { artifact: string; at_s: number; position: number | null; url: string } | null;
  // długość oryginału z metadanych pobrania; clip: czy plik jest krótszym wycinkiem (null: nie wiadomo)
  original: { duration_s: number | null; clip: boolean | null };
  // mowa z nagrania zamieniona na tekst (model może się mylić); null: brak dźwięku, cisza albo kanał wyłączony
  speech: { source: string; text: string; language: string; model: string; audio_s: number; truncated: boolean } | null;
  missing: string[];
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
  id: number; // stały w obrębie krawędzi, do wyłączania w laboratorium dowodów
  family: Family;
  family_label: string;
  kind: string;
  label: string;
  value_a: string;
  value_b: string;
  display_value: string; // czytelna wartość, np. nazwisko osoby zamiast person:ID
  similarity: number;
  df: number; // w ilu niezależnych źródłach występuje wartość; 0 dla markerów miękkich
  corpus_n: number;
  raw_bits: number;
  weight_bits: number;
  decisive: boolean;
  artifact_a: string | null;
  artifact_b: string | null;
}

export interface GroupChange {
  group: string;
  before: number[];
  after: { key: string; ads: number[] }[];
  released: number[];
}
export interface GroupMerge {
  group: string; // klucz grupy po scaleniu
  ads: number[];
  from: string[]; // klucze grup przed
  joined: number[]; // reklamy, które wcześniej nie miały grupy
}
export interface Regroup {
  campaign: GroupChange[];
  operator: GroupChange[];
  merged?: { campaign: GroupMerge[]; operator: GroupMerge[] }; // tylko przy przywróceniu przesłanki
}

// Zakwestionowanie przesłanki (/api/premises): globalne podważenie jednego śladu (rodzaj + wartość).
export interface PremiseKind {
  kind: string;
  label: string;
  family: string;
  family_label: string;
}
export interface PremiseEdgeState {
  relation: Relation | null;
  relation_label: string;
  bits: number;
  probability: number; // wynik modelu (niekalibrowany)
}
export interface PremiseEdge {
  id: number;
  ad_a: number;
  ad_b: number;
  verdict: Verdict;
  before: PremiseEdgeState;
  after: PremiseEdgeState & { independent: string[]; kept_by_verdict: boolean };
  removed: boolean; // krawędź znika bez tego śladu
  relation_changed: boolean;
}
export interface PremiseGroupSplit {
  key: string;
  before: number[];
  after: { key: string | null; ads: number[] }[]; // pierwsza część zachowuje klucz, reszta dostaje nowe grupy
  released: number[]; // reklamy, które tracą członkostwo
}
export interface PremiseGroupStay {
  key: string;
  before: number[];
  supported_by: (PremiseKind & { bits: number })[]; // najmocniejsze ślady, które trzymają grupę bez zakwestionowanego
}
export interface PremisePreview extends PremiseKind {
  value: string;
  display_value: string;
  ads: number[];
  edge_count: number;
  edges: PremiseEdge[];
  groups: Record<"campaign" | "operator", { split: PremiseGroupSplit[]; stay: PremiseGroupStay[] }>;
  split_count: number;
  model_version: string;
  warnings: string[];
}
export interface PremiseState {
  groups: Record<"campaign" | "operator", { key: string; ads: number[] }[]>;
  edges: { id: number; ad_a: number; ad_b: number; relation: Relation; bits: number; probability: number }[];
  regroup?: Regroup;
}
export interface Premise {
  id: number;
  kind: string;
  label: string;
  value: string;
  display_value: string;
  status: "challenged" | "restored";
  status_label: string;
  reason: string;
  user: string | null;
  created_at: string;
  restored_at: string | null;
  before?: PremiseState;
  after?: PremiseState;
  restored_state?: PremiseState | null;
}

export interface EdgeDetail extends Edge {
  verdict_note: string;
  verdict_reason: VerdictReason | "";
  verdict_at: string | null;
  ads: AdSummary[];
  evidence: Evidence[];
}

export interface SimulationResult {
  relation: Relation | null; // null: krawędź by nie powstała
  relation_label: string;
  probability: number;
  bits: number;
  decisive: boolean;
  duplicate: boolean;
  families: Partial<Record<Family, number>>;
  independent: string[]; // niezależne silne potwierdzenia; "kit" to ślady jednego silnika lejka
  reasons: string[];
}

export interface GroupImpact {
  binds_before: boolean;
  binds_after: boolean;
  pair_still_connected: boolean | null; // liczone tylko, gdy krawędź przestałaby spinać grupę
  path_length: number | null;
  note: string;
}

export interface Simulation {
  edge: number;
  edge_version: string;
  model_version: string;
  stored: { relation: Relation; bits: number; model_version: string };
  baseline: SimulationResult;
  simulated: SimulationResult;
  relation_changed: boolean;
  excluded: { id: number; family: Family; kind: string; label: string; value: string; display_value: string; weight_bits: number; decisive: boolean }[];
  group_impact: { campaign: GroupImpact; operator: GroupImpact };
  warnings: string[];
}

export type UrlMatch = "exact" | "normalized" | "domain" | "different" | "unknown";

export interface ObservationContext {
  browser: string;
  platform: string;
  mobile: boolean | null;
  accept_language: string;
  cookies: boolean;
  referer: boolean;
}

export interface ObservationArtifacts {
  har: { sha256: string; download: string } | null; // tylko do pobrania
  html: { sha256: string; download: string } | null; // tylko do pobrania, nigdy renderowania
  page_screenshot: { sha256: string; image: string } | null; // tylko z crawlera z przeglądarką (docs/crawler.md)
  ad_creatives: { sha256: string; image: string }[]; // reklama, nie strona docelowa
}

export interface ObservationSide {
  ad: number;
  external_id: string;
  title: string;
  // krótki fragment widocznego tekstu z zapisanego HTML (zwykły tekst, do 300 znaków); null: brak zapisu strony
  text_excerpt: { text: string; chars: number; source: string; artifact: string } | null;
  exact_url: string;
  captured_at: string | null; // null: nieznane
  time_source: string | null; // har.entries | nask.archive_info | page-capture.manifest
  context: ObservationContext | null; // null: nieznany
  hosts: string[];
  sources: string[];
  creatives: string[];
  artifacts?: ObservationArtifacts;
}

export interface AdObservations {
  ad: number;
  observation: ObservationSide;
  artifacts: ObservationArtifacts;
  candidates: { ad: number; external_id: string; title: string; url_match: UrlMatch; url_match_label: string; captured_at: string | null }[];
  message: string;
}

export interface ObservationComparison {
  a: ObservationSide;
  b: ObservationSide;
  url_match: UrlMatch;
  url_match_label: string;
  seconds_between: number | null;
  content: { page_text_minhash: number | null; dom_minhash: number | null; image_set: number | null };
  trackers_only_a: string[];
  trackers_only_b: string[];
  hosts_only_a: string[];
  hosts_only_b: string[];
  verdict: "identical" | "similar" | "different" | "insufficient";
  verdict_label: string;
  differences: string[];
  hypotheses: string[]; // tylko przy zgodnym adresie i różnej treści
  limitations: string[];
  edge: { id: number; relation: Relation; detail: string } | null;
  graph: string;
  thresholds: { same_text: number; same_dom: number; similar_text: number; similar_dom: number };
  note: string;
}

export interface WeakestLinkGroup {
  id: string; // "kit" | "motif" | "infra" | "content" | "creative" | "template" | "kind:<typ>" | "unknown:<typ>"
  label: string;
  evidence_ids: number[];
  weight_bits: number;
}

export interface WeakestLink {
  edge: number;
  edge_version: string;
  baseline: SimulationResult;
  groups: WeakestLinkGroup[];
  searched: {
    max_group_size: number;
    scenarios_checked: number;
    scenario_limit: number;
    time_limit_ms: number;
    complete: boolean;
    stopped_reason: string;
  };
  solutions: {
    groups: string[];
    labels: string[];
    excluded_evidence: number[]; // do api.simulateEdge, ten sam wynik
    simulated: SimulationResult;
    change: string;
  }[];
  minimal_size: number | null; // tylko przy pełnym przeszukiwaniu
  message: string;
}

export type SuggestionCode =
  | "single_support"
  | "engine_without_account"
  | "copy_without_backend"
  | "har_missing"
  | "screenshot_only"
  | "story_unknown";

export interface Suggestion {
  code: SuggestionCode;
  missing: string; // jakiego dowodu brakuje (hipoteza, nie istniejący dowód)
  why: string;
  next_step: string;
  limitation: string;
  rule: string; // reguła silnika albo stan materiałów, z której wynika wskazówka
  sides: string[]; // "A (reklama #12)"; pusta, gdy dotyczy całej pary
}

export interface EdgeMaterials {
  har: boolean;
  page: boolean;
  creative: boolean;
  library_ids: string[];
}

export interface Suggestions {
  edge: number;
  relation: Relation | null;
  materials: { A: EdgeMaterials; B: EdgeMaterials };
  suggestions: Suggestion[]; // pusta lista to poprawny wynik
  note: string;
  warnings: string[];
}

export interface Group {
  id: number;
  key: string;
  label: string;
  size: number;
  created_at: string;
}

// Pozycja listy kampanii albo operatorów: skład grupy według źródła reklam.
export interface GroupListItem extends Group {
  sources: Partial<Record<Source, number>>;
  cases: number; // ile różnych spraw z paczek
  cert_pl: number; // ile reklam ma domenę na Liście Ostrzeżeń CERT Polska
}

export interface CoreMarker {
  kind: string;
  label: string;
  family: Family;
  decisive: boolean;
  value: string;
  display_value: string; // nazwisko zamiast person:ID; dla pozostałych typów równe value
  in_group: number;
  ad_count: number;
  // Wkład w grupę: suma weight_bits dowodów tego śladu na krawędziach grupy (null, gdy żadna krawędź go nie używa).
  bits: number | null;
  // Ile krawędzi grupy ma dowód z tym śladem.
  edges: number;
}

// Reklama na karcie grupy: lista reklam plus miniatura (pierwsza kreacja albo zrzut strony; null, gdy brak obrazu).
export interface GroupAd extends AdSummary {
  thumbnail: { sha256: string; image: string } | null;
}

export interface GroupDetail extends Group {
  ads: GroupAd[];
  edges: Edge[];
  core_markers: CoreMarker[];
}

export interface OperatorDetail extends GroupDetail {
  campaigns: string[];
}

// Oś obserwacji kampanii albo operatora. Każde zdarzenie mówi, jaki to rodzaj czasu i skąd jest data.
// Rzeczy bez daty nie ma na osi, są tylko policzone w `undated`.
export type TimelineEventType =
  | "domain_registered"
  | "cert_issued"
  | "ad_first_seen"
  | "trace_first_observed"
  | "link_observable"
  | "snapshot"
  | "ad_last_seen"
  | "cert_pl_added"
  | "cert_pl_removed";

// observed: chwila obserwacji materiału (to nie jest początek kampanii); reported: data podana przez źródło zewnętrzne.
export type TimeKind = "observed" | "reported";
export type TimeSource = Source | "rdap" | "crt.sh" | "cert_pl";

export interface TimelineEvent {
  type: TimelineEventType;
  label: string;
  at: string;
  time_kind: TimeKind;
  source: TimeSource;
  precision: "exact" | "day";
  ads: number[];
  value: string;
  detail: {
    registrar?: string;
    issuer?: string;
    domains?: string[];
    count?: number;
    last_at?: string;
    active?: boolean;
    kind?: string;
    kind_label?: string;
    family?: Family;
    in_group?: number;
    undated_ads?: number;
    tied?: boolean;
    // link_observable: jedno zdarzenie na dołączającą reklamę
    relations?: Partial<Record<Relation, number>>;
    partners?: number[]; // wcześniej widziane reklamy, z którymi się wiąże (do 50)
    edges?: number[]; // krawędzie (do 50)
    max_probability?: number;
    truncated?: boolean; // powiązań jest więcej niż na listach
  };
}

export interface Timeline {
  group: string;
  events: TimelineEvent[];
  undated: { ads: number[]; traces: number; links: number; certificates: number };
}

export interface Graph {
  /** Czy `edges` to ucięty wynik: `total` jest większe niż liczba zwróconych krawędzi. */
  truncated: boolean;
  /** Użyty limit krawędzi (`?limit=`, domyślnie 2000, najwyżej 20000). */
  limit: number;
  /** Liczba krawędzi po filtrach, przed ucięciem. Do wyświetlenia "N z M". */
  total: number;
  total_by_relation: Partial<Record<Relation, number>>;
  returned_by_relation: Partial<Record<Relation, number>>;
  nodes: { id: number; label: string; source: Source; campaign: string | null; operator: string | null; case: string | null; listed: boolean; /** Tylko przy `?campaign=` i `?operator=`: czy reklama należy do tej grupy (false = sąsiad spoza grupy). */ member?: boolean }[];
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
  alerts_unseen: number;
  // Krawędzie według werdyktu (none to bez decyzji) i pozycje kolejki /api/review dla source=capture.
  verdicts: { none: number; confirmed: number; rejected: number; unsure: number };
  review_pending: number;
  cert_pl_listed: number;
  last_analysis: string | null;
}

export type ReviewReason = "challenged" | "changed_after_decision" | "unbacked" | "borderline" | "new_in_group" | "operator_to_confirm" | "campaign_to_confirm" | "content_only" | "other";

export interface ReviewAd {
  id: number;
  external_id: string;
  source: Source;
  title: string;
  // Host z adresu docelowego po redakcji tokenów.
  domain: string;
  first_seen: string | null;
  // Pierwsza kreacja albo zrzut strony; obraz pod `image` (/api/artifacts/{sha256}/image).
  thumbnail: { sha256: string; image: string } | null;
}

export interface ReviewItem {
  id: number;
  relation: Relation;
  probability: number;
  bits: number;
  model_version: string;
  // Wersja krawędzi: ta sama wartość jako edge_version przy decyzji.
  updated_at: string;
  reason: ReviewReason;
  reason_label: string;
  ad_a: ReviewAd;
  ad_b: ReviewAd;
  // Najwyżej 3 najmocniejsze ślady, malejąco po weight_bits. value po redakcji, strona A.
  evidence: {
    kind: string;
    label: string;
    family: Family;
    family_label: string;
    weight_bits: number;
    value: string;
    artifact_a: string | null;
    artifact_b: string | null;
  }[];
  // Zdania o tym, czego krawędź nie dowodzi (może być puste).
  limitations: string[];
}

export type ReviewPage = Page<ReviewItem>;

export interface ReviewParams {
  page?: number;
  // Domyślnie "capture"; "all" bez filtra źródła.
  source?: Source | "all";
  relation?: Relation;
  reason?: ReviewReason;
}

export type AlertKind = "joined_campaign" | "new_campaign_known_operator" | "joined_operator" | "hunt_confirmed";

export interface Alert {
  id: number;
  kind: AlertKind;
  kind_label: string;
  // Alert łowcy domen (hunt_confirmed) nie ma reklamy: ad to null, ad_title pusty, a domena i kandydat są w polach niżej.
  ad: number | null;
  ad_title: string;
  hunt_candidate: number | null;
  domain: string | null;
  campaign: string | null;
  campaign_id: number | null;
  operator: string | null;
  operator_id: number | null;
  description: string;
  // Najwyżej 3 najmocniejsze typy markerów łączące reklamę z grupą, malejąco po bits.
  evidence: { kind: string; label: string; family: Family; bits: number; value: string }[];
  seen: boolean;
  seen_at: string | null;
  created_at: string;
}

// Łowca domen: nowe domeny znanych operatorów z logów Certificate Transparency (crt.sh) i Listy CERT Polska.
export type HuntStatus = "candidate" | "confirmed" | "rejected" | "unavailable";
export type HuntSource = "crtsh" | "cert_pl";

// Ślad wspólny ze stroną kandydata. bits to wkład w sumę (po rabacie rodziny), raw_bits przed rabatem, df liczba źródeł z tą wartością.
export interface HuntEvidence {
  kind: string;
  label: string;
  family: Family;
  bits: number;
  raw_bits: number;
  decisive: boolean;
  value: string;
  df: number;
  ad_ids: number[]; // reklamy operatora, z których wzięto ten ślad
}

export interface HuntCandidate {
  id: number;
  domain: string;
  operator: string; // klucz, np. O-0007
  operator_id: number;
  sources: HuntSource[];
  status: HuntStatus;
  status_label: string;
  prelim_score: number; // 0..1, bez połączenia ze stroną
  score_parts: {
    tokens: { token: string; match: "exact" | "part"; weight: number }[];
    template: string | null;
    issuer: string | null;
  };
  cert: { issuer: string; serial: string; not_before: string | null; crtsh_id: number | null } | null;
  bits: number | null; // po potwierdzeniu przez crawlera
  probability: number | null;
  evidence: HuntEvidence[];
  note: string;
  final_url: string;
  http_status: number | null;
  crawl_error: string;
  html_sha: string; // surowy HTML tylko do pobrania (artifactDownloadUrl), nigdy do renderowania
  screenshot_sha: string; // zrzut strony: artifactImageUrl; pusty, gdy crawler nie dał zrzutu
  attempts: number;
  checked_at: string | null;
  analysis: string | null; // id analizy, gdy domenę zgłoszono do pełnego potoku
  ad: number | null; // reklama powstała z tej analizy
  alert: number | null; // alert hunt_confirmed
  run: string | null;
  created_at: string;
  updated_at: string;
}

export interface HuntPattern {
  type: "name_token" | "name_template" | "cert_issuer" | "marker";
  kind: string | null; // typ markera, gdy type == marker
  label: string;
  value: string;
  role: "search" | "score" | "confirm";
  ad_count: number;
  ad_ids: number[]; // pochodzenie: reklamy operatora (najwyżej 20)
  weight?: number; // tylko name_token; 0 dla zbyt pospolitego
  domains?: string[]; // name_token i name_template: domeny, z których powstał
  other_domains?: number; // name_token: ile obcych domen korpusu zawiera token
  generic?: boolean;
  share?: number;
}

export interface HuntProfile {
  operator: { id: number; key: string; label: string };
  ads: number;
  domains: string[];
  queries: string[]; // tokeny, po których pytamy crt.sh
  patterns: HuntPattern[];
  candidates: Partial<Record<HuntStatus, number>>;
}

export interface HuntRun {
  id: string;
  operator: string | null;
  params: { operator?: number | null; days?: number; max_queries?: number; max_crawl?: number; crawl?: boolean };
  status: "queued" | "running" | "done" | "failed";
  // Po przebiegu: queries_made, queries[{token, ok, certs, domains}], candidates_new, crawled, confirmed, rejected, unavailable, aborted...
  stats: Record<string, unknown>;
  error: string;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface HuntFilter {
  operator?: number | string;
  status?: HuntStatus[];
  source?: HuntSource;
}

export interface Kinds {
  families: { code: Family; label: string }[];
  kinds: { code: string; family: Family; label: string; decisive: boolean; soft: boolean }[];
  verdict_reasons: { value: Exclude<VerdictReason, "unknown">; label: string }[];
}

// Wagi modelu: ekspercka i uczona (EM) każdego typu markera. `learned` jest null bez pliku z wagami.
export interface KindWeights {
  code: string;
  label: string;
  family: Family;
  family_label: string;
  soft: boolean;
  decisive: boolean;
  cap: number;
  expert: { m: number | null; f0: number | null; bits: number };
  learned: {
    source: "em" | "expert";
    m: number;
    u: number;
    u_basis: "population" | "candidates";
    bits: number;
    pairs_agree: number;
    bits_std: number | null;
  } | null;
}

export interface WeightsCalibration {
  fitted: boolean;
  decisions: number;
  confirmed: number;
  rejected: number;
  note?: string;
  coefficients?: { intercept: number; weights: number[]; features: string[]; scale: number };
}

export interface Weights {
  active: "expert" | "learned";
  model_version: string;
  learned_available: boolean;
  learned_error: string | null;
  meta: {
    model_version: string;
    created: string;
    source: string;
    ads: number;
    pairs: number;
    iterations: number;
    converged: boolean;
    stable: boolean;
    unstable_kinds: number;
    learned_kinds: number;
    kinds: number;
    classes: Record<string, { iterations: number; converged: boolean; match_share: number; expected_matches: number }>;
  } | null;
  calibration: WeightsCalibration | null;
  kinds: KindWeights[];
}

// Pamięć sprzeciwu: powód decyzji analityka. "unknown" mają decyzje bez podanego powodu i wszystkie sprzed tej funkcji.
export type VerdictReason =
  | "shared_tool"
  | "shared_infrastructure"
  | "extraction_error"
  | "no_independent_confirmation"
  | "confirmed_by_analyst"
  | "other"
  | "unknown";

// Stan krawędzi z chwili decyzji. Dowody krawędzi są przebudowywane przy przeliczeniu, migawka nie.
export interface DecisionSnapshot {
  relation: Relation;
  bits: number;
  probability: number;
  decisive: boolean;
  duplicate: boolean;
  families: Partial<Record<Family, number>>;
  model_version: string;
  edge_version: string | null;
  evidence: {
    kind: string;
    label: string;
    family: Family;
    family_label: string;
    value_a: string;
    value_b: string;
    similarity: number;
    df: number;
    corpus_n: number;
    weight_bits: number;
    decisive: boolean;
    kit: boolean;
    motif: boolean;
  }[];
  groups: Record<"a" | "b", { campaign: string | null; operator: string | null }>;
  ads: Partial<Record<"a" | "b", { id: number; source: Source; case: string | null; landing_url: string }>>;
}

export interface EdgeDecision {
  id: number;
  edge: number | null;
  ad_a: number | null;
  ad_b: number | null;
  verdict: Exclude<Verdict, "">;
  previous_verdict: Verdict;
  reason: VerdictReason;
  reason_label: string;
  note: string;
  legacy: boolean;
  user: string | null;
  created_at: string;
  has_snapshot: boolean;
  snapshot: DecisionSnapshot | null;
}

export interface PrecedentGroup {
  group: string;
  label: string;
}

// Podobne wcześniejsze rozstrzygnięcie innej pary. Doradczo: nie przesądza o bieżącej krawędzi.
export interface Precedent {
  decision: number;
  edge: number | null;
  ad_a: number | null;
  ad_b: number | null;
  verdict: Exclude<Verdict, "">;
  reason: VerdictReason;
  reason_label: string;
  reason_known: boolean;
  note: string;
  user: string | null;
  created_at: string;
  source: string;
  similarity: number;
  same_relation: boolean;
  relation_then: Relation;
  relation_now: Relation;
  model_then: string;
  shared_groups: PrecedentGroup[];
  only_now: PrecedentGroup[];
  only_then: PrecedentGroup[];
  new_independent: PrecedentGroup[];
  why: string[];
  differences: string[];
  evidence_then: { kind: string; label: string; weight_bits: number }[];
}

// Sugestia Jev dla krawędzi. Tylko odczyt; odpowiedź jest widoczna wyłącznie w trybie "on".
export type AssistStatus =
  | "disabled"
  | "shadow"
  | "none"
  | "ok"
  | "abstain"
  | "unavailable"
  | "timeout"
  | "error"
  | "unauthorized"
  | "payment"
  | "rate_limited";

export interface ReviewPremises {
  relacja: Relation;
  bity: number;
  pewnosc: number;
  rozstrzygajacy_slad: boolean;
  duplikat: boolean;
  grupy_sladow: { grupa: string; slady: number; bity: number; rozstrzygajacy: boolean }[];
  niezalezne_grupy: number;
  niezalezne_grupy_zaplecza: number;
  tylko_silnik_lub_motywy: boolean;
}

export interface EdgeAssist {
  edge: number;
  mode: "off" | "shadow" | "on";
  model: string | null;
  question_version: string;
  question: string | null;
  case_data_allowed: boolean;
  visible: boolean;
  status: AssistStatus;
  suggestion: {
    status: AssistStatus;
    answer: "przeglad" | "spojne" | null;
    label: string | null;
    probabilities: Partial<Record<"przeglad" | "spojne", number>>;
    confidence: number | null;
    uncertain: boolean;
    model: string;
    served_model: string | null;
    question_version: string;
    created_at: string;
    stale: boolean;
    error: string | null;
  } | null;
  shadow?: { recorded_at: string; status: AssistStatus };
  premises: ReviewPremises;
  analyst: { verdict: Verdict; reason: VerdictReason | null; decided_at: string | null };
  precedent_ranking: "not_validated";
  notice: string;
}

export interface Precedents {
  edge: number;
  edge_version: string;
  relation: Relation;
  groups: PrecedentGroup[];
  status: "found" | "none";
  considered: number;
  matching: number;
  skipped_without_snapshot: number;
  limit: number;
  conflict: boolean;
  notice: string;
  precedents: Precedent[];
}

export interface EdgeDecisions {
  edge: number;
  current: Verdict;
  decisions: EdgeDecision[];
}

export interface Page<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

// Opcjonalny klucz zapisu (API_WRITE_KEY w backendzie). Trafia do kodu strony, więc chroni przed zapisem
// z obcych stron i skryptów w sieci, a nie przed kimś, kto ma dostęp do samego interfejsu.
const API_KEY = process.env.NEXT_PUBLIC_API_KEY ?? "";

// Czytelne streszczenie pliku HAR (GET /api/artifacts/{sha256}/har). Bez treści odpowiedzi, adresy po redakcji.
export interface HarEntry {
  n: number;
  method: string;
  host: string;
  path: string;
  url: string;
  status: number; // 0, gdy brak odpowiedzi
  type: string; // dokument, skrypt, styl, obraz, czcionka, dane, wideo, dźwięk, inne
  size: number | null;
  ms: number | null;
  ip: string;
  redirect_to: string;
  main: boolean; // dokument główny strony
  traces: string[]; // kody typów markerów, klucze w trace_labels
}
export interface HarOverview {
  sha256: string;
  download: string;
  total: number;
  page_url: string;
  started_at: string;
  chain: { url: string; status: number }[];
  hosts: { host: string; requests: number }[];
  entries: HarEntry[];
  truncated: boolean;
  with_traces: number;
  trace_labels: Record<string, string>;
}

export class ApiError extends Error {
  constructor(readonly status: number, detail: string) {
    super(`API ${status}: ${detail}`);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const keyHeader: Record<string, string> = API_KEY && init?.method && init.method !== "GET" ? { "X-API-Key": API_KEY } : {};
  const headers = init?.body instanceof FormData
    ? { ...keyHeader, ...(init.headers as Record<string, string> | undefined) }
    : { "Content-Type": "application/json", ...keyHeader, ...(init?.headers as Record<string, string> | undefined) };
  const response = await fetch(`${API_URL}${path}`, { ...init, headers });
  if (!response.ok) {
    const body = await response.text();
    throw new ApiError(response.status, body.slice(0, 300));
  }
  return response.json() as Promise<T>;
}

export const artifactImageUrl = (sha256: string) => `${API_URL}/api/artifacts/${sha256}/image`;
export const artifactDownloadUrl = (sha256: string) => `${API_URL}/api/artifacts/${sha256}`;
// Wzbogacony korpus jako ZIP (reklamy z markerami, krawędzie z dowodami, grupy). source="capture": same materiały spraw.
// Operatorzy i kampanie jako STIX 2.1 do wymiany z zespołami CERT (MISP też go czyta).
export const exportStixUrl = (filter: { operator?: number; campaign?: number } = {}) =>
  `${API_URL}/api/export/stix${filter.operator ? `?operator=${filter.operator}` : filter.campaign ? `?campaign=${filter.campaign}` : ""}`;
export const exportCorpusUrl = (source?: Source) => `${API_URL}/api/export${source ? `?source=${source}` : ""}`;
// Pakiet dowodowy grupy jako ZIP do przekazania dalej (raport do druku, artefakty z sumami SHA-256, STIX, krawędzie, skrypt weryfikacji).
// raw=false pomija surowy HAR i HTML stron oszustów (zostają obrazy i nagrania). Link otwiera pobieranie, to nie jest wywołanie fetch.
export const operatorPackageUrl = (id: number, options: { raw?: boolean } = {}) =>
  `${API_URL}/api/operators/${id}/package${options.raw === false ? "?surowe=0" : ""}`;
export const campaignPackageUrl = (id: number, options: { raw?: boolean } = {}) =>
  `${API_URL}/api/campaigns/${id}/package${options.raw === false ? "?surowe=0" : ""}`;

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
  // edgeVersion (updated_at krawędzi z wczytania): przy zmienionej krawędzi 409. Odpowiedź ma regroup z rozdzieleniem grup.
  setVerdict: (id: number, verdict: Exclude<Verdict, "">, note = "", reason?: Exclude<VerdictReason, "unknown">, edgeVersion?: string) =>
    request<EdgeDetail & { regroup?: Regroup }>(`/api/edges/${id}/verdict`, {
      method: "POST",
      body: JSON.stringify({ verdict, note, ...(reason ? { reason } : {}), ...(edgeVersion ? { edge_version: edgeVersion } : {}) }),
    }),
  edgeDecisions: (id: number) => request<EdgeDecisions>(`/api/edges/${id}/decisions`),
  edgePrecedents: (id: number, limit = 5) => request<Precedents>(`/api/edges/${id}/precedents?limit=${limit}`),
  edgeAssist: (id: number) => request<EdgeAssist>(`/api/edges/${id}/assist`),
  // Laboratorium dowodów: przeliczenie bez wybranych dowodów. Niczego nie zapisuje. 409, gdy krawędź się zmieniła.
  simulateEdge: (id: number, exclude: number[], edgeVersion?: string) =>
    request<Simulation>(`/api/edges/${id}/simulate`, {
      method: "POST",
      body: JSON.stringify({ exclude, ...(edgeVersion ? { edge_version: edgeVersion } : {}) }),
    }),
  // Zakwestionowanie przesłanki. Podgląd niczego nie zapisuje; zapis i przywrócenie przeliczają krawędzie i grupy.
  // 400: ślad miękki albo nieznany rodzaj, 404: żadna reklama nie ma śladu, 409: już zakwestionowany / już przywrócony.
  previewPremise: (kind: string, value: string) =>
    request<PremisePreview>(`/api/premises/preview`, { method: "POST", body: JSON.stringify({ kind, value }) }),
  challengePremise: (kind: string, value: string, reason: string) =>
    request<Premise & { regroup: Regroup }>(`/api/premises`, { method: "POST", body: JSON.stringify({ kind, value, reason }) }),
  restorePremise: (id: number) => request<Premise & { regroup: Regroup }>(`/api/premises/${id}/restore`, { method: "POST" }),
  premises: (status?: "challenged" | "restored") =>
    request<{ count: number; results: Premise[] }>(`/api/premises${status ? `?status=${status}` : ""}`),
  premise: (id: number) => request<Premise>(`/api/premises/${id}`),
  // Czytelne streszczenie HAR. 404, gdy artefakt nie jest plikiem HAR (np. zapis HTML), 422, gdy plik jest uszkodzony.
  harOverview: (sha256: string) => request<HarOverview>(`/api/artifacts/${sha256}/har`),
  // Dwie twarze jednego linku: obserwacja strony reklamy i strony do porównania; porównanie tylko do odczytu.
  adObservations: (id: number) => request<AdObservations>(`/api/ads/${id}/observations`),
  compareObservations: (a: number, b: number) => request<ObservationComparison>(`/api/observations/compare?a=${a}&b=${b}`),
  // Test najsłabszego ogniwa: najmniejsze zestawy grup śladów, których utrata zmienia relację. Niczego nie zapisuje.
  weakestLink: (id: number, params: { max_group_size?: 1 | 2; max_scenarios?: number; time_limit_ms?: number; edge_version?: string } = {}) =>
    request<WeakestLink>(`/api/edges/${id}/weakest-link`, { method: "POST", body: JSON.stringify(params) }),
  // Co sprawdzić dalej: wskazówki z brakujących dowodów pary, bez zapytań na zewnątrz.
  edgeSuggestions: (id: number) => request<Suggestions>(`/api/edges/${id}/suggestions`),
  // source: np. "capture", żeby zostawić grupy z materiałów spraw (bez samych reklam z bibliotek)
  campaigns: (source?: string) => request<Page<GroupListItem>>(`/api/campaigns${source ? `?source=${source}` : ""}`),
  campaign: (id: number) => request<GroupDetail>(`/api/campaigns/${id}`),
  operators: (source?: string) => request<Page<GroupListItem>>(`/api/operators${source ? `?source=${source}` : ""}`),
  operator: (id: number) => request<OperatorDetail>(`/api/operators/${id}`),
  campaignTimeline: (id: number) => request<Timeline>(`/api/campaigns/${id}/timeline`),
  operatorTimeline: (id: number) => request<Timeline>(`/api/operators/${id}/timeline`),
  // Filtry: ?campaign=ID, ?operator=ID, ?ad=ID, ?relation=same_campaign,same_operator, ?limit=
  graph: (query = "") => request<Graph>(`/api/graph${query}`),
  kinds: () => request<Kinds>("/api/kinds"),
  weights: () => request<Weights>("/api/weights"),
  stats: () => request<Stats>("/api/stats"),
  // Kolejka "Do oceny": krawędzie bez werdyktu z powodem uwagi, od najpilniejszych.
  review: (params: ReviewParams = {}) => {
    const query = new URLSearchParams();
    for (const [key, value] of Object.entries(params)) if (value !== undefined && value !== "") query.set(key, String(value));
    const text = query.toString();
    return request<ReviewPage>(`/api/review${text ? `?${text}` : ""}`);
  },
  // Alerty: nowy materiał w znanej kampanii albo u znanego operatora. unseenOnly zostawia nieprzejrzane.
  alerts: (unseenOnly = false, page = 1) => {
    const query = new URLSearchParams();
    if (unseenOnly) query.set("unseen", "1");
    if (page > 1) query.set("page", String(page));
    return request<Page<Alert>>(`/api/alerts${query.size ? "?" + query : ""}`);
  },
  markAlertSeen: (id: number, seen = true) =>
    request<Alert>(`/api/alerts/${id}/seen`, { method: "POST", body: JSON.stringify({ seen }) }),
  // Łowca domen. Lista: potwierdzeni pierwsi, potem po wyniku wstępnym.
  hunt: (filter: HuntFilter = {}) => {
    const query = new URLSearchParams();
    if (filter.operator !== undefined) query.set("operator", String(filter.operator));
    if (filter.status?.length) query.set("status", filter.status.join(","));
    if (filter.source) query.set("source", filter.source);
    const text = query.toString();
    return request<Page<HuntCandidate>>(`/api/hunt${text ? `?${text}` : ""}`);
  },
  huntProfile: (operatorId: number) => request<HuntProfile>(`/api/operators/${operatorId}/hunt-profile`),
  // Start przebiegu w tle; 409 (z danymi trwającego przebiegu w treści błędu), gdy poprzedni jeszcze trwa.
  huntRun: (options: { operator?: number | null; days?: number; max_queries?: number; max_crawl?: number; crawl?: boolean } = {}) =>
    request<HuntRun>("/api/hunt/run", { method: "POST", body: JSON.stringify(options) }),
  huntRuns: () => request<Page<HuntRun>>("/api/hunt/runs"),
  huntRunStatus: (id: string) => request<HuntRun>(`/api/hunt/runs/${id}`),
  // Zgłoszenie domeny do pełnej analizy (potok jak przy createAnalysis); 409, gdy już zgłoszona.
  analyzeHuntCandidate: (id: number) => request<Analysis>(`/api/hunt/${id}/analyze`, { method: "POST" }),
};

// Strumień postępu analizy. Zdarzenia przychodzą w kolejności, w jakiej backend je zapisał.
export function streamAnalysis(
  analysis: Pick<Analysis, "events_url">,
  onEvent: (event: AnalysisEvent) => void,
  onClose: (reason: "complete" | "interrupted") => void,
): () => void {
  const source = new EventSource(`${API_URL}${analysis.events_url}`);
  const stages: AnalysisEvent["stage"][] = ["ingest", "crawl", "extract", "enrich", "fuse", "cluster", "end"];
  for (const stage of stages) {
    source.addEventListener(stage, (message) => onEvent(JSON.parse((message as MessageEvent).data)));
  }
  const finish = (reason: "complete" | "interrupted") => {
    source.close();
    onClose(reason);
  };
  source.addEventListener("close", () => finish("complete"));
  source.onerror = () => finish("interrupted");
  return () => source.close();
}
