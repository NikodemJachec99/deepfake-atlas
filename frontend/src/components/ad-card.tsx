"use client";

// Karta reklamy z GET /api/ads/{id}: zrzuty, metadane, genom w siedmiu pasmach, powiązania.
// Adres strony pokazujemy jako tekst. Strona oszusta nigdy nie otwiera się z interfejsu.

import Link from "next/link";
import { useState } from "react";

import { API_URL, api, artifactImageUrl, type AdDetail, type Edge } from "@/lib/api";
import { SOURCE_LABELS, adTitle, dateTime, day, hostOf } from "@/lib/format";
import { useApi } from "@/lib/hooks";

import { ObservationPanel } from "./observation-panel";
import { GenomeBands, MarkerList } from "./genome";
import { Empty, ErrorBox, Field, GroupLink, Loading, Meter, Mono, RelationTag, Tag, VerdictTag } from "./ui";

export function Creatives({ shas, size = "h-40" }: { shas: string[]; size?: string }) {
  if (shas.length === 0) return <p className="text-faint">Brak zrzutu reklamy w materiale.</p>;
  return (
    <div className="flex gap-2 overflow-x-auto">
      {shas.map((sha) => (
        <a key={sha} href={artifactImageUrl(sha)} target="_blank" rel="noreferrer" className="shrink-0 border border-line bg-bg" title="Otwórz zrzut reklamy w nowej karcie">
          {/* eslint-disable-next-line @next/next/no-img-element -- obraz z API dowodów */}
          <img src={artifactImageUrl(sha)} alt="Zrzut reklamy" loading="lazy" className={`${size} w-auto object-contain`} />
        </a>
      ))}
    </div>
  );
}

function AdText({ ad }: { ad: AdDetail }) {
  const [expanded, setExpanded] = useState(false);
  if (!ad.text) return null;
  const frameText = ad.source === "capture" && !!ad.videos?.length;
  return <figure className="border-l-2 border-line-strong pl-3">
    {frameText && <figcaption className="text-sm text-muted">Tekst odczytany z klatek nagrania (OCR)</figcaption>}
    <blockquote className={frameText && !expanded ? "line-clamp-3 whitespace-pre-wrap" : "whitespace-pre-wrap"}>{ad.text}</blockquote>
    {frameText && <button aria-expanded={expanded} className="text-accent underline" onClick={() => setExpanded(!expanded)}>{expanded ? "Zwiń OCR" : "Rozwiń OCR"}</button>}
  </figure>;
}

function Speech({ speech }: { speech: NonNullable<AdDetail["videos"][number]["speech"]> }) {
  const [expanded, setExpanded] = useState(false);
  return <section className="mt-2">
    <h3 className="font-medium">Mowa z nagrania (Whisper {speech.model}, pierwsze {speech.audio_s.toLocaleString("pl-PL")} s)</h3>
    <p className={expanded ? "whitespace-pre-wrap" : "line-clamp-3"}>{speech.text}</p>
    <button aria-expanded={expanded} className="text-accent underline" onClick={() => setExpanded(!expanded)}>{expanded ? "Zwiń transkrypcję" : "Rozwiń transkrypcję"}</button>
    {speech.truncated && <p className="text-muted">Transkrypcja obejmuje tylko początek nagrania.</p>}
  </section>;
}

