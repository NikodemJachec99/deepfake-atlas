"use client";

// Minimalny ekran Discovery. Dowodzi, że API działa od wejścia do dowodów.
// Docelowy interfejs (trzy tryby, graf, panel dowodów) powstaje według docs/design-prompt.md.

import { FolderInput, ArrowUpRight } from "lucide-react";
import { useApi } from "@/lib/hooks";
import { adTitle } from "@/lib/format";
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
} from "@/lib/api";

const stageLabels = { ingest: "Przyjęcie", crawl: "Strona", extract: "Markery", enrich: "Infrastruktura", fuse: "Powiązania", cluster: "Grupowanie", end: "Zakończenie" };
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

export function Discovery() {
  const archive = useApi("discovery-case-materials", latestCaseMaterials);
  const [files, setFiles] = useState<File[]>([]);
  const [kind, setKind] = useState<"url" | "text">("url");
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [events, setEvents] = useState<AnalysisEvent[]>([]);
  const [ad, setAd] = useState<AdDetail | null>(null);
  const [edges, setEdges] = useState<Edge[]>([]);
  const [selected, setSelected] = useState<number | null>(null);
  const evidenceHeading = useRef<HTMLHeadingElement>(null);
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
    if (typeof start === "function") setBatch([]);
    setBusy(true);
    setRetry(null);
    setError("");
    setEvents([]);
    setAd(null);
    setEdges([]);
    setSelected(null);
    setAssessment("");
    try {
      const result = typeof start === "function" ? await start() : start;
      if (generation.current !== current) return;
      const analysis = Array.isArray(result) ? result[0] : result;
      if (!analysis) throw new Error("W przesłanych plikach nie znaleziono materiału do analizy.");
      if (Array.isArray(result)) setBatch(result);
      setActiveId(analysis.id);
      stop.current = streamAnalysis(
        analysis,
        (item) => {
          if (generation.current === current) setEvents(previous => [...previous, item]);
        },
        async () => {
          try {
            const finished = await api.analysis(analysis.id);
            if (generation.current !== current) return;
            if (finished.status === "running" || finished.status === "queued") {
              setRetry(analysis);
              return;
            }
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
      setError(String(reason));
      setBusy(false);
    }
  }

  function submit(event: React.FormEvent) {
    event.preventDefault();
    const material = value.trim();
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

  return (
    <main className="mx-auto flex w-full max-w-7xl flex-col gap-6 px-4 py-7 font-sans md:px-9">
      <header className="flex flex-col gap-1">
        <h1 className="text-4xl font-semibold tracking-tight">Analiza materiału</h1>
        <p className="text-muted">Wrzuć adres reklamy albo jej tekst. System znajdzie ślady i pokaże, z czym się łączy.</p>
      </header>

      <div className="grid overflow-hidden rounded-xl border border-line lg:grid-cols-[3fr_2fr]">
      <section className="grid content-center gap-4 bg-panel p-5 md:p-7">
      <h2 className="text-xl font-semibold">Adres lub treść reklamy</h2>
      <form onSubmit={submit} className="flex flex-col gap-2 sm:flex-row">
        <select
          id="input-kind"
          aria-label="Rodzaj materiału"
          value={kind}
          onChange={(e) => setKind(e.target.value as "url" | "text")}
          className="rounded border border-line-strong bg-raised px-2 py-2"
        >
          <option value="url">Adres URL</option>
          <option value="text">Tekst lub nazwa produktu</option>
        </select>
        <input
          id="input-value"
          aria-label={kind === "url" ? "Adres URL" : "Tekst lub nazwa produktu"}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder={kind === "url" ? "https://..." : "Treść reklamy"}
          required
          className="min-w-0 flex-1 rounded border border-line-strong bg-raised px-3 py-2 font-mono"
        />
        <button id="analyze" disabled={busy || !value.trim()} className="rounded bg-accent px-4 py-2 font-medium text-on-accent disabled:opacity-50">
          {busy ? "Analiza trwa" : "Analizuj"}
        </button>
      </form>
      {!value.trim() && <p className="text-sm text-muted">{kind === "url" ? "Wpisz adres URL, aby rozpocząć analizę." : "Wpisz treść reklamy lub nazwę produktu, aby rozpocząć analizę."}</p>}
      </section>

      <section className="grid min-w-0 content-center gap-3 bg-raised p-5 md:p-7">
        <h2 className="text-lg font-semibold">Import plików</h2>
        <label onDragOver={event => event.preventDefault()} onDrop={event => {
          event.preventDefault();
          const added = Array.from(event.dataTransfer.files);
          if (!busy) setFiles(previous => [...previous, ...added]);
        }} className="grid cursor-pointer justify-items-start gap-2 rounded-lg border border-dashed border-line-strong p-4 focus-within:outline">
          <FolderInput size={24} className="text-accent" aria-hidden />
          <span>Upuść pliki lub wybierz je z dysku</span>
          <span className="text-sm text-muted">Zrzut reklamy, zapisana strona, HAR lub ZIP ze sprawą</span>
          <input id="input-files" type="file" multiple disabled={busy} className="sr-only" onChange={event => {
            const added = Array.from(event.target.files ?? []);
            setFiles(previous => [...previous, ...added]);
            event.target.value = "";
          }} />
        </label>
        {files.length > 0 && <>
          <ul>{files.map((file, index) => <li key={index} className="flex items-baseline justify-between gap-3">
            <span className="min-w-0 break-all">{file.name}</span>
            <button disabled={busy} aria-label={`Usuń ${file.name}`} onClick={() => setFiles(previous => previous.filter((_, i) => i !== index))}>Usuń</button>
          </li>)}</ul>
          <button disabled={busy} className="justify-self-start rounded bg-accent px-4 py-2 text-on-accent" onClick={() => upload(files)}>Analizuj pliki</button>
        </>}
      </section>
      </div>

      {batch.length > 1 && <label className="flex items-center gap-2">Materiał z paczki
        <select className="min-w-0 max-w-full rounded border border-line bg-panel p-2" value={activeId} onChange={event => {
          const analysis = batch.find(item => item.id === event.target.value);
          if (analysis) void run(analysis);
        }}>
          {batch.map((item, index) => <option key={item.id} value={item.id}>
            {index + 1}. {item.input_value || item.id}
          </option>)}
        </select>
      </label>}
      {retry && <div role="status" className="flex flex-wrap items-center gap-3 rounded border border-line p-3">
        <span>Przerwano odbiór danych analizy.</span>
        <button className="text-accent underline" onClick={() => void run(retry)}>Wznów podgląd</button>
      </div>}
      {error && <p className="rounded border border-rejected px-3 py-2 text-rejected">Analiza nie powiodła się: {error}</p>}

      <div className="grid gap-6 lg:grid-cols-[minmax(15rem,1fr)_minmax(0,2fr)]">
        <section className="flex min-w-0 flex-col gap-2">
          <h2 className="border-b border-line pb-2 text-lg font-semibold">Przebieg analizy</h2>
          <ol className="grid gap-1">
            {Object.entries(stageLabels).map(([stage, label]) => {
              const latest = [...events].reverse().find(event => event.stage === stage);
              return <li key={stage} className="flex items-center gap-3 border-b border-line py-2">
                <span aria-hidden className={latest ? "size-2 rounded-full bg-accent" : "size-2 rounded-full border border-line-strong"} />
                <span>{label}</span><span className="ml-auto text-xs text-muted">{latest ? stateLabels[latest.status] : "oczekuje"}</span>
              </li>;
            })}
          </ol>
          {events.filter(event => event.stage === "crawl" && Array.isArray(event.payload.chain)).map(event =>
            <section key={event.seq}>
              <h3>{event.payload.profile === "bot" ? "Profil automatu" : event.payload.profile === "victim" ? "Profil odbiorcy" : "Przechwycenie"}</h3>
              <CrawlShot sha={event.payload.screenshot} />
              <ol aria-label="Łańcuch przekierowań" className="break-all font-mono">
              {(event.payload.chain as {url: string; status?: number; via?: string}[]).map((hop, index) =>
                <li key={index}>{hop.via === "js" ? "Skrypt / meta refresh" : hop.via === "http" ? "HTTP" : ""} {hop.status} {hop.url}</li>)}
            </ol></section>)}
          {events.some(e => e.payload.cloaking === true) && <p>Cloaking: automat i odbiorca otrzymali różne wersje strony.</p>}
          {events.length === 0 && <p className="text-muted">Tu pojawią się kolejne etapy, na żywo.</p>}
          <ol className="flex flex-col gap-1 font-mono text-xs">
            {events.map((item) => (
              <li key={item.seq} className={item.status === "error" ? "text-rejected" : item.status === "info" ? "text-muted" : ""}>
                <span className="text-muted">{String(item.seq).padStart(2, "0")}</span> {item.stage} · {item.message}
              </li>
            ))}
          </ol>
        </section>

        <section className="flex min-w-0 flex-col gap-2">
          {!activeId && <section className="mb-4">
            <div className="flex items-baseline justify-between border-b border-line pb-2"><h2 className="text-lg font-semibold">Ostatnie materiały ze spraw</h2><Link href="/archive" className="text-accent underline">Całe archiwum</Link></div>
            {archive.loading ? <p>Pobieranie materiałów…</p> : archive.error ? <button onClick={archive.reload} className="text-accent underline">Ponów pobranie materiałów</button> :
              archive.data?.length ? archive.data.map(item => <Link key={item.id} href={`/ads/${item.id}`} className="flex items-center gap-4 border-b border-line py-3 hover:bg-panel">
                <span className="font-mono text-muted">#{item.id}</span><strong className="min-w-0 flex-1 truncate">{adTitle(item)}</strong><span className="text-muted">{item.case}</span><ArrowUpRight size={16} aria-hidden />
              </Link>) : <p>Brak materiałów przypisanych do spraw.</p>}
          </section>}
          <h2 className="text-lg font-semibold">{cluster?.assessment_label || assessment || "Powiązania"}</h2>
          {!ad && !cluster && !edges.length && <p className="text-muted">Po zakończeniu analizy zobaczysz tutaj powiązania materiału.</p>}
          {(ad || cluster) && <p aria-label="Przypisanie do grup">
            Kampania <GroupLink group={ad ? ad.campaign : cluster?.campaign} /> · Operator <GroupLink group={ad ? ad.operator : cluster?.operator} />
          </p>}
          {strongest.length > 0 && <section><h3>Najsilniejsze dowody</h3><ol>{strongest.map(({ best, edges }) => (
            <li key={JSON.stringify([best.kind, best.value])}><FamilyDot family={best.family} /> {best.label} · {markerValue(best.value, ad?.genome?.find(band => band.family === best.family)?.markers.find(marker => marker.kind === best.kind && marker.value === best.value)?.display_value)} · {best.bits} bitów · liczba powiązań: {edges.size}</li>
          ))}</ol></section>}
          {ad && (
            <p>
              {ad.labels.topics && ad.labels.topics.length > 0 && <span className="block text-muted">Tematyka: {ad.labels.topics.join(", ")}</span>}
              {ad.labels.keywords && ad.labels.keywords.length > 0 && (
                <span className="block text-muted">Słowa kluczowe: {ad.labels.keywords.slice(0, 8).join(", ")}</span>
              )}
              {"cert_pl" in ad.labels && <> Domena jest na Liście Ostrzeżeń CERT Polska.</>}
            </p>
          )}
          {ad && <nav aria-label="Szczegóły wyniku" className="flex flex-wrap gap-4 text-accent">
            <Link href={`/ads/${ad.id}`}>Karta reklamy #{ad.id}</Link>
            <Link href={`/investigation?ad=${ad.id}`}>Otwórz w Investigation</Link>
          </nav>}
          {ad && edges.length === 0 && <p className="text-muted">Brak powiązań powyżej progu.</p>}
          <ul className="flex flex-col gap-1">
            {edges.map((edge) => (
              <li key={edge.id}>
                <button
                  onClick={() => openEvidence(edge.id)}
                  className="flex w-full items-center justify-between gap-3 rounded border border-line px-3 py-2 text-left hover:border-accent"
                >
                  <span>
                    #{edge.ad_a} ↔ #{edge.ad_b} · {RELATION_LABELS[edge.relation]}
                    {edge.duplicate && " · duplikat"}
                  </span>
                  <span className="font-mono">{edge.probability.toFixed(2)}</span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      </div>

      <LiveGraph events={events} onEdge={openEvidence} />
      {selected !== null && <section aria-labelledby="discovery-evidence">
        <h2 id="discovery-evidence" ref={evidenceHeading} tabIndex={-1} className="font-semibold">Dowody powiązania #{selected}</h2>
        <EdgePanel key={selected} edgeId={selected} />
      </section>}
    </main>
  );
}
