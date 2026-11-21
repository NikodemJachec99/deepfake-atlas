"use client";

import Link from "next/link";
import { useState } from "react";
import { api, artifactDownloadUrl, type ObservationSide } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { ErrorBox, Loading } from "./ui";

function Capture({ side }: { side: ObservationSide }) {
  const date = side.captured_at && new Date(side.captured_at);
  return <article className="min-w-0 space-y-1 break-words border border-line p-2">
    <h4><Link href={`/ads/${side.ad}`} className="text-accent underline">Materiał #{side.ad}</Link> · {side.title || "Brak tytułu"}</h4>
    <p className="break-all font-mono">{side.exact_url || "Adres nieznany"}</p>
    <p>{date && Number.isFinite(date.getTime()) ? date.toLocaleString("pl-PL", { timeZoneName: "short" }) : "Data nieznana"} · {side.time_source || "Źródło daty nieznane"}</p>
    <p>Źródła obserwacji · {side.sources.join(", ") || "Brak informacji"}</p>
    <p>Kontekst · {side.context ? [side.context.browser, side.context.platform, side.context.accept_language].filter(Boolean).join(", ") || "Nieznany" : "Nieznany"}</p>
    <p>Brak zrzutu strony docelowej. Fragment tekstu strony niedostępny.</p>
    {(["har", "html"] as const).map(kind => {
      const file = side.artifacts?.[kind];
      return file && <a key={kind} className="mr-3 text-accent underline" href={artifactDownloadUrl(file.sha256)} download>Pobierz {kind.toUpperCase()}</a>;
    })}
  </article>;
}

export function ObservationPanel({ adId }: { adId: number }) {
  const [open, setOpen] = useState(false);
  const [chosen, setChosen] = useState<number | null>(null);
  const observations = useApi(open ? String(adId) : null, () => api.adObservations(adId));
  const candidates = observations.data?.candidates;
  const partner = candidates?.find(item => item.ad === chosen) ?? candidates?.[0];
  const pair = useApi(open && partner ? `${adId}/${partner.ad}` : null, () => api.compareObservations(adId, partner!.ad));
  const result = pair.data;
  return <section className="grid gap-2 border-y border-line p-2">
    <button className="justify-self-start text-accent underline" aria-expanded={open} onClick={() => setOpen(!open)}>Dwie twarze jednego linku</button>
    {open && (observations.loading ? <Loading /> : observations.error ? <ErrorBox message={observations.error} onRetry={observations.reload} /> :
      !partner ? <p>{observations.data?.message || "Brak drugiego przechwycenia do porównania."}</p> : <>
        <label>Porównaj z materiałem <select className="max-w-full border border-line bg-panel" value={partner.ad} onChange={event => setChosen(Number(event.target.value))}>
          {candidates?.map(item => <option key={item.ad} value={item.ad}>#{item.ad} · {item.url_match_label} · {item.title || item.external_id}</option>)}
        </select></label>
        {pair.loading ? <Loading /> : pair.error ? <ErrorBox message={pair.error} onRetry={pair.reload} /> : result && <>
          <p aria-live="polite">{result.url_match_label} · {result.verdict_label}</p>
          <div className="grid gap-2 lg:grid-cols-2"><Capture side={result.a} /><Capture side={result.b} /></div>
          <h3>Różnice między obserwacjami</h3>
          {result.differences.length ? <ul>{result.differences.map(text => <li key={text}>{text}</li>)}</ul> : <p>API nie wskazało różnic.</p>}
          {!!result.hypotheses.length && <section><h3>Możliwe wyjaśnienia</h3><ul>{result.hypotheses.map(text => <li key={text}>{text}</li>)}</ul></section>}
          {result.limitations.map(text => <p key={text}>{text}</p>)}
          {result.edge && <Link className="text-accent underline" href={`/investigation?ad=${adId}&edge=${result.edge.id}`}>Dowody powiązania #{result.edge.id}</Link>}
          <p>{result.note}</p>
        </>}
      </>)}
  </section>;
}
