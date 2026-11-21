"use client";

// Minimalny ekran Discovery. Dowodzi, że API działa od wejścia do dowodów.
// Docelowy interfejs (trzy tryby, graf, panel dowodów) powstaje według docs/design-prompt.md.

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

export function Discovery() {
  const [kind, setKind] = useState<"url" | "text">("url");
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [events, setEvents] = useState<AnalysisEvent[]>([]);
  const [ad, setAd] = useState<AdDetail | null>(null);
  const [edges, setEdges] = useState<Edge[]>([]);
  const [selected, setSelected] = useState<number | null>(null);
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
    void run(() => api.createAnalysis(kind, value.trim()));
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
    <main className="mx-auto flex w-full max-w-6xl flex-col gap-6 px-4 py-8 font-sans text-sm">
      <header className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold">SCAM DNA</h1>
        <p className="opacity-70">Wrzuć adres reklamy albo jej tekst. System znajdzie ślady i pokaże, z czym się łączy.</p>
      </header>

      <form onSubmit={submit} className="flex flex-col gap-2 sm:flex-row">
        <select
          id="input-kind"
          value={kind}
          onChange={(e) => setKind(e.target.value as "url" | "text")}
          className="rounded border border-neutral-600 bg-transparent px-2 py-2"
        >
          <option value="url">Adres URL</option>
          <option value="text">Tekst lub nazwa produktu</option>
        </select>
        <input
          id="input-value"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder={kind === "url" ? "https://..." : "Treść reklamy"}
          required
          className="min-w-0 flex-1 rounded border border-neutral-600 bg-transparent px-3 py-2 font-mono"
        />
        <button id="analyze" disabled={busy} className="rounded bg-sky-600 px-4 py-2 font-medium text-white disabled:opacity-50">
          {busy ? "Analiza trwa" : "Analizuj"}
        </button>
      </form>

      <label onDragOver={event => event.preventDefault()} onDrop={event => { event.preventDefault(); upload(Array.from(event.dataTransfer.files)); }} className="flex flex-wrap items-center gap-3 rounded border border-dashed border-neutral-600 px-3 py-3">
        <span className="opacity-70">Upuść pliki lub wybierz je z dysku: zrzut ekranu reklamy, zapisana strona, HAR, ZIP ze sprawą.</span>
        <input id="input-files" type="file" multiple disabled={busy} onChange={event => { upload(Array.from(event.target.files ?? [])); event.target.value = ""; }} className="text-xs" />
      </label>

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
      {error && <p className="rounded border border-red-500 px-3 py-2 text-red-400">Analiza nie powiodła się: {error}</p>}

      <div className="grid gap-6 lg:grid-cols-2">
        <section className="flex min-w-0 flex-col gap-2">
          <h2 className="font-semibold">Przebieg analizy</h2>
          <ol className="grid gap-1">
            {Object.entries(stageLabels).map(([stage, label]) => {
              const latest = [...events].reverse().find(event => event.stage === stage);
              return <li key={stage}>{label} · {latest ? stateLabels[latest.status] : "oczekuje"}</li>;
            })}
          </ol>
          {events.filter(event => event.stage === "crawl" && Array.isArray(event.payload.chain)).map(event =>
            <ol key={event.seq} aria-label="Łańcuch przekierowań" className="break-all font-mono">
              {(event.payload.chain as {url: string; status?: number}[]).map((hop, index) =>
                <li key={index}>{hop.status} {hop.url}</li>)}
            </ol>)}
          {events.length === 0 && <p className="opacity-60">Tu pojawią się kolejne etapy, na żywo.</p>}
          <ol className="flex flex-col gap-1 font-mono text-xs">
            {events.map((item) => (
              <li key={item.seq} className={item.status === "error" ? "text-red-400" : item.status === "info" ? "opacity-70" : ""}>
                <span className="opacity-50">{String(item.seq).padStart(2, "0")}</span> {item.stage} · {item.message}
              </li>
            ))}
          </ol>
        </section>

        <section className="flex min-w-0 flex-col gap-2">
          <h2 className="font-semibold">{cluster?.assessment_label || assessment || "Powiązania"}</h2>
          {cluster && <p>Kampania {cluster.campaign ?? "brak"} · Operator {cluster.operator ?? "brak"}</p>}
          {strongest.length > 0 && <section><h3>Najsilniejsze dowody</h3><ol>{strongest.map(({ best, edges }) => (
            <li key={JSON.stringify([best.kind, best.value])}><FamilyDot family={best.family} /> {best.label} · {markerValue(best.value, ad?.genome?.find(band => band.family === best.family)?.markers.find(marker => marker.kind === best.kind && marker.value === best.value)?.display_value)} · {best.bits} bitów · liczba powiązań: {edges.size}</li>
          ))}</ol></section>}
          {ad && (
            <p>
              Reklama #{ad.id}
              {ad.campaign ? <> należy do kampanii <b>{ad.campaign}</b>.</> : <> nie należy do żadnej kampanii.</>}
              {ad.operator && <> Operator: <b>{ad.operator}</b>.</>}
              {ad.labels.topics && ad.labels.topics.length > 0 && <span className="block opacity-70">Tematyka: {ad.labels.topics.join(", ")}</span>}
              {ad.labels.keywords && ad.labels.keywords.length > 0 && (
                <span className="block opacity-70">Słowa kluczowe: {ad.labels.keywords.slice(0, 8).join(", ")}</span>
              )}
              {"cert_pl" in ad.labels && <> Domena jest na Liście Ostrzeżeń CERT Polska.</>}
            </p>
          )}
          {ad && <nav aria-label="Szczegóły wyniku" className="flex flex-wrap gap-4 text-accent">
            <Link href={`/ads/${ad.id}`}>Karta reklamy #{ad.id}</Link>
            <Link href={`/investigation?ad=${ad.id}`}>Otwórz w Investigation</Link>
          </nav>}
          {ad && edges.length === 0 && <p className="opacity-60">Brak powiązań powyżej progu.</p>}
          <ul className="flex flex-col gap-1">
            {edges.map((edge) => (
              <li key={edge.id}>
                <button
                  onClick={() => setSelected(edge.id)}
                  className="flex w-full items-center justify-between gap-3 rounded border border-neutral-700 px-3 py-2 text-left hover:border-sky-500"
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

      <LiveGraph events={events} onEdge={setSelected} />
      {selected !== null && <EdgePanel key={selected} edgeId={selected} />}
    </main>
  );
}
