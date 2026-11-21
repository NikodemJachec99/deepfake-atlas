"use client";

// Minimalny ekran Discovery. Dowodzi, że API działa od wejścia do dowodów.
// Docelowy interfejs (trzy tryby, graf, panel dowodów) powstaje według docs/design-prompt.md.

import { useRef, useState } from "react";

import {
  api,
  type Analysis,
  type ClusterResult,
  FAMILY_LABELS,
  RELATION_LABELS,
  streamAnalysis,
  type AdDetail,
  type AnalysisEvent,
  type Edge,
  type EdgeDetail,
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
  const [selected, setSelected] = useState<EdgeDetail | null>(null);
  const [assessment, setAssessment] = useState("");
  const stop = useRef<(() => void) | null>(null);

  async function run(start: () => Promise<Analysis>) {
    stop.current?.();
    setBusy(true);
    setError("");
    setEvents([]);
    setAd(null);
    setEdges([]);
    setSelected(null);
    setAssessment("");
    try {
      const analysis = await start();
      stop.current = streamAnalysis(
        analysis,
        (item) => setEvents((previous) => [...previous, item]),
        async () => {
          try {
            const finished = await api.analysis(analysis.id);
            setAssessment((finished.result.cluster as ClusterResult | undefined)?.assessment_label ?? "");
            if (finished.ad) {
              setAd(await api.ad(finished.ad));
              setEdges(await api.adEdges(finished.ad));
            }
            if (finished.status === "failed") setError(finished.error || "Backend zgłosił błąd analizy.");
            if (finished.status === "running" || finished.status === "queued") setError("Utracono połączenie ze strumieniem. Analiza pozostaje w kolejce backendu.");
          } catch (reason) {
            setError(String(reason));
          } finally {
            setBusy(false);
          }
        },
      );
    } catch (reason) {
      setError(String(reason));
      setBusy(false);
    }
  }

  function submit(event: React.FormEvent) {
    event.preventDefault();
    void run(() => api.createAnalysis(kind, value.trim()));
  }

  function upload(files: File[]) {
    if (!busy && files.length) void run(async () => {
      const [first] = await api.uploadCase(files);
      if (!first) throw new Error("W przesłanych plikach nie znaleziono materiału do analizy.");
      return first;
    });
  }

  const strongest = events.filter(item => item.stage === "fuse" && item.status === "info")
    .flatMap(item => (item.payload as Partial<FuseEventPayload>).top_evidence ?? [])
    .sort((a, b) => b.bits - a.bits).slice(0, 5);
  const cluster = [...events].reverse().find(item => item.stage === "cluster" && item.status === "done")?.payload as Partial<ClusterResult> | undefined;

  async function openEdge(id: number) {
    setSelected(await api.edge(id));
  }

  async function decide(verdict: "confirmed" | "rejected" | "unsure") {
    if (selected) setSelected(await api.setVerdict(selected.id, verdict));
  }

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
          {strongest.length > 0 && <section><h3>Najsilniejsze dowody</h3><ol>{strongest.map((item, index) => <li key={index}><FamilyDot family={item.family} /> {item.label} · {item.value} · {item.bits} bitów</li>)}</ol></section>}
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
          {ad && edges.length === 0 && <p className="opacity-60">Brak powiązań powyżej progu.</p>}
          <ul className="flex flex-col gap-1">
            {edges.map((edge) => (
              <li key={edge.id}>
                <button
                  onClick={() => openEdge(edge.id)}
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

      {selected && (
        <section className="flex flex-col gap-3 rounded border border-neutral-700 p-4">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="font-semibold">
              Dowody: #{selected.ad_a} ↔ #{selected.ad_b} · {RELATION_LABELS[selected.relation]} · pewność{" "}
              <span className="font-mono">{selected.probability.toFixed(2)}</span>
            </h2>
            <div className="flex gap-2">
              {(["confirmed", "unsure", "rejected"] as const).map((verdict) => (
                <button
                  key={verdict}
                  onClick={() => decide(verdict)}
                  className={`rounded border px-2 py-1 ${selected.verdict === verdict ? "border-sky-500 text-sky-400" : "border-neutral-600"}`}
                >
                  {verdict === "confirmed" ? "Potwierdź" : verdict === "unsure" ? "Niepewne" : "Odrzuć"}
                </button>
              ))}
            </div>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] border-collapse text-left">
              <thead className="text-xs uppercase opacity-60">
                <tr>
                  <th className="py-1 pr-3">Rodzina</th>
                  <th className="py-1 pr-3">Marker</th>
                  <th className="py-1 pr-3">Wartość</th>
                  <th className="py-1 pr-3">Źródła</th>
                  <th className="py-1 text-right">Bity</th>
                </tr>
              </thead>
              <tbody>
                {selected.evidence.map((item, index) => (
                  <tr key={index} className="border-t border-neutral-800 align-top">
                    <td className="py-1.5 pr-3">
                      <span className="flex items-center gap-2">
                        <FamilyDot family={item.family} />
                        {FAMILY_LABELS[item.family]}
                      </span>
                    </td>
                    <td className="py-1.5 pr-3">
                      {item.label}
                      {item.decisive && <span className="ml-2 rounded bg-sky-900 px-1 text-xs text-sky-200">rozstrzyga</span>}
                    </td>
                    <td className="max-w-xs break-all py-1.5 pr-3 font-mono text-xs">
                      {item.df > 0 ? item.value_a : `podobieństwo ${item.similarity.toFixed(2)}`}
                    </td>
                    <td className="py-1.5 pr-3 font-mono text-xs">{item.df > 0 ? `${item.df} z ${item.corpus_n}` : ""}</td>
                    <td className="py-1.5 text-right font-mono">{item.weight_bits.toFixed(1)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </main>
  );
}