function Recordings({ videos = [] }: { videos?: AdDetail["videos"] }) {
  if (!videos.length) return null;
  return <section className="grid gap-3">
    <h2 className="text-lg font-semibold">Nagrania</h2>
    {videos.map(video => <figure key={video.sha256} className="min-w-0">
      <figcaption className="break-words font-medium">{video.name}</figcaption>
      <p className="text-muted">
        {video.duration_s != null && <span>Czas trwania: {video.duration_s.toLocaleString("pl-PL")} s </span>}
        {video.width != null && video.height != null && <span> · {video.width} × {video.height} px</span>}
      </p>
      {video.playable && video.url ? <>
        <video controls preload="metadata" aria-label={video.name} src={API_URL + video.url}
          poster={video.poster ? API_URL + video.poster.url : undefined} className="max-h-80 w-full bg-black" />
        {video.poster && <p className="text-sm text-muted">Klatka poglądowa z nagrania · {video.poster.at_s.toLocaleString("pl-PL")} s</p>}
      </> : <div><p>Nagranie niedostępne do odtworzenia. {video.missing.some(reason => reason.includes("ponad limit magazynu")) ? "Plik przekracza limit magazynu." : "Brak dostępnej kopii do odtworzenia."}</p>
        {video.missing.length > 0 && <details><summary>Szczegóły nagrania</summary><ul>{video.missing.map(reason => <li key={reason}>{reason}</li>)}</ul></details>}</div>}
      {video.speech?.text && <Speech speech={video.speech} />}
    </figure>)}
  </section>;
}

function MaterialWorkspace({ ad }: { ad: AdDetail }) {
  const [selected, setSelected] = useState(0);
  const image = ad.creatives[selected] ?? ad.creatives[0];
  return <section className="border-b border-line">
    <header className="border-b border-line px-5 py-4">
      <p className="text-muted">Reklama #{ad.id}{ad.case && ` · Sprawa ${ad.case}`}</p>
      <h1 className="my-1 text-2xl font-semibold tracking-tight">{adTitle(ad)}</h1>
      <Labels ad={ad} />
    </header>
    <div className="grid xl:grid-cols-[minmax(0,1fr)_minmax(22rem,32%)]">
      <div className="min-w-0 space-y-4 p-5">
        {(ad.creatives.length > 0 || !ad.videos?.length) && <h2 className="text-lg font-semibold">Zrzuty reklamy</h2>}
        {image && <a className="block text-accent underline" href={artifactImageUrl(image)} target="_blank" rel="noreferrer">
          {/* eslint-disable-next-line @next/next/no-img-element -- obraz dowodowy z API */}
          <img className="mb-2 max-h-56 w-full object-contain" src={artifactImageUrl(image)} alt={`Podgląd zrzutu ${ad.creatives.indexOf(image) + 1}`} />
          Otwórz zrzut w pełnym rozmiarze
        </a>}
        {ad.creatives.length ? <div className="flex flex-wrap gap-3">
          {ad.creatives.map((sha, i) => <button key={sha} type="button" onClick={() => setSelected(i)}
            aria-pressed={image === sha} className="max-w-full rounded-md border border-line bg-panel p-1 text-left aria-pressed:outline-2 aria-pressed:outline-accent">
            {/* eslint-disable-next-line @next/next/no-img-element -- obraz dowodowy z API */}
            <img className="h-16 max-w-full object-contain" alt="" src={artifactImageUrl(sha)} />
            <span className="block px-1 py-1">Zrzut {i + 1}</span>
          </button>)}
        </div> : !ad.videos?.length && <p className="text-muted">Brak zrzutu reklamy w materiale.</p>}
        <Recordings videos={ad.videos} />
        <AdText ad={ad} />
        {ad.genome.some(band => band.markers.some(marker => marker.kind === "white_dom_hash")) && <p>Cloaking: automat i odbiorca otrzymali różne wersje strony.</p>}
        {ad.landing_url?.trim() && <ObservationPanel adId={ad.id} />}
        <Link href={`/investigation?ad=${ad.id}`} className="inline-block w-fit rounded-md border border-line bg-panel px-3 py-2 text-sm font-medium text-accent hover:underline">Pokaż na grafie powiązań</Link>
      </div>
      <aside className="min-w-0 space-y-3 border-t border-line bg-panel p-5 xl:border-t-0 xl:border-l">
        <h2 className="text-lg font-semibold">Wybrany materiał</h2>
        <AdMeta ad={ad} />
      </aside>
    </div>
  </section>;
}

