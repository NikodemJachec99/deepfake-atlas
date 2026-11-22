"use client";

// Ekran startowy: co można zrobić teraz (liczby z /api/stats) i dodanie nowego materiału.
// Wynik analizy najpierw prostym językiem, szczegóły techniczne w trybie eksperckim.

import { FolderInput, ArrowRight, ArrowUpRight, ClipboardCheck, Bell, Network, Check, Loader2 } from "lucide-react";
import { useApi } from "@/lib/hooks";
import { useExpert } from "@/lib/expert";
import { bits, adTitle, errorText, prob, plural } from "@/lib/format";
import { CrawlShot } from "./crawl-shot";
import { GroupLink } from "./ui";
import { LiveGraph } from "./live-graph";
import { EdgePanel } from "./edge-panel";
import { markerValue } from "@/lib/format";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import {
  api,
  type Analysis,
  type ClusterResult,
  RELATION_LABELS,
  streamAnalysis,
  type AdDetail,
  type AdSummary,
  type AnalysisEvent,
  type Edge,
  type Family,
  type FuseEventPayload,
  type Relation,
  type Stats,
} from "@/lib/api";

const stageLabels = { ingest: "Przyjęcie", crawl: "Strona", extract: "Markery", enrich: "Infrastruktura", fuse: "Powiązania", cluster: "Grupowanie", end: "Zakończenie" };
const stageSteps = { ingest: "Przyjęcie materiału", crawl: "Pobranie strony", extract: "Szukanie śladów", enrich: "Sprawdzanie zaplecza", fuse: "Szukanie powiązań", cluster: "Przypisanie do grup", end: "Zakończenie" };
const stateLabels = { started: "w toku", info: "w toku", done: "zakończono", error: "błąd" };

function FamilyDot({ family }: { family: Family }) {
  return <span className="inline-block h-2.5 w-2.5 shrink-0 rounded-sm" style={{ background: `var(--fam-${family})` }} />;
}

async function latestCaseMaterials() {
  const materials: AdSummary[] = [];
  for (let page = 1; ; page++) {
    const result = await api.ads(`?page=${page}&page_size=100`);
    materials.push(...result.results.filter(item => item.case));
    if (materials.length >= 4 || !result.next) return materials.slice(0, 4);
  }
}

function TaskCard({ href, Icon, title, value, note, loading, tone = "accent" }: {
  href: string; Icon: typeof Bell; title: string; value: number | null; note: string; loading: boolean; tone?: "accent" | "alert";
}) {
  const highlight = value !== null && value > 0;
  const icon = <span className={`inline-flex size-8 shrink-0 items-center justify-center rounded-lg ${tone === "alert" && highlight ? "bg-rejected/10 text-rejected" : "bg-accent-soft text-accent"}`}><Icon size={17} aria-hidden /></span>;
  const number = loading ? <span className="inline-block h-8 w-12 animate-pulse rounded bg-hover" aria-label="Pobieranie" />
    : value !== null && <span className="text-3xl font-semibold tracking-tight tabular-nums sm:text-4xl">{value}</span>;
  return <Link href={href} className="group min-w-0 rounded-xl border border-line bg-raised transition-colors duration-150 hover:border-accent hover:bg-panel">
    <span className="flex items-center gap-3 p-4 sm:hidden">
      {icon}
      <span className="flex min-w-0 flex-1 flex-col"><span className="font-medium">{title}</span><span className="text-sm text-muted">{note}</span></span>
      {number}
    </span>
    <span className="hidden flex-col gap-3 p-5 sm:flex">
      <span className="flex items-center gap-2 font-medium">
        {icon}{title}
        <ArrowRight size={16} className="ml-auto text-muted transition-transform duration-150 group-hover:translate-x-0.5 group-hover:text-accent" aria-hidden />
      </span>
      <span className="flex items-baseline gap-2">{number}<span className="text-muted">{note}</span></span>
    </span>
  </Link>;
}

