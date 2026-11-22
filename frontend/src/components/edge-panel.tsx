"use client";

import { ContentSimilarity } from "./content-similarity";

// Panel dowodów krawędzi: z czego wynika połączenie dwóch reklam. Najważniejszy ekran aplikacji.
// Wszystko pochodzi z GET /api/edges/{id}; zrzuty reklam z GET /api/ads/{id}.

import { Check, ChevronDown, ChevronRight, Download, HelpCircle, Info, X } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import Link from "next/link";
import { EdgeSuggestions } from "./edge-suggestions";
import { JevReview } from "./jev-review";
import { DecisionHistory } from "./decision-history";
import type { Regroup, ReviewItem, VerdictReason } from "@/lib/api";
import { PremiseChallenge } from "./premise-challenge";
import { EvidenceLab } from "./evidence-lab";
import { useRef, useState } from "react";

import { api, ApiError, artifactDownloadUrl, artifactImageUrl, type AdDetail, type AdSummary, type EdgeDetail, type Evidence, type Verdict } from "@/lib/api";
import { SOURCE_LABELS, reviewReasonLabel, utcEdgeVersion, markerValue, RELATION_HINT, adTitle, bits, dateTime, errorText, famVar, hostOf, num, plural } from "@/lib/format";
import { isTyping, useApi, useHotkey } from "@/lib/hooks";
import { useExpert } from "@/lib/expert";
import { hypothesisSentence, isHardTrace, overallStrength, plainLimitation, rarityWords, STRENGTH_LABELS, traceStrength, type Strength } from "@/lib/hypothesis";

import { Btn, Empty, ErrorBox, FamilyBar, FamilyDot, GroupLink, Kbd, Loading, Meter, Mono, RelationTag, Tag, VerdictTag } from "./ui";

const VISUAL_KINDS = new Set(["creative_phash", "creative_sha256", "image_set"]);
const CAUTION_REASONS = new Set<ReviewItem["reason"]>(["challenged", "unbacked", "borderline"]);
const zrodel = (n: number) => plural(n, "źródle", "źródłach", "źródłach");

function Creative({ sha, label, height = "h-28" }: { sha: string; label: string; height?: string }) {
  const [broken, setBroken] = useState(false);
  if (broken) return <div className={`flex ${height} items-center justify-center rounded border border-line text-faint`}>zrzut niedostępny</div>;
  return (
    <a href={artifactImageUrl(sha)} target="_blank" rel="noreferrer" title="Otwórz zrzut reklamy w nowej karcie" className="block overflow-hidden rounded border border-line bg-bg">
      {/* eslint-disable-next-line @next/next/no-img-element -- obraz z API dowodów, bez optymalizacji po stronie Next */}
      <img src={artifactImageUrl(sha)} alt={label} loading="lazy" onError={() => setBroken(true)} className={`${height} w-full object-contain`} />
    </a>
  );
}