export function Labels({ ad }: { ad: Pick<AdDetail, "labels"> }) {
  const [expanded, setExpanded] = useState(false);
  const topics = ad.labels.topics ?? [];
  const keywords = ad.labels.keywords ?? [];
  if (topics.length + keywords.length === 0) return null;
  return (
    <div className="flex flex-wrap items-center gap-1">
      {topics.map((topic) => (
        <Tag key={topic} tone="accent">{topic}</Tag>
      ))}
      {(expanded ? keywords : keywords.slice(0, 8)).map((keyword) => (
        <Link key={keyword} href={`/archive?q=${encodeURIComponent(keyword)}`} className="rounded-sm border border-line px-1 text-[0.85rem] text-muted hover:border-line-strong hover:text-fg" title="Słowo kluczowe. Kliknij, aby szukać w archiwum.">
          {keyword}
        </Link>
      ))}
      {keywords.length > 8 && <button aria-expanded={expanded} className="text-accent underline" onClick={() => setExpanded(!expanded)}>{expanded ? "Pokaż mniej" : `Więcej słów (${keywords.length - 8})`}</button>}
    </div>
  );
}

export function AdMeta({ ad }: { ad: AdDetail }) {
  const cert = ad.labels.cert_pl;
  return (
    <dl>
      <Field label="Domena">
        <Mono>{hostOf(ad.landing_url) || "brak"}</Mono>
      </Field>
      <Field label="Adres">
        <Mono className="break-all text-muted">{ad.landing_url || "brak adresu docelowego"}</Mono>
      </Field>
      <Field label="Sprawa">{ad.case ? <Link href={`/archive?case=${encodeURIComponent(ad.case)}`} className="font-mono text-[0.92rem] text-accent hover:underline">{ad.case}</Link> : <span className="text-faint">brak</span>}{ad.labels.bundle && <span className="text-muted"> · paczka {ad.labels.bundle}</span>}</Field>
      <Field label="Kampania">
        <GroupLink group={ad.campaign} />
      </Field>
      <Field label="Operator">
        <GroupLink group={ad.operator} />
      </Field>
      <Field label="Reklamodawca">{ad.advertiser?.name ? <>{ad.advertiser.name}{ad.advertiser.payer && <span className="text-muted"> · płatnik {ad.advertiser.payer}</span>}</> : <span className="text-faint">nieustalony</span>}</Field>
      <Field label="CERT Polska">
        {cert ? (
          <span className="flex flex-wrap items-center gap-1.5">
            <Tag tone="rejected">Lista Ostrzeżeń</Tag>
            <Mono>{cert.domain}</Mono>
            {cert.added_at && <span className="text-muted">wpis {day(cert.added_at)}</span>}
            {cert.removed_at && <span className="text-muted">usunięto {day(cert.removed_at)}</span>}
          </span>
        ) : (
          <span className="text-muted">domeny nie ma na Liście Ostrzeżeń</span>
        )}
      </Field>
      <Field label="Źródło">
        {SOURCE_LABELS[ad.source] ?? ad.source} <Mono className="text-muted">{ad.external_id}</Mono>
      </Field>
      <Field label="Pierwsza obserwacja"><Mono>{dateTime(ad.first_seen) || "brak daty"}</Mono></Field>
      <Field label={ad.source === "capture" || ad.source === "manual" ? "Import do systemu" : "Ostatnia obserwacja"}><Mono>{dateTime(ad.last_seen) || "brak daty"}</Mono></Field>
    </dl>
  );
}

