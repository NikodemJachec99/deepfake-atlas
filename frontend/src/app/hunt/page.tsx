"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, ApiError, artifactDownloadUrl, artifactImageUrl, type HuntCandidate, type HuntRun } from "@/lib/api";
import { bits, dateTime, errorText } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import { ErrorBox, Loading } from "@/components/ui";

function Candidate({ item }: { item: HuntCandidate }) {
  const [pending, setPending] = useState(false);
  const [submitted, setSubmitted] = useState(Boolean(item.analysis));
  const [error, setError] = useState("");
  async function analyze() {
    setPending(true);
    setError("");
    try { await api.analyzeHuntCandidate(item.id); setSubmitted(true); }
    catch (reason) {
      if (reason instanceof ApiError && reason.status === 409) setSubmitted(true);
      else setError(errorText(reason));
    } finally { setPending(false); }
  }
  return <article id={`kandydat-${item.id}`} className="grid min-w-0 gap-2 border-b border-line py-4">
    <h2 className="break-all text-lg font-semibold">{item.domain}</h2>
    <p>{item.status_label} · <Link className="text-accent" href={`/operators/${item.operator_id}`}>{item.operator}</Link> · {item.sources.map(source => source === "crtsh" ? "crt.sh" : "CERT Polska").join(", ")}</p>
    <p>Ocena wstępna {item.prelim_score.toLocaleString("pl-PL")} · Siła dowodu {item.bits == null ? "brak oceny" : bits(item.bits) + " bita"} · Prawdopodobieństwo {item.probability == null ? "brak oceny" : item.probability.toLocaleString("pl-PL", { style: "percent" })}</p>
    <p>{item.note} · Sprawdzenie: {dateTime(item.checked_at) || "jeszcze nie sprawdzono"}</p>
    <details><summary>Szczegóły kandydata</summary>
      {item.cert && <p>Certyfikat · {item.cert.issuer} · {item.cert.serial} · {dateTime(item.cert.not_before)}</p>}
      <p>Składniki oceny · {[...item.score_parts.tokens.map(t => t.token + " (" + t.weight + ")"), item.score_parts.template, item.score_parts.issuer].filter(Boolean).join(", ") || "brak"}</p>
      <ul>{item.evidence.map((e, i) => <li key={i}>{e.label} · {e.value} · {bits(e.bits)} bita {e.ad_ids.map(id => <Link key={id} className="mr-2 text-accent" href={`/ads/${id}`}>Reklama #{id}</Link>)}</li>)}</ul>
      {item.screenshot_sha && <a href={artifactImageUrl(item.screenshot_sha)}>Zobacz zrzut strony</a>}
      {item.html_sha && <a className="ml-2 text-accent" href={artifactDownloadUrl(item.html_sha)} download>Pobierz HTML</a>}
    </details>
    <button className="justify-self-start rounded border border-line px-3 py-1" disabled={pending || submitted} onClick={analyze}>{submitted ? "Zgłoszono do analizy" : pending ? "Zgłaszanie…" : "Zgłoś do analizy"}</button>
    {error && <ErrorBox message={error}/>}
  </article>;
}

export default function HuntPage() {
  const list = useApi("hunt", () => api.hunt());
  const [run, setRun] = useState<HuntRun | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const reload = list.reload;
  const runId = run?.id;
  const running = run?.status === "queued" || run?.status === "running";
  useEffect(() => {
    if (!runId || !running) return;
    let live = true;
    let timer: ReturnType<typeof setTimeout>;
    async function poll(id: string) {
      try {
        const next = await api.huntRunStatus(id);
        if (!live) return;
        setRun(next);
        setError("");
        if (next.status === "done" || next.status === "failed") { reload(); return; }
      } catch (reason) { if (live) setError(errorText(reason)); }
      if (live) timer = setTimeout(() => poll(id), 3000);
    }
    void poll(runId);
    return () => { live = false; clearTimeout(timer); };
  }, [runId, running, reload]);
  async function start() {
    setPending(true); setError("");
    try { setRun(await api.huntRun()); }
    catch (reason) {
      if (reason instanceof ApiError && reason.status === 409) {
        try { setRun((await api.huntRuns()).results[0] ?? null); }
        catch (failure) { setError(errorText(failure)); }
      } else setError(errorText(reason));
    } finally { setPending(false); }
  }
  useEffect(() => {
    if (list.data && window.location.hash) document.getElementById(window.location.hash.slice(1))?.scrollIntoView();
  }, [list.data]);
  return <main className="atlas-page"><h1 className="atlas-title">Łowca domen</h1>
    <button className="self-start rounded bg-accent px-3 py-2 text-on-accent" disabled={pending || running} onClick={start}>Uruchom przebieg</button>
    {run && <p role="status">Przebieg · {({ queued: "w kolejce", running: "w toku", done: "zakończony", failed: "błąd" })[run.status]} {run.error}</p>}
    {error && <ErrorBox message={error}/>}
    {list.loading ? <Loading/> : list.error ? <ErrorBox message={list.error} onRetry={reload}/> : list.data && <>
      <p>Kandydaci: {list.data.count} · Potwierdzone na tej stronie: {list.data.results.filter(c => c.status === "confirmed").length}</p>
      {list.data.results.map(item => <Candidate key={item.id} item={item}/>)}
    </>}
  </main>;
}