function Tasks() {
  const stats = useApi<Stats>("home-stats", api.stats);
  const data = stats.data;
  const loading = stats.loading;
  const missing = "liczba chwilowo niedostępna";
  const review = data?.review_pending ?? null;
  const alerts = data?.alerts_unseen ?? null;
  return <section aria-labelledby="tasks-heading" className="grid gap-3 sm:gap-4">
    <h1 id="tasks-heading" className="text-3xl font-semibold tracking-tight md:text-4xl">Co chcesz zrobić?</h1>
    <div className="grid gap-2 sm:grid-cols-2 sm:gap-3 lg:grid-cols-3">
      <TaskCard href="/review" Icon={ClipboardCheck} title="Oceń powiązania" loading={loading} value={review}
        note={review === null ? missing : review === 0 ? "kolejka pusta" : plural(review, "para czeka na decyzję", "pary czekają na decyzję", "par czeka na decyzję")} />
      <TaskCard href="/alerts" Icon={Bell} title="Sprawdź alerty" tone="alert" loading={loading} value={alerts}
        note={alerts === null ? missing : alerts === 0 ? "brak nowych alertów" : plural(alerts, "nowy alert", "nowe alerty", "nowych alertów")} />
      <TaskCard href="/investigation" Icon={Network} title="Przeglądaj powiązania" loading={loading} value={data?.campaigns ?? null}
        note={data ? `${plural(data.campaigns, "kampania", "kampanie", "kampanii")} · ${data.operators} ${plural(data.operators, "operator", "operatorów", "operatorów")}` : missing} />
    </div>
  </section>;
}