export function EdgeRows({ edges, adId, onEdge, selected }: { edges: Edge[]; adId: number; onEdge: (edge: Edge) => void; selected?: number | null }) {
  if (edges.length === 0) return <Empty title="Brak powiązań powyżej progu">Silnik nie znalazł dla tej reklamy wspólnych śladów z resztą korpusu.</Empty>;
  return (
    <table className="dense">
      <thead>
        <tr>
          <th>Z reklamą</th>
          <th>Relacja</th>
          <th>Wynik modelu (niekalibrowany)</th>
          <th className="text-right">Bity</th>
          <th>Decyzja</th>
        </tr>
      </thead>
      <tbody>
        {edges.map((edge) => (
          <tr key={edge.id} data-selected={selected === edge.id} onClick={() => onEdge(edge)} className="cursor-pointer">
            <td><button type="button" className="table-action" aria-label={`Dowody powiązania reklam #${edge.ad_a} i #${edge.ad_b}`}>
              #{edge.ad_a === adId ? edge.ad_b : edge.ad_a}
            </button></td>
            <td>
              <RelationTag relation={edge.relation} duplicate={edge.duplicate} />
            </td>
            <td>
              <Meter value={edge.probability} width={48} />
            </td>
            <td className="text-right font-mono text-[0.92rem]">{edge.bits.toFixed(1).replace(".", ",")}</td>
            <td>
              <VerdictTag verdict={edge.verdict} />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

// Wersja do inspektora: jedna kolumna.
export function AdCard({ adId, onEdge, selectedEdge, full = false }: { adId: number; onEdge: (edge: Edge) => void; selectedEdge?: number | null; full?: boolean }) {
  const [tab, setTab] = useState("Materiał");
  const ad = useApi(`ad:${adId}`, () => api.ad(adId));
  const edges = useApi(ad.data ? `ad-edges:${adId}` : null, () => api.adEdges(adId));
  if (ad.loading) return <Loading label="Pobieranie karty reklamy" />;
  if (ad.error) return <ErrorBox message={ad.error} onRetry={ad.reload} missing={ad.status === 404 ? { description: `Nie ma takiej reklamy (#${adId}).`, href: "/archive", link: "Przejdź do archiwum" } : undefined} />;
  const data = ad.data;
  if (!data) return null;
  return (
    <div className="flex flex-col">
      {full && <nav aria-label="Sekcje reklamy" className="flex flex-wrap gap-2 border-b border-line p-2">{["Materiał", "Powiązania", "Ślady", "Historia"].map(t => <button key={t} aria-pressed={tab === t} className="rounded px-3 aria-pressed:bg-accent-soft" onClick={() => setTab(t)}>{t}</button>)}</nav>}
      {full && tab !== "Materiał" && <h1 className="px-3 py-2 font-semibold">Reklama #{adId} · {adTitle(data)}</h1>}
      {full ? tab === "Materiał" && <MaterialWorkspace key={adId} ad={data} /> : <div className="flex flex-col gap-2 border-b border-line p-2">
        <div className="flex items-center justify-between gap-2">
          <Mono className="text-muted">reklama #{data.id}</Mono>
          <Link href={`/ads/${data.id}`} className="text-accent hover:underline">
            Pełna karta
          </Link>
        </div>
        <h1 className="text-[1.08rem] font-medium">{adTitle(data)}</h1>
        <Labels ad={data} />
        {(data.creatives.length > 0 || !data.videos?.length) && <Creatives shas={data.creatives} size="h-32" />}
        <Recordings videos={data.videos} />
        <AdMeta ad={data} />
        {data.text && <div className="max-h-24 overflow-auto"><AdText ad={data} /></div>}
      </div>}
      {(!full || tab === "Ślady") && <div className="border-b border-line p-2">
        <GenomeBands genome={data.genome} caption="Genom reklamy" />
      </div>}
      {(!full || tab === "Powiązania") && <><p className="cap flex h-7 items-center border-b border-line px-2">Powiązania</p>
      {edges.loading ? <Loading /> : edges.error ? <ErrorBox message={edges.error} onRetry={edges.reload} /> : <EdgeRows edges={edges.data ?? []} adId={adId} onEdge={onEdge} selected={selectedEdge} />}</>}
      {(!full || tab === "Ślady") && <><p className="cap flex h-7 items-center border-y border-line px-2">Markery</p>
      <MarkerList videos={data.videos} genome={data.genome} initiallyOpen={full} /></>}
      {full && tab === "Historia" && <dl className="p-4"><Field label="Pierwsza obserwacja">{dateTime(data.first_seen) || "Brak daty"}</Field><Field label={["capture", "manual"].includes(data.source) ? "Import do systemu" : "Ostatnia obserwacja"}>{dateTime(data.last_seen) || "Brak daty"}</Field></dl>}
    </div>
  );
}