function AdSide({ ad, detail, side, onOpenAd, large }: { ad: AdSummary; detail?: AdDetail; side: "A" | "B"; onOpenAd?: (id: number) => void; large?: boolean }) {
  const { expert } = useExpert();
  const creative = detail?.creatives[0];
  const domain = hostOf(ad.landing_url);
  const imageHeight = large ? "h-44" : "h-28";
  return (
    <div className="flex min-w-0 flex-1 flex-col gap-1.5 p-3">
      <div className="flex flex-wrap items-center gap-1.5">
        <Tag>Materiał {side}</Tag>
        {expert && <Mono className="text-muted">#{ad.id}</Mono>}
        {ad.case && <span className="text-muted">sprawa {ad.case}</span>}
        {"cert_pl" in ad.labels && <Tag tone="rejected" title="Domena jest na Liście Ostrzeżeń CERT Polska">CERT</Tag>}
      </div>
      <p className="break-words text-base font-semibold" title={ad.landing_url}>{domain || "brak adresu"}</p>
      <p className="break-words sm:line-clamp-2 sm:min-h-[2.8em]" title={ad.title}>
        {adTitle(ad)}
      </p>
      <p className="text-xs text-muted">{SOURCE_LABELS[ad.source] ?? ad.source} · {dateTime(ad.first_seen) || "Brak daty obserwacji"}</p>
      {expert ? <div className="flex items-center gap-2 text-xs">
        <GroupLink group={ad.campaign} />
        <GroupLink group={ad.operator} />
      </div> : <p className="flex flex-wrap items-center gap-x-3 text-xs text-muted">
        {ad.campaign ? <span className="whitespace-nowrap">Kampania <GroupLink group={ad.campaign} /></span> : <span className="whitespace-nowrap">Bez kampanii</span>}
        {ad.operator ? <span className="whitespace-nowrap">Operator <GroupLink group={ad.operator} /></span> : <span className="whitespace-nowrap">Bez operatora</span>}
      </p>}
      {creative ? <Creative sha={creative} label={`Zrzut reklamy ${side}`} height={imageHeight} /> : <div className={`flex ${imageHeight} items-center justify-center rounded border border-dashed border-line text-faint`}>{detail ? "brak zrzutu reklamy" : "…"}</div>}
      {onOpenAd ? (
        <Btn variant="ghost" className="self-start px-0! text-accent!" onClick={() => onOpenAd(ad.id)}>
          Otwórz źródło
        </Btn>
      ) : (
        <Link href={`/ads/${ad.id}`} className="self-start text-accent hover:underline">
          Otwórz źródło
        </Link>
      )}
    </div>
  );
}

const STRENGTH_TONE: Record<Strength, string> = {
  decisive: "border-accent bg-accent-soft text-accent",
  strong: "border-accent text-accent",
  medium: "border-line-strong text-fg",
  weak: "border-line text-muted",
};

function StrengthPill({ item }: { item: Evidence }) {
  const strength = traceStrength(item);
  return <span className={`inline-flex shrink-0 items-center rounded-full border px-2 py-0.5 text-xs whitespace-nowrap ${STRENGTH_TONE[strength]}`}>{STRENGTH_LABELS[strength]}</span>;
}

// Wartość pokazujemy w trybie prostym tylko tam, gdzie analityk ją rozumie bez słownika (osoba, marka, treść).
const READABLE_FAMILIES = new Set(["pers", "narr"]);

// Karta dowodu. Tryb prosty: nazwa śladu, siła i rzadkość słowem. Tryb ekspercki: wartości, bity, df, artefakty.
function EvidenceCard({ item, max, refresh, more = 0 }: { item: Evidence; max: number; refresh: () => void; more?: number }) {
  const { expert } = useExpert();
  const [open, setOpen] = useState(false);
  const soft = item.df === 0;
  const same = item.value_a === item.value_b;
  const left = markerValue(item.value_a, item.display_value);
  const right = same ? left : markerValue(item.value_b);
  const discounted = item.raw_bits - item.weight_bits > 0.05;
  const challengeable = expert ? !soft : isHardTrace(item);
  return (
    <li className="border-b border-line">
      {expert ? <button type="button" onClick={() => setOpen(!open)} aria-expanded={open} className="grid min-h-9 w-full grid-cols-[12px_minmax(0,1fr)] sm:grid-cols-[12px_minmax(0,1fr)_auto] items-center gap-x-2 px-2 py-1 text-left hover:bg-hover">
        {open ? <ChevronDown size={12} className="text-muted" /> : <ChevronRight size={12} className="text-muted" />}
        <span className="flex min-w-0 flex-col">
          <span className="flex flex-wrap items-center gap-1.5">
            <FamilyDot family={item.family} />
            <span className="break-words">{item.label}</span>
            {item.decisive && <Tag tone="accent" title="Rzadki marker rozstrzygający: sam wystarcza do stwierdzenia wspólnego źródła">rozstrzyga</Tag>}
          </span>
          {soft ? (
            <span className="text-muted">
              podobieństwo <Mono className="text-fg">{num(item.similarity, 2)}</Mono>
            </span>
          ) : (
            <Mono className="break-all text-muted" title={same ? left : `${left} | ${right}`}>
              {same ? left : `${left} | ${right}`}
            </Mono>
          )}
        </span>
        <span className="col-start-2 flex flex-wrap items-center gap-x-3 sm:col-start-auto sm:flex-col sm:items-end">
          <span className="flex items-center gap-2">
            <span className="h-1.5 w-14 bg-line">
              <span className="block h-full" style={{ width: `${Math.min(100, (item.weight_bits / max) * 100)}%`, background: famVar(item.family) }} />
            </span>
            <Mono className="w-[3.2em] text-right">{bits(item.weight_bits)}</Mono>
            <span className="text-faint">bita</span>
          </span>
          <span className="text-xs text-muted">{soft ? "marker miękki" : `w ${item.df} z ${item.corpus_n} źródeł`}</span>
        </span>
      </button> : <button type="button" onClick={() => setOpen(!open)} aria-expanded={open} className="grid w-full grid-cols-[12px_minmax(0,1fr)_auto] items-start gap-x-2 px-3 pt-2.5 pb-1 text-left hover:bg-hover">
        {open ? <ChevronDown size={12} className="mt-1.5 text-muted" /> : <ChevronRight size={12} className="mt-1.5 text-muted" />}
        <span className="flex min-w-0 flex-col gap-0.5">
          <span className="flex items-center gap-2 font-medium"><FamilyDot family={item.family} /><span className="break-words">{item.label}</span></span>
          <span className="text-xs text-muted">{rarityWords(item.df, item.corpus_n)}{!soft && READABLE_FAMILIES.has(item.family) && left && <> · <span className="text-fg">{left}</span></>}{more > 0 && ` · i jeszcze ${more} ${plural(more, "wartość", "wartości", "wartości")}`}</span>
        </span>
        <StrengthPill item={item} />
      </button>}
      <div className={`flex flex-wrap items-center gap-x-4 gap-y-1 text-xs ${expert ? "px-2 pb-1" : "px-3 pb-2.5 pl-8"}`}>
        {([["A", item.artifact_a], ["B", item.artifact_b]] as const).map(([side, sha]) =>
          sha ? (
            <a key={side} href={artifactDownloadUrl(sha)} className="inline-flex items-center gap-1 text-accent hover:underline" title="Surowy dowód jako plik. Nigdy nie renderuje się w przeglądarce.">
              <Download size={12} />
              Sprawdź źródło {side} {expert && <Mono className="text-muted">{sha.slice(0, 12)}</Mono>}
            </a>
          ) : expert ? (
            <span key={side} className="text-faint">
              {side} · brak pliku źródłowego
            </span>
          ) : null,
        )}
        {challengeable && !expert && <PremiseChallenge item={item} refresh={refresh} inline />}
      </div>
      {challengeable && expert && <PremiseChallenge item={item} refresh={refresh}/>}
      {expert && <ContentSimilarity kind={item.kind} similarity={item.similarity} />}

      <AnimatePresence initial={false}>
        {open && (
          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.15 }} className="overflow-hidden bg-bg">
            <div className="flex flex-col gap-2 px-2 py-2 pl-7">
              {!expert ? (
                soft ? <p className="text-muted">Ten ślad porównuje podobieństwo treści, a nie jedną wartość. Samo podobieństwo nie dowodzi wspólnego zaplecza.</p> : <>
                  <div className="grid grid-cols-2 gap-2">
                    {(["a", "b"] as const).map((side) => (
                      <div key={side} className="min-w-0">
                        <p className="cap">Materiał {side.toUpperCase()}</p>
                        <Mono className="break-all">{side === "a" ? left : right}</Mono>
                      </div>
                    ))}
                  </div>
                  <p className="text-muted">{same ? "Ta sama wartość po obu stronach" : "Wartości różnią się zapisem, ale oznaczają to samo"}; {rarityWords(item.df, item.corpus_n)}.</p>
                </>
              ) : soft ? (
                <p className="text-muted">
                  Marker miękki porównywany przez podobieństwo, nie przez równość wartości. Podobieństwo <Mono className="text-fg">{num(item.similarity, 3)}</Mono>.
                </p>
              ) : (
                <div className="grid grid-cols-2 gap-2">
                  {(["a", "b"] as const).map((side) => (
                    <div key={side} className="min-w-0">
                      <p className="cap">Strona {side.toUpperCase()}</p>
                      <Mono className="break-all">{side === "a" ? left : right}</Mono>
                    </div>
                  ))}
                  <p className="col-span-2 text-muted">
                    {same ? "Wartości identyczne po obu stronach." : "Wartości różnią się zapisem, marker uznał je za zgodne."} Ta wartość występuje w <Mono className="text-fg">{item.df}</Mono> z{" "}
                    <Mono className="text-fg">{item.corpus_n}</Mono> niezależnych {zrodel(item.corpus_n)} korpusu (źródło to kampania albo reklama bez kampanii).
                  </p>
                </div>
              )}
              {VISUAL_KINDS.has(item.kind) && <div className="grid grid-cols-2 gap-2">
                {([["A", item.artifact_a], ["B", item.artifact_b]] as const).map(([side, sha]) => sha
                  ? <Creative key={side} sha={sha} label={`Artefakt dowodu · ${side}`} />
                  : <p key={side} className="text-muted">{side} · Brak artefaktu dowodu</p>)}
              </div>}
              {expert && <p className="text-muted">
                Wkład <Mono className="text-fg">{bits(item.weight_bits)}</Mono> bita
                {discounted && (
                  <>
                    {" "}
                    (waga surowa <Mono className="text-fg">{bits(item.raw_bits)}</Mono> bita, obniżona za korelację w rodzinie: kolejny marker tej samej rodziny liczy się połowę słabiej)
                  </>
                )}
                . Typ markera: <Mono>{item.kind}</Mono>.
                {" "}<Link className="text-accent underline" href={`/weights?kind=${encodeURIComponent(item.kind)}`}>Sprawdź wagi tego markera</Link>
              </p>}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </li>
  );
}

const DECISIONS: { verdict: Exclude<Verdict, "">; label: string; key: string; icon: typeof Check }[] = [
  { verdict: "confirmed", label: "Potwierdź", key: "P", icon: Check },
  { verdict: "unsure", label: "Do wyjaśnienia", key: "N", icon: HelpCircle },
  { verdict: "rejected", label: "Odrzuć", key: "O", icon: X },
];

function Decision({ edge, onSaved, refresh }: { edge: EdgeDetail; refresh: () => void; onSaved: (edge: EdgeDetail & { regroup?: Regroup }) => void }) {
  const footer = useRef<HTMLElement>(null);
  const { expert } = useExpert();
  const reasons = useApi("verdict-reasons", api.kinds);
  const storageKey = `atlas:decision:${edge.id}:${edge.updated_at}`;
  const savedReason = edge.verdict_reason && edge.verdict_reason !== "unknown" ? edge.verdict_reason : "";
  type Draft = { selected: Verdict; note: string; reason: Exclude<VerdictReason, "unknown"> | "" };
  const savedDraft: Draft = { selected: edge.verdict, note: edge.verdict_note, reason: savedReason };
  const [draft, setDraft] = useState<Draft>(() => {
    try {
      const carryKey = `atlas:decision:${edge.id}:carry`;
      const raw = sessionStorage.getItem(storageKey) ?? sessionStorage.getItem(carryKey);
      sessionStorage.removeItem(carryKey);
      const stored = raw && JSON.parse(raw);
      if (stored && typeof stored.note === "string" && typeof stored.reason === "string" &&
        ["", ...DECISIONS.map(d => d.verdict)].includes(stored.selected)) return stored;
    } catch { /* Storage can be unavailable in private browsing. */ }
    return savedDraft;
  });
  const { reason, selected, note } = draft;
  const dirty = selected !== edge.verdict || note !== edge.verdict_note || reason !== savedReason;
  function edit(change: Partial<Draft>) {
    const next = { ...draft, ...change };
    setDraft(next);
    try { sessionStorage.setItem(storageKey, JSON.stringify(next)); } catch { /* Keep the in-memory draft. */ }
  }
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  function discardDraft() {
    setDraft(savedDraft);
    setError("");
    try { sessionStorage.removeItem(storageKey); } catch { /* Keep the reset in memory. */ }
  }

  const [stale, setStale] = useState(false);
  async function decide(verdict: Exclude<Verdict, "">) {
    setBusy(true);
    setError("");
    try {
      const saved = await api.setVerdict(edge.id, verdict, note, reason || undefined, utcEdgeVersion(edge.updated_at));
      try { sessionStorage.removeItem(storageKey); } catch { /* Storage unavailable. */ }
      onSaved(saved);
    } catch (reason) {
      if (reason instanceof ApiError && reason.status === 409) {
        // Szkic przechodzi na nową wersję krawędzi po odświeżeniu danych.
        try { sessionStorage.setItem(`atlas:decision:${edge.id}:carry`, JSON.stringify(draft)); } catch { /* Szkic zostanie tylko w pamięci. */ }
        setStale(true);
      }
      else setError(errorText(reason));
    } finally {
      setBusy(false);
    }
  }

  useHotkey((event) => {
    if (event.repeat || isTyping(event) || event.ctrlKey || event.metaKey || event.altKey || busy || stale) return;
    // Enter zapisuje wybraną ocenę, gdy fokus nie stoi na innym przycisku ani linku.
    const target = event.target as HTMLElement | null;
    if (event.key === "Enter" && (!target || target === document.body || target.dataset.decision) && dirty && selected && footer.current?.getClientRects().length) {
      event.preventDefault();
      decide(selected);
      return;
    }
    const decision = DECISIONS.find((d) => d.key.toLowerCase() === event.key.toLowerCase());
    if (decision && footer.current?.getClientRects().length) edit({ selected: decision.verdict });
  });

  const [notesOpen, setNotesOpen] = useState(() => Boolean(draft.note || draft.reason));
  const tones: Record<Exclude<Verdict, "">, string> = {
    confirmed: "aria-pressed:border-confirmed aria-pressed:bg-confirmed/10 aria-pressed:text-confirmed",
    unsure: "aria-pressed:border-unsure aria-pressed:bg-unsure/10 aria-pressed:text-unsure",
    rejected: "aria-pressed:border-rejected aria-pressed:bg-rejected/10 aria-pressed:text-rejected",
  };

  return (
    <footer ref={footer} className="shrink-0 border-t border-line bg-panel px-3 py-2.5">
      <div className="flex items-center justify-between gap-2 pb-2">
        {expert ? <span className="cap">Twoja ocena powiązania</span> : <span className="font-medium">Twoja ocena<span className="hidden sm:inline">: czy hipoteza się zgadza?</span></span>}
        <span className="flex items-center gap-2 text-xs text-muted">
          <span role="status">{busy ? "Zapisywanie…" : dirty ? (selected ? "Wybrano, teraz zapisz ocenę" : "Szkic") : edge.verdict ? "Zapisana ocena" : expert ? "Do oceny" : ""}</span>
          {(expert || edge.verdict) && <VerdictTag verdict={edge.verdict} />}
          {expert && edge.verdict_at && <Mono>{dateTime(edge.verdict_at)}</Mono>}
        </span>
      </div>
      <div className="grid grid-cols-3 gap-2">
        {DECISIONS.map(({ verdict, label, key, icon: Icon }) => (
          <button key={verdict} type="button" data-decision={verdict} disabled={busy || stale} aria-pressed={selected === verdict} onClick={() => edit({ selected: verdict })}
            className={`flex min-h-11 items-center justify-center gap-1.5 rounded-md border-2 border-line-strong bg-raised px-1.5 text-sm leading-tight font-medium transition-colors hover:bg-hover disabled:opacity-40 sm:gap-2 sm:text-base ${tones[verdict]}`}>
            <Icon size={18} aria-hidden className="shrink-0" />
            {label}
            <span className="hidden sm:inline-flex"><Kbd>{key}</Kbd></span>
          </button>
        ))}
      </div>
      {notesOpen && <div className="mt-2 grid gap-2">
        <label className="flex flex-wrap items-center gap-2">Powód decyzji
          <select className="max-w-full min-w-0 flex-1 rounded-sm border border-line bg-panel p-1" value={reason}
            disabled={!reasons.data?.verdict_reasons?.length || busy}
            onChange={event => edit({ reason: event.target.value as typeof reason })}>
            <option value="">{reasons.loading ? "Pobieranie powodów…" : reasons.data?.verdict_reasons?.length ? "Bez podanego powodu" : "Lista powodów niedostępna"}</option>
            {reasons.data?.verdict_reasons?.map(item => <option key={item.value} value={item.value}>{item.label}</option>)}
          </select>
        </label>
        <label className="block">Uzasadnienie<textarea disabled={busy}
          value={note}
          onChange={(event) => edit({ note: event.target.value })}
          rows={2}
          placeholder="Opcjonalne. Trafia do dziennika audytu razem z decyzją."
          className="mt-1 w-full resize-none rounded-sm border border-line bg-bg px-2 py-1 outline-none placeholder:text-faint focus:border-accent"
        /></label>
      </div>}
      <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-2">
        <button type="button" aria-expanded={notesOpen} onClick={() => setNotesOpen(!notesOpen)} className="text-accent hover:underline">
          {notesOpen ? "Ukryj uzasadnienie" : note || reason ? "Uzasadnienie dodane, pokaż" : "Dodaj uzasadnienie"}
        </button>
        {expert && <span className="text-xs text-muted" title={edge.updated_at}>Wersja dowodów · {dateTime(edge.updated_at)}</span>}
        <span className="ml-auto flex items-center gap-3">
          {dirty && <button type="button" disabled={busy} onClick={discardDraft} className="text-muted underline hover:text-fg">Cofnij</button>}
          <button type="button" title="Skrót: Enter" disabled={!dirty || !selected || busy || stale} onClick={() => selected && decide(selected)}
            className="min-h-10 rounded-md border border-accent bg-accent px-4 font-medium text-on-accent transition hover:brightness-110 disabled:border-line-strong disabled:bg-raised disabled:text-muted">Zapisz ocenę</button>
        </span>
      </div>
      {stale && <p role="alert" className="mt-2 rounded border border-unsure p-2">Dowody tej pary zmieniły się od wczytania (np. po zakwestionowaniu przesłanki), więc ocena nie została zapisana. <button className="text-accent underline" onClick={refresh}>Odśwież dane</button> i oceń ponownie.</p>}
      {error && <p className="pt-1 text-rejected">Decyzja nie została zapisana: {error}</p>}
    </footer>
  );
}

export function EdgePanel({ edgeId, onOpenAd, onVerdict, review }: { edgeId: number; review?: ReviewItem; onOpenAd?: (id: number) => void; onVerdict?: (edge: EdgeDetail & { regroup?: Regroup }) => void }) {
  const [tab, setTab] = useState("Dowody");
  const [showAll, setShowAll] = useState(false);
  const [result, setResult] = useState("");
  const [section, setSection] = useState<string | null>(null);
  const toggle = (name: string) => setSection(current => current === name ? null : name);
  const { expert } = useExpert();
  const edge = useApi(`edge:${edgeId}`, () => api.edge(edgeId));
  const data = edge.data;
  const adA = useApi(data ? `ad:${data.ad_a}` : null, () => api.ad(data!.ad_a));
  const adB = useApi(data ? `ad:${data.ad_b}` : null, () => api.ad(data!.ad_b));

  if (edge.loading) return <Loading label={expert ? "Pobieranie dowodów krawędzi" : "Wczytywanie pary i jej przesłanek"} />;
  if (edge.error) return <ErrorBox message={edge.error} onRetry={edge.reload} missing={edge.status === 404 ? {
    description: expert ? `Nie znaleziono krawędzi #${edgeId}.` : "Nie znaleziono tej pary. Mogła zniknąć po ponownym przeliczeniu powiązań.",
    href: "/review",
    link: "Przejdź do kolejki ocen",
  } : undefined} />;
  if (!data) return null;

  const evidence = [...data.evidence].sort((a, b) => b.weight_bits - a.weight_bits);
  const max = Math.max(1, ...evidence.map((e) => e.weight_bits));
  // Tryb prosty: jeden wiersz na rodzaj śladu (najmocniejsza wartość), reszta jako liczba podobnych wartości.
  const repeats = new Map<string, number>();
  for (const item of evidence) repeats.set(item.label, (repeats.get(item.label) ?? -1) + 1);
  const listed = expert ? evidence : evidence.filter((item, index) => evidence.findIndex(other => other.label === item.label) === index);
  const sources = expert ? evidence : evidence.filter((item, index) => evidence.findIndex(other => other.label === item.label && other.artifact_a === item.artifact_a && other.artifact_b === item.artifact_b) === index);
  const [a, b] = [data.ads.find((ad) => ad.id === data.ad_a) ?? data.ads[0], data.ads.find((ad) => ad.id === data.ad_b) ?? data.ads[1]];
  const crossDomain = a && b && hostOf(a.landing_url) && hostOf(b.landing_url) && hostOf(a.landing_url) !== hostOf(b.landing_url);
  // Ostrożne brzmienie, gdy kolejka wskazuje słabe podstawy albo wynik modelu jest poniżej progu relacji.
  const cautious = data.probability < 0.9 || (!!review && CAUTION_REASONS.has(review.reason));
  const sentence = hypothesisSentence(data.relation, evidence, { duplicate: data.duplicate, crossDomain: !!crossDomain, cautious });
  const strength = overallStrength(data.probability, data.decisive);

  const decision = (
    <Decision
        key={`${data.id}:${data.updated_at}:${data.verdict_at}`}
        refresh={edge.reload}
        edge={data}
        onSaved={(saved) => {
          setResult(regroupMessage(saved.regroup));
          edge.set(saved);
          onVerdict?.(saved);
        }}
      />
  );
  return (
    <div className="flex h-full min-h-0 min-w-0 flex-col">
      <div className={review ? "min-h-0 flex-1 overflow-auto lg:grid lg:grid-cols-2 lg:overflow-hidden" : "min-h-0 flex-1 overflow-auto"}>
        <div className={review ? "lg:min-h-0 lg:overflow-auto lg:border-r lg:border-line" : undefined}>
        {!expert && <div className="flex flex-col gap-2 border-b border-line p-3">
          <h2 className="cap">Hipoteza modelu</h2>
          <p className="text-base leading-snug font-medium text-balance sm:text-lg">{sentence}</p>
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <span className="rounded-full border border-line bg-bg px-2 py-0.5" title="Linia przy nazwie pokazuje, jak ta relacja jest rysowana w grafie">
              <RelationTag relation={data.relation} duplicate={data.duplicate} />
            </span>
            <span className={`rounded-full border px-2 py-0.5 ${strength.tone === "confirmed" ? "border-confirmed text-confirmed" : strength.tone === "unsure" ? "border-unsure text-unsure" : "border-line-strong text-muted"}`}>{strength.label}</span>
            {review && <span className="text-muted">Do oceny, bo: {(l => l.charAt(0).toLowerCase() + l.slice(1))(reviewReasonLabel(review.reason, review.reason_label, false))}</span>}
          </div>
        </div>}
        {expert && <div className="flex flex-col gap-2 border-b border-line p-2">
          <h2 className="text-lg font-semibold">Hipoteza modelu</h2>
          {review && <span className="text-xs text-muted">Do oceny · {review.reason_label}</span>}
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="flex items-center gap-2 text-[1.08rem] font-medium">
              <span className="text-muted">Relacja</span>
              <span className="rounded border border-line bg-bg px-2 py-0.5" title="Linia przy nazwie pokazuje, jak ta relacja jest rysowana w grafie">
                <RelationTag relation={data.relation} duplicate={data.duplicate} />
              </span>
            </span>
            <Mono className="text-muted">Powiązanie #{data.id}</Mono>
          </div>
          <p className="text-muted">
            {RELATION_HINT[data.relation]}
            {data.duplicate && ". Duplikat: ta sama strona przechwycona ponownie"}
            {crossDomain && !data.duplicate && data.relation !== "similar" && ". Reklamy prowadzą do różnych domen"}.
          </p>
          <div className="flex flex-wrap items-center gap-x-5 gap-y-1">
            <span className="flex items-center gap-2">
              <span className="text-muted">wynik modelu (niekalibrowany)</span>
              <Meter value={data.probability} width={96} />
            </span>
            <span>
              <span className="text-muted">suma dowodów</span> <Mono>{bits(data.bits)}</Mono> <span className="text-faint">bita</span>
            </span>
            <span>
              <span className="text-muted">dowody</span> <Mono>{evidence.length}</Mono>
            </span>
            {data.decisive && <Tag tone="accent">marker rozstrzygający</Tag>}
          </div>
          <FamilyBar families={data.families} legend />
        </div>}

        <div className="grid grid-cols-1 divide-y divide-line border-b border-line sm:grid-cols-2 sm:divide-x sm:divide-y-0">
          {a && <AdSide ad={a} detail={adA.data} side="A" onOpenAd={onOpenAd} large={!!review} />}
          {b && <AdSide ad={b} detail={adB.data} side="B" onOpenAd={onOpenAd} large={!!review} />}
        </div>

        </div>
        <div className={review ? "lg:min-h-0 lg:overflow-auto" : undefined}>
        <div className="flex gap-2 border-b border-line px-2" aria-label="Widok pary">{["Dowody", "Źródła", "Kontekst"].map(t =>
          <button key={t} aria-pressed={tab === t} className="min-h-10 px-2 aria-pressed:border-b-2 aria-pressed:border-accent" onClick={() => setTab(t)}>{t}</button>)}</div>
        {tab === "Kontekst" && <>        <DecisionHistory open={section === "history"} onToggle={() => toggle("history")} edge={data} />
        <JevReview open={section === "jev"} onToggle={() => toggle("jev")} key={`jev-${data.id}`} edge={data} />
        <EdgeSuggestions open={section === "suggestions"} onToggle={() => toggle("suggestions")} key={`suggestions-${data.id}`} edgeId={data.id} />
        <EvidenceLab open={section === "lab"} onToggle={() => toggle("lab")} key={data.id + ":" + data.updated_at} edge={data} refresh={edge.reload} />
</>}
        {tab === "Źródła" && <ul className="grid gap-2 p-3">{sources.map(item => <li key={item.id}><strong>{item.label}</strong> · {([["A", item.artifact_a], ["B", item.artifact_b]] as const).map(([side,sha]) => sha ? <a className="mr-2 text-accent underline" key={side} href={artifactDownloadUrl(sha)} download>Sprawdź źródło {side}</a> : <span className="mr-2 text-muted" key={side}>{side} · brak pliku</span>)}</li>)}</ul>}
        {tab === "Dowody" && <>        <div className="flex flex-wrap items-baseline justify-between gap-x-2 gap-y-1 border-b border-line px-2 py-1">
          <span className="cap">Co uzasadnia tę hipotezę</span>
          {expert ? <span className="text-xs text-faint">wersja modelu oceny powiązań · {data.model_version}</span>
            : <span className="text-xs text-muted">najważniejsze najpierw</span>}
        </div>
        {evidence.length === 0 ? (
          <Empty title="Krawędź nie ma zapisanych dowodów">To nie powinno się zdarzyć: silnik nie tworzy krawędzi bez dowodów. Zgłoś identyfikator krawędzi.</Empty>
        ) : (
          <ul>
            {(showAll ? listed : listed.slice(0, 3)).map((item, index) => (
              <EvidenceCard key={`${item.kind}:${item.value_a}:${index}`} item={item} max={max} refresh={edge.reload} more={expert ? 0 : repeats.get(item.label) ?? 0} />
            ))}
          </ul>
        )}
        {listed.length > 3 && <button className="min-h-9 px-3 text-accent" onClick={() => setShowAll(!showAll)}>{showAll ? "Zwiń listę" : `Wszystkie przesłanki (${listed.length})`}</button>}
        {!!review?.limitations.length && <aside className="m-3 rounded-lg border border-line bg-bg p-3">
          <h3 className="mb-1 flex items-center gap-2 font-medium text-muted"><Info size={16} aria-hidden/>Czego te dowody nie pokazują</h3>
          <ul className="list-disc space-y-1 pl-5">{review.limitations.map(text => <li key={text}>{expert ? text.replace(/^ślad (.+) współdzielony przez (\d+) reklam$/, "Ślad $1 występuje w $2 reklamach") : plainLimitation(text)}</li>)}</ul>
        </aside>}
        {!review && decision}
        {!review && result && <p role="status" className="p-2">{result}</p>}</>}
        </div>
      </div>
      {review && decision}
    </div>
  );
}

export function EdgePanelEmpty() {
  return (
    <Empty title="Wybierz krawędź albo węzeł">
      Kliknij krawędź w grafie albo wiersz w tabeli, żeby zobaczyć dowody: typ markera, wartości po obu stronach, rzadkość w korpusie i wkład w bitach. Kliknięcie węzła otwiera kartę reklamy.
    </Empty>
  );
}


export function regroupMessage(regroup?: Regroup, lead = "Zapisano ocenę.") {
  const changes = [
    ...(regroup?.campaign ?? []).map(c => ({ ...c, kind: "Kampania" })),
    ...(regroup?.operator ?? []).map(c => ({ ...c, kind: "Operator" })),
  ];
  if (!changes.length) return `${lead} Skład kampanii i operatorów pozostał ten sam.`;
  const parts = changes.map(c => {
    const after = c.after.map(g => `${g.key} (${g.ads.length} ${plural(g.ads.length, "reklama", "reklamy", "reklam")})`);
    const what = after.length === 0 ? "rozwiązana" : after.length === 1 ? `zmienia skład: ${after[0]}` : `rozdzielona na ${after.join(" i ")}`;
    const released = c.released.length ? `; reklamy bez grupy: ${c.released.map(id => "#" + id).join(", ")}` : "";
    return `${c.kind} ${c.group} ${what}${released}`;
  });
  return `${lead} Zmiana grup: ${parts.join(". ")}.`;
}