export function Discovery() {
  const { expert } = useExpert();
  const archive = useApi("discovery-case-materials", latestCaseMaterials);
  const [files, setFiles] = useState<File[]>([]);
  const [kind, setKind] = useState<"url" | "text" | "files">("url");
  const [address, setAddress] = useState("");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [events, setEvents] = useState<AnalysisEvent[]>([]);
  const [ad, setAd] = useState<AdDetail | null>(null);
  const [edges, setEdges] = useState<Edge[]>([]);
  const [allEdges, setAllEdges] = useState(false);
  const [selected, setSelected] = useState<number | null>(null);
  const evidenceHeading = useRef<HTMLHeadingElement>(null);
  const resultRef = useRef<HTMLElement>(null);
  function focusEvidence() {
    evidenceHeading.current?.focus({ preventScroll: true });
    evidenceHeading.current?.scrollIntoView({ block: "start" });
  }
  useEffect(() => {
    if (selected !== null) focusEvidence();
  }, [selected]);

  function openEvidence(id: number) {
    if (id === selected) focusEvidence();
    else setSelected(id);
  }

  const [assessment, setAssessment] = useState("");
  const [batch, setBatch] = useState<Analysis[]>([]);
  const [activeId, setActiveId] = useState("");
  const [retry, setRetry] = useState<Analysis | null>(null);
  const stop = useRef<(() => void) | null>(null);

  // Po zakończeniu analizy wynik ląduje na górze widoku: ocena i „dlaczego” bez przewijania.
  const done = !busy && !!activeId;
  useEffect(() => {
    if (done) resultRef.current?.scrollIntoView({ block: "start", behavior: "smooth" });
  }, [done]);

  const generation = useRef(0);
  useEffect(() => () => {
    generation.current++;
    stop.current?.();
    stop.current = null;
    setBusy(false);
  }, []);

  async function run(start: (() => Promise<Analysis | Analysis[]>) | Analysis) {
    const current = ++generation.current;
    stop.current?.();
    if (typeof start === "function") {
      setBatch([]);
      setActiveId("");
    }
    setBusy(true);
    setRetry(null);
    setError("");
    setEvents([]);
    setAd(null);
    setEdges([]);
    setAllEdges(false);
    setSelected(null);
    setAssessment("");
    try {
      const result = typeof start === "function" ? await start() : start;
      if (generation.current !== current) return;
      const analysis = Array.isArray(result) ? result[0] : result;
      if (!analysis) throw new Error("W przesłanych plikach nie znaleziono materiału do analizy.");
      if (Array.isArray(result)) setBatch(result);
      setActiveId(analysis.id);
      requestAnimationFrame(() => resultRef.current?.scrollIntoView({ block: "start", behavior: "smooth" }));
      stop.current = streamAnalysis(
        analysis,
        (item) => {
          if (generation.current === current) setEvents(previous => [...previous, item]);
        },
        async (reason) => {
          try {
            const finished = await api.analysis(analysis.id);
            if (generation.current !== current) return;
            if (finished.status === "running" || finished.status === "queued") {
              setRetry(analysis);
              return;
            }
            if (reason === "interrupted") setRetry(analysis);
            if (finished.status === "failed") {
              setError(finished.error || "Backend zgłosił błąd analizy.");
              return;
            }
            setAssessment((finished.result.cluster as ClusterResult | undefined)?.assessment_label ?? "");
            if (finished.ad) {
              const [detail, links] = await Promise.all([api.ad(finished.ad), api.adEdges(finished.ad)]);
              if (generation.current !== current) return;
              setAd(detail);
              setEdges(links);
            }
          } catch {
            if (generation.current === current) setRetry(analysis);
          } finally {
            if (generation.current === current) setBusy(false);
          }
        },
      );
    } catch (reason) {
      if (generation.current !== current) return;
      setError(errorText(reason));
      setBusy(false);
    }
  }

  function submit(event: React.FormEvent) {
    event.preventDefault();
    if (kind === "files") { upload(files); return; }
    const material = (kind === "url" ? address : text).trim();
    if (!material || busy) return;
    void run(() => api.createAnalysis(kind, material));
  }

  function upload(files: File[]) {
    if (!busy && files.length) void run(() => api.uploadCase(files));
  }

  const markers = new Map<string, { best: FuseEventPayload["top_evidence"][number]; edges: Set<number> }>();
  for (const event of events) {
    if (event.stage !== "fuse" || event.status !== "info") continue;
    const { edge, top_evidence } = event.payload as Partial<FuseEventPayload>;
    if (typeof edge !== "number") continue;
    for (const item of top_evidence ?? []) {
      const key = JSON.stringify([item.kind, item.value]);
      const match = markers.get(key);
      if (match) {
        match.edges.add(edge);
        if (item.bits > match.best.bits) match.best = item;
      } else {
        markers.set(key, { best: item, edges: new Set([edge]) });
      }
    }
  }
  const strongest = [...markers.values()].sort((a, b) => b.best.bits - a.best.bits).slice(0, 5);
  const cluster = [...events].reverse().find(item => item.stage === "cluster" && item.status === "done")?.payload as Partial<ClusterResult> | undefined;
  const verdict = cluster?.assessment_label || assessment;

  // Jedno zdanie „dlaczego”: nazwy najsilniejszych śladów z API, bez wartości i bitów.
  const reasonNames = [...new Set(strongest.map(({ best }) => best.label))].slice(0, 3);
  // Mała litera w środku zdania, chyba że to nazwa własna (kolejne słowo z wielkiej litery, np. „Meta Pixel”; skróty jak „URL” się nie liczą).
  const lowerFirst = (name: string) => /\s\p{Lu}\p{Ll}/u.test(name) ? name : name.charAt(0).toLocaleLowerCase("pl") + name.slice(1);
  const reasonList = reasonNames.map(lowerFirst);
  const reasonText = reasonList.length
    ? `Najmocniej łączy ją z innymi reklamami: ${reasonList.length > 1 ? `${reasonList.slice(0, -1).join(", ")} i ${reasonList.at(-1)}` : reasonList[0]}.`
    : "";
  const relationCounts = edges.reduce<Partial<Record<Relation, number>>>((counts, edge) => ({ ...counts, [edge.relation]: (counts[edge.relation] ?? 0) + 1 }), {});
  const sortedEdges = [...edges].sort((a, b) => b.probability - a.probability);
  const shownEdges = allEdges ? sortedEdges : sortedEdges.slice(0, 6);
  const stageKeys = Object.keys(stageSteps) as (keyof typeof stageSteps)[];
  const reached = stageKeys.filter(stage => events.some(event => event.stage === stage));
  const currentStage = reached.at(-1);
  const finished = !busy && !!activeId && !error;
  const active = busy || activeId || events.length > 0;

  return (
    <main className="mx-auto flex w-full max-w-6xl flex-col gap-8 px-4 py-6 font-sans md:gap-10 md:px-10 md:py-10">
      <Tasks />

      <section aria-labelledby="add-heading" className="grid gap-4">
        <div className="grid gap-1">
          <h2 id="add-heading" className="text-xl font-semibold tracking-tight">Sprawdź nowy materiał</h2>
          <p className="max-w-[65ch] text-muted">Wklej adres reklamy, jej tekst albo wrzuć pliki. System znajdzie ślady i pokaże, z czym materiał się łączy.</p>
        </div>
        <form onSubmit={submit} className="grid gap-5 rounded-xl border border-line bg-panel p-5 md:p-6">
          <fieldset id="input-kind" disabled={busy} className="grid gap-2">
            <legend className="mb-2 text-sm font-medium text-muted">Rodzaj materiału</legend>
            <div className="inline-flex w-fit max-w-full rounded-lg border border-line bg-raised p-1">
              {([["url", "Adres"], ["text", "Tekst"], ["files", "Pliki"]] as const).map(([type, label]) =>
                <button type="button" key={type} aria-pressed={kind === type} onClick={() => setKind(type)}
                  className="h-9 rounded-md px-4 font-medium text-muted transition-colors duration-150 hover:text-fg aria-pressed:bg-accent-soft aria-pressed:text-accent">{label}</button>)}
            </div>
          </fieldset>
          {kind === "url" && <label className="grid gap-1.5 font-medium">Adres reklamy lub strony<input id="input-value" type="url" required value={address} onChange={e => setAddress(e.target.value)}
            placeholder="https://…" className="block h-10 w-full rounded-lg border border-line-strong bg-raised px-3 font-normal" /></label>}
          {kind === "text" && <label className="grid gap-1.5 font-medium">Tekst lub nazwa produktu<textarea id="input-value" required rows={4} value={text} onChange={e => setText(e.target.value)}
            placeholder="Np. treść ogłoszenia lub nazwa reklamowanego produktu" className="block w-full rounded-lg border border-line-strong bg-raised px-3 py-2 font-normal" /></label>}
          {kind === "files" && <>
            <label onDragOver={event => event.preventDefault()} onDrop={event => {
              event.preventDefault();
              const added = Array.from(event.dataTransfer.files);
              if (!busy) setFiles(previous => [...previous, ...added]);
            }} className="grid cursor-pointer justify-items-center gap-2 rounded-lg border border-dashed border-line-strong bg-raised px-4 py-8 text-center transition-colors duration-150 hover:border-accent focus-within:outline">
              <FolderInput size={28} className="text-accent" aria-hidden />
              <span className="font-medium">Upuść pliki albo wybierz je z dysku</span>
              <span className="text-sm text-muted">Zrzut reklamy, zapisana strona, HAR lub ZIP ze sprawą</span>
              <input id="input-files" type="file" multiple disabled={busy} className="sr-only" onChange={event => {
                const added = Array.from(event.target.files ?? []);
                setFiles(previous => [...previous, ...added]);
                event.target.value = "";
              }} />
            </label>
            {files.length > 0 && <ul className="grid gap-1">{files.map((file, index) => <li key={index} className="flex items-center justify-between gap-3 rounded-lg bg-raised px-3 py-1">
              <span className="min-w-0 break-all">{file.name}</span>
              <button type="button" disabled={busy} aria-label={`Usuń ${file.name}`} onClick={() => setFiles(previous => previous.filter((_, i) => i !== index))}
                className="shrink-0 rounded-md px-2 text-sm text-muted hover:bg-hover hover:text-fg">Usuń</button>
            </li>)}</ul>}
          </>}
          <button id="analyze" type="submit" disabled={busy || (kind === "files" ? !files.length : !(kind === "url" ? address : text).trim())}
            className="inline-flex h-10 items-center gap-2 justify-self-start rounded-lg bg-accent px-5 font-medium text-on-accent transition-[filter] duration-150 hover:brightness-110 disabled:opacity-50">
            {busy && <Loader2 size={16} className="animate-spin" aria-hidden />}
            {busy ? "Analiza trwa" : "Przeanalizuj materiał"}
          </button>
        </form>
      </section>

      {batch.length > 1 && <label className="flex flex-wrap items-center gap-2">Materiał z paczki
        <select className="min-w-0 max-w-full rounded-lg border border-line bg-panel px-2" value={activeId} onChange={event => {
          const analysis = batch.find(item => item.id === event.target.value);
          if (analysis) void run(analysis);
        }}>
          {batch.map((item, index) => <option key={item.id} value={item.id}>
            {index + 1}. {item.input_value || item.id}
          </option>)}
        </select>
      </label>}
      {retry && <div role="status" className="flex flex-wrap items-center gap-3 rounded-xl border border-line p-4">
        <span>Przerwano odbiór danych analizy.</span>
        <button className="rounded-lg px-2 text-accent underline" onClick={() => void run(retry)}>Wznów podgląd</button>
      </div>}
      {error && <p role="alert" className="rounded-xl border border-rejected px-4 py-3 text-rejected">Analiza nie powiodła się: {error}</p>}

      {active && <section ref={resultRef} aria-labelledby="result-heading" className="grid scroll-mt-4 gap-5 rounded-xl border border-line bg-raised p-5 md:p-7">
        <div className="grid gap-2">
          <p className="flex items-center gap-2 text-sm font-medium text-muted">
            {busy ? <><Loader2 size={15} className="animate-spin text-accent" aria-hidden />{currentStage ? `${stageSteps[currentStage]} (krok ${reached.length} z ${stageKeys.length})` : "Rozpoczynanie analizy"}</>
              : finished ? <><Check size={15} className="text-confirmed" aria-hidden />Analiza zakończona</> : "Wynik analizy"}
          </p>
          {busy && <div className="h-1.5 overflow-hidden rounded-full bg-hover" role="progressbar" aria-label="Postęp analizy" aria-valuemin={0} aria-valuemax={stageKeys.length} aria-valuenow={reached.length}>
            <div className="h-full rounded-full bg-accent transition-[width] duration-300" style={{ width: `${(reached.length / stageKeys.length) * 100}%` }} />
          </div>}
          <h2 id="result-heading" className="text-2xl font-semibold tracking-tight md:text-3xl">{verdict || (busy ? "Szukamy powiązań…" : "Powiązania")}</h2>
          {reasonText && <p className="max-w-[70ch] text-base">{reasonText}</p>}
          {!busy && ad && edges.length === 0 && <p className="text-base text-muted">Nie znaleźliśmy wspólnych śladów z reklamami w bazie.</p>}
        </div>

        {(ad || cluster) && <dl aria-label="Przypisanie do grup" className="flex flex-wrap gap-x-8 gap-y-2">
          <div className="grid gap-0.5"><dt className="text-xs text-muted">Kampania</dt><dd><GroupLink group={ad ? ad.campaign : cluster?.campaign} /></dd></div>
          <div className="grid gap-0.5"><dt className="text-xs text-muted">Operator</dt><dd><GroupLink group={ad ? ad.operator : cluster?.operator} /></dd></div>
          {edges.length > 0 && <div className="grid gap-0.5"><dt className="text-xs text-muted">Powiązane reklamy</dt><dd>{edges.length}{" "}
            <span className="text-muted">({Object.entries(relationCounts).map(([relation, count]) => `${RELATION_LABELS[relation as Relation].toLocaleLowerCase("pl")}: ${count}`).join(", ")})</span></dd></div>}
        </dl>}

        {ad && <nav aria-label="Szczegóły wyniku" className="flex flex-wrap gap-2">
          <Link href={`/ads/${ad.id}`} className="inline-flex h-10 items-center gap-1.5 rounded-lg bg-accent px-4 font-medium text-on-accent hover:brightness-110">Karta reklamy<ArrowRight size={16} aria-hidden /></Link>
          <Link href={`/investigation?ad=${ad.id}`} className="inline-flex h-10 items-center rounded-lg border border-line-strong px-4 font-medium hover:bg-hover">Pokaż w śledztwie</Link>
          <Link href="/review" className="inline-flex h-10 items-center rounded-lg border border-line-strong px-4 font-medium hover:bg-hover">Przejdź do oceny</Link>
        </nav>}

        {ad && ((ad.labels.topics?.length ?? 0) > 0 || (ad.labels.keywords?.length ?? 0) > 0 || "cert_pl" in ad.labels) && <div className="grid gap-1 text-muted">
          {ad.labels.topics && ad.labels.topics.length > 0 && <p>Tematyka: <span className="text-fg">{ad.labels.topics.join(", ")}</span></p>}
          {ad.labels.keywords && ad.labels.keywords.length > 0 && <p>Słowa kluczowe: <span className="text-fg">{ad.labels.keywords.slice(0, 8).join(", ")}</span></p>}
          {"cert_pl" in ad.labels && <p className="text-fg">Domena jest na Liście Ostrzeżeń CERT Polska.</p>}
        </div>}

        {expert && strongest.length > 0 && <section className="grid gap-2"><h3 className="font-semibold">Najsilniejsze dowody</h3><ol className="grid gap-1">{strongest.map(({ best, edges }) => (
          <li key={JSON.stringify([best.kind, best.value])} className="flex flex-wrap items-center gap-x-2 break-all"><FamilyDot family={best.family} /> {best.label} · {markerValue(best.value, ad?.genome?.find(band => band.family === best.family)?.markers.find(marker => marker.kind === best.kind && marker.value === best.value)?.display_value)} · {bits(best.bits)} bita · liczba powiązań: {edges.size}</li>
        ))}</ol></section>}

        {shownEdges.length > 0 && <section className="grid gap-2">
          <h3 className="font-semibold">Z czym się łączy</h3>
          <ul className="grid gap-1.5 sm:grid-cols-2">
            {shownEdges.map((edge) => {
              const other = ad && edge.ad_a === ad.id ? edge.ad_b : edge.ad_a;
              return <li key={edge.id}>
                <button onClick={() => openEvidence(edge.id)}
                  className="flex w-full items-center justify-between gap-3 rounded-lg border border-line px-3 py-2 text-left transition-colors duration-150 hover:border-accent hover:bg-panel">
                  <span className="min-w-0">
                    <span className="font-medium">{expert ? `#${edge.ad_a} ↔ #${edge.ad_b}` : `Reklama #${other}`}</span>
                    <span className="text-muted"> · {RELATION_LABELS[edge.relation]}{edge.duplicate && " · duplikat"}</span>
                  </span>
                  {expert ? <span className="font-mono">{prob(edge.probability)}</span> : <span className="shrink-0 text-sm text-accent">Dowody</span>}
                </button>
              </li>;
            })}
          </ul>
          {sortedEdges.length > 6 && <button type="button" onClick={() => setAllEdges(value => !value)} className="justify-self-start rounded-lg px-2 text-accent hover:underline">
            {allEdges ? "Pokaż mniej" : `Pokaż wszystkie (${sortedEdges.length})`}
          </button>}
        </section>}

        <details key={busy && expert ? "running" : "finished"} open={busy && expert} className="rounded-lg border border-line px-4 py-3">
          <summary className="font-medium text-muted">Przebieg analizy krok po kroku</summary>
          <ol className="mt-2 grid gap-1">
            {Object.entries(stageLabels).map(([stage, label]) => {
              const latest = [...events].reverse().find(event => event.stage === stage);
              return <li key={stage} className="flex items-center gap-3 border-b border-line py-2">
                <span aria-hidden className={latest ? "size-2 rounded-full bg-accent" : "size-2 rounded-full border border-line-strong"} />
                <span>{expert ? label : stageSteps[stage as keyof typeof stageSteps]}</span><span className="ml-auto text-xs text-muted">{latest ? stateLabels[latest.status] : "oczekuje"}</span>
              </li>;
            })}
          </ol>
          {events.filter(event => event.stage === "crawl" && Array.isArray(event.payload.chain)).map(event =>
            <section key={event.seq}>
              <h3>{event.payload.profile === "bot" ? "Profil automatu" : event.payload.profile === "victim" ? "Profil odbiorcy" : "Przechwycenie"}</h3>
              <CrawlShot sha={event.payload.screenshot} />
              <ol aria-label="Łańcuch przekierowań" className="break-all font-mono">
                {(event.payload.chain as { url: string; status?: number; via?: string }[]).map((hop, index) =>
                  <li key={index}>{hop.via === "js" ? "Skrypt / meta refresh" : hop.via === "http" ? "HTTP" : ""} {hop.status} {hop.url}</li>)}
              </ol></section>)}
          {events.some(e => e.payload.cloaking === true) && <p>Cloaking: automat i odbiorca otrzymali różne wersje strony.</p>}
          {events.length === 0 && <p className="text-muted">Tu pojawią się kolejne etapy, na żywo.</p>}
          {expert && <ol className="mt-2 flex flex-col gap-1 font-mono text-xs">
            {events.map((item) => (
              <li key={item.seq} className={item.status === "error" ? "text-rejected" : item.status === "info" ? "text-muted" : ""}>
                <span className="text-muted">{String(item.seq).padStart(2, "0")}</span> {stageLabels[item.stage as keyof typeof stageLabels] ?? item.stage} · {item.message}
              </li>
            ))}
          </ol>}
        </details>
      </section>}

      <LiveGraph events={events} onEdge={openEvidence} />
      {selected !== null && <section aria-labelledby="discovery-evidence" className="grid gap-2">
        <h2 id="discovery-evidence" ref={evidenceHeading} tabIndex={-1} className="text-lg font-semibold">Dowody powiązania{expert && ` #${selected}`}</h2>
        <EdgePanel key={selected} edgeId={selected} />
      </section>}

      {!active && <section aria-labelledby="recent-heading" className="grid gap-2">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 id="recent-heading" className="text-lg font-semibold">Ostatnie materiały ze spraw</h2>
          <Link href="/archive" className="inline-flex items-center gap-1 text-accent hover:underline">Całe archiwum<ArrowRight size={15} aria-hidden /></Link>
        </div>
        {archive.loading ? <p className="text-muted">Pobieranie materiałów…</p> : archive.error ? <button onClick={archive.reload} className="justify-self-start text-accent underline">Ponów pobranie materiałów</button> :
          archive.data?.length ? <ul className="flex flex-col overflow-hidden rounded-xl border border-line">{archive.data.map(item => <li key={item.id} className="min-w-0 border-b border-line last:border-0">
            <Link href={`/ads/${item.id}`} className="flex items-center gap-4 px-4 py-3 transition-colors duration-150 hover:bg-panel focus-visible:-outline-offset-2">
              <strong className="min-w-0 flex-1 truncate font-medium">{adTitle(item)}</strong>
              <span className="shrink-0 text-sm text-muted">sprawa {item.case}</span>
              <ArrowUpRight size={16} className="shrink-0 text-muted" aria-hidden />
            </Link></li>)}</ul>
            : <p className="text-muted">Brak materiałów przypisanych do spraw. Dodaj pierwszy materiał powyżej.</p>}
      </section>}
    </main>
  );
}
