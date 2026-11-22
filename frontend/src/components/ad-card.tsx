"use client";

// Karta reklamy z GET /api/ads/{id}: zrzuty, metadane, genom w siedmiu pasmach, powiązania.
// Adres strony pokazujemy jako tekst. Strona oszusta nigdy nie otwiera się z interfejsu.

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useState } from "react";

import { API_URL, FAMILY_LABELS, RELATION_LABELS, api, artifactImageUrl, type AdDetail, type Edge, type Family } from "@/lib/api";
import { SOURCE_LABELS, adTitle, dateTime, day, hostOf, lastSeenLabel } from "@/lib/format";
import { Expert, useExpert } from "@/lib/expert";
import { useApi } from "@/lib/hooks";

import { ObservationPanel } from "./observation-panel";
import { GenomeBands, KeyTraces, MarkerList } from "./genome";
import { Fold, period } from "./simple";
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
  const { expert } = useExpert();
  return <section className="mt-2">
    <h3 className="font-medium">Mowa z nagrania ({expert && `Whisper ${speech.model}, `}pierwsze {speech.audio_s.toLocaleString("pl-PL")} s)</h3>
    <p className={expanded ? "whitespace-pre-wrap" : "line-clamp-3"}>{speech.text}</p>
    <button aria-expanded={expanded} className="text-accent underline" onClick={() => setExpanded(!expanded)}>{expanded ? "Zwiń transkrypcję" : "Rozwiń transkrypcję"}</button>
    {speech.truncated && <p className="text-muted">Transkrypcja obejmuje tylko początek nagrania.</p>}
  </section>;
}

function Recordings({ videos = [] }: { videos?: AdDetail["videos"] }) {
  const { expert } = useExpert();
  if (!videos.length) return null;
  return <section className="grid gap-3">
    <h2 className="text-lg font-semibold">Nagrania</h2>
    {videos.map(video => <figure key={video.sha256} className="min-w-0">
      <figcaption className={expert ? "break-words font-medium" : "break-words text-sm text-muted"}>{video.name}</figcaption>
      <p className="text-muted">
        {video.duration_s != null && <span>Czas trwania: {video.duration_s.toLocaleString("pl-PL")} s </span>}
        {expert && video.width != null && video.height != null && <span> · {video.width} × {video.height} px</span>}
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

/** Rodziny śladów, które dały powiązaniu najwięcej, słowami (bez bitów). */
function topFamilies(edge: Edge, count = 2) {
  return (Object.entries(edge.families) as [Family, number][]).filter(([, value]) => value > 0)
    .sort((a, b) => b[1] - a[1]).slice(0, count).map(([family]) => FAMILY_LABELS[family]).join(", ");
}

const VERDICT_ORDER: Record<string, number> = { confirmed: 0, "": 1, unsure: 2, rejected: 3 };

function sortEdges(edges: Edge[]) {
  return [...edges].sort((a, b) => (VERDICT_ORDER[a.verdict] ?? 1) - (VERDICT_ORDER[b.verdict] ?? 1) || b.bits - a.bits);
}

function KeyLinks({ ad, edges }: { ad: AdDetail; edges: Edge[] | undefined }) {
  if (!edges) return null;
  const top = sortEdges(edges.filter(edge => edge.verdict !== "rejected")).slice(0, 3);
  return <section className="grid gap-2">
    <h2 className="text-lg font-semibold">Najważniejsze powiązania</h2>
    {top.length ? <ul className="grid gap-2">{top.map(edge => {
      const other = edge.ad_a === ad.id ? edge.ad_b : edge.ad_a;
      const families = topFamilies(edge);
      return <li key={edge.id} className="rounded-md border border-line bg-raised p-2">
        <p className="flex flex-wrap items-center gap-x-2"><Link href={`/ads/${other}`} className="font-medium text-accent hover:underline">Reklama #{other}</Link>
          <span>{RELATION_LABELS[edge.relation]}</span>{edge.verdict && <VerdictTag verdict={edge.verdict} />}</p>
        {families && <p className="text-sm text-muted">Najwięcej wspólnego: {families.toLocaleLowerCase("pl")}</p>}
      </li>;
    })}</ul> : <p className="text-muted">Brak powiązań z innymi reklamami.</p>}
    {edges.length > top.length && <Link href={`/ads/${ad.id}?tab=links`} scroll={false} className="text-accent underline">Wszystkie powiązania ({edges.length})</Link>}
  </section>;
}

function MaterialWorkspace({ ad, edges }: { ad: AdDetail; edges?: Edge[] }) {
  const [selected, setSelected] = useState(0);
  const { expert } = useExpert();
  const image = ad.creatives[selected] ?? ad.creatives[0];
  return <section className="border-b border-line">
    <header className="border-b border-line px-5 py-4">
      <p className="text-muted">Reklama #{ad.id}{ad.case && ` · Sprawa ${ad.case}`}</p>
      <h1 className="my-1 text-2xl font-semibold tracking-tight text-pretty">{adTitle(ad)}</h1>
      <Labels ad={ad} />
    </header>
    <div className="grid xl:grid-cols-[minmax(0,1fr)_minmax(22rem,34%)]">
      <div className="min-w-0 space-y-4 p-5">
        {expert && (ad.creatives.length > 0 || !ad.videos?.length) && <h2 className="text-lg font-semibold">Zrzuty reklamy</h2>}
        {image && <figure className="grid gap-2">
          <a className="block rounded-lg border border-line bg-panel p-2" href={artifactImageUrl(image)} target="_blank" rel="noreferrer" title="Otwórz zrzut w pełnym rozmiarze">
            {/* eslint-disable-next-line @next/next/no-img-element -- obraz dowodowy z API */}
            <img className={`mx-auto w-full object-contain ${expert ? "max-h-56" : "max-h-[28rem]"}`} src={artifactImageUrl(image)} alt={`Podgląd zrzutu ${ad.creatives.indexOf(image) + 1}`} />
          </a>
          <a className="w-fit text-sm text-accent underline" href={artifactImageUrl(image)} target="_blank" rel="noreferrer">Otwórz zrzut w pełnym rozmiarze</a>
        </figure>}
        {ad.creatives.length > (expert ? 0 : 1) ? <div className="flex flex-wrap gap-3">
          {ad.creatives.map((sha, i) => <button key={sha} type="button" onClick={() => setSelected(i)}
            aria-pressed={image === sha} className="max-w-full rounded-md border border-line bg-panel p-1 text-left aria-pressed:outline-2 aria-pressed:outline-accent">
            {/* eslint-disable-next-line @next/next/no-img-element -- obraz dowodowy z API */}
            <img className="h-16 max-w-full object-contain" alt="" src={artifactImageUrl(sha)} />
            <span className="block px-1 py-1">Zrzut {i + 1}</span>
          </button>)}
        </div> : !ad.creatives.length && !ad.videos?.length && <p className="text-muted">Brak zrzutu reklamy w materiale.</p>}
        <Recordings videos={ad.videos} />
        <AdText ad={ad} />
        {ad.genome.some(band => band.markers.some(marker => marker.kind === "white_dom_hash")) && <p>Cloaking: automat i odbiorca otrzymali różne wersje strony.</p>}
        {ad.landing_url?.trim() && <ObservationPanel adId={ad.id} />}
        <Link href={`/investigation?ad=${ad.id}`} className="inline-block w-fit rounded-md border border-line bg-panel px-3 py-2 text-sm font-medium text-accent hover:underline">Pokaż na grafie powiązań</Link>
      </div>
      <aside className="min-w-0 space-y-5 border-t border-line bg-panel p-5 xl:border-t-0 xl:border-l">
        <section className="space-y-3">
          <h2 className="text-lg font-semibold">{expert ? "Wybrany materiał" : "W skrócie"}</h2>
          <AdMeta ad={ad} />
        </section>
        {!expert && <KeyLinks ad={ad} edges={edges} />}
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
        <Link key={keyword} href={`/archive?q=${encodeURIComponent(keyword)}`} className="rounded-sm border border-line px-1 text-xs text-muted hover:border-line-strong hover:text-fg" title="Słowo kluczowe. Kliknij, aby szukać w archiwum.">
          {keyword}
        </Link>
      ))}
      {keywords.length > 8 && <button aria-expanded={expanded} className="text-accent underline" onClick={() => setExpanded(!expanded)}>{expanded ? "Pokaż mniej" : `Więcej słów (${keywords.length - 8})`}</button>}
    </div>
  );
}

export function AdMeta({ ad }: { ad: AdDetail }) {
  const cert = ad.labels.cert_pl;
  const { expert } = useExpert();
  if (!expert) {
    const seen = period([ad]);
    return <div className="grid gap-3">
      <dl>
        <Field label="Kampania"><GroupLink group={ad.campaign} /></Field>
        <Field label="Operator"><GroupLink group={ad.operator} /></Field>
        <Field label="Domena"><Mono>{hostOf(ad.landing_url) || "brak"}</Mono></Field>
        <Field label="CERT Polska">{cert ? <span className="flex flex-wrap items-center gap-1.5"><Tag tone="rejected">Lista Ostrzeżeń</Tag>{cert.added_at && <span className="text-muted">od {day(cert.added_at)}</span>}</span>
          : <span className="text-muted">domeny nie ma na liście</span>}</Field>
        <Field label="Reklamodawca">{ad.advertiser?.name || <span className="text-faint">nieustalony</span>}</Field>
        <Field label="Źródło">{SOURCE_LABELS[ad.source] ?? ad.source}{ad.case && <span className="text-muted"> · sprawa {ad.case}</span>}</Field>
        <Field label="Widziana">{seen ? (seen.includes(" do ") ? `od ${seen}` : seen) : <span className="text-faint">brak daty</span>}</Field>
      </dl>
      <Fold title="Pełny adres i identyfikatory">
        <dl>
          <Field label="Adres"><Mono className="break-all text-muted">{ad.landing_url || "brak adresu docelowego"}</Mono></Field>
          <Field label="Identyfikator"><Mono className="break-all text-muted">{ad.external_id}</Mono></Field>
          {ad.labels.bundle && <Field label="Paczka">{ad.labels.bundle}</Field>}
          {ad.advertiser?.payer && <Field label="Płatnik">{ad.advertiser.payer}</Field>}
        </dl>
      </Fold>
    </div>;
  }
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
      <Field label={lastSeenLabel(ad.source)}><Mono>{dateTime(ad.last_seen) || "brak daty"}</Mono></Field>
    </dl>
  );
}

export function EdgeRows({ edges, adId, onEdge, selected }: { edges: Edge[]; adId: number; onEdge: (edge: Edge) => void; selected?: number | null }) {
  const { expert } = useExpert();
  if (edges.length > 0 && !expert) return (
    <div className="atlas-table" role="region" aria-label="Powiązania reklam" tabIndex={0}>
      <table className="dense">
        <thead><tr><th>Z reklamą</th><th>Relacja</th><th className="max-md:hidden">Najwięcej wspólnego</th><th>Decyzja</th></tr></thead>
        <tbody>{sortEdges(edges).map(edge => <tr key={edge.id} data-selected={selected === edge.id} onClick={() => onEdge(edge)} className="cursor-pointer">
          <td><button type="button" className="table-action" aria-label={`Dowody powiązania reklam #${edge.ad_a} i #${edge.ad_b}`}>#{edge.ad_a === adId ? edge.ad_b : edge.ad_a}</button></td>
          <td><RelationTag relation={edge.relation} duplicate={edge.duplicate} /></td>
          <td className="text-muted max-md:hidden">{topFamilies(edge) || "—"}</td>
          <td>{edge.verdict ? <VerdictTag verdict={edge.verdict} /> : <span className="text-faint">do oceny</span>}</td>
        </tr>)}</tbody>
      </table>
    </div>
  );
  if (edges.length === 0) return <Empty title="Brak powiązań powyżej progu">Silnik nie znalazł dla tej reklamy wspólnych śladów z resztą korpusu.</Empty>;
  return (
    <div className="atlas-table" role="region" aria-label="Powiązania reklam" tabIndex={0}>
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
    </div>
  );
}

// Wersja do inspektora: jedna kolumna.
export function AdCard({ adId, onEdge, selectedEdge, full = false }: { adId: number; onEdge: (edge: Edge) => void; selectedEdge?: number | null; full?: boolean }) {
  const params = useSearchParams();
  const sections = [
    { key: "", label: "Materiał" }, { key: "links", label: "Powiązania" },
    { key: "traces", label: "Ślady" }, { key: "history", label: "Historia" },
  ];
  const tab = sections.find(section => section.key === params.get("tab"))?.label ?? "Materiał";
  const ad = useApi(`ad:${adId}`, () => api.ad(adId));
  const edges = useApi(ad.data ? `ad-edges:${adId}` : null, () => api.adEdges(adId));
  if (ad.loading) return <Loading label="Pobieranie karty reklamy" />;
  if (ad.error) return <ErrorBox message={ad.error} onRetry={ad.reload} missing={ad.status === 404 ? { description: `Nie ma takiej reklamy (#${adId}).`, href: "/archive", link: "Przejdź do archiwum" } : undefined} />;
  const data = ad.data;
  if (!data) return null;
  return (
    <div className="flex flex-col">
      {full && <nav aria-label="Sekcje reklamy" className="flex flex-wrap gap-2 border-b border-line p-2">{sections.map(({ key, label }) => {
        const query = new URLSearchParams(params.toString());
        if (key) query.set("tab", key);
        else query.delete("tab");
        return <Link key={label} href={`/ads/${adId}${query.size ? "?" + query : ""}`} scroll={false} aria-current={tab === label ? "page" : undefined}
          className="inline-flex min-h-9 items-center rounded px-3 aria-[current=page]:bg-accent-soft">{label}</Link>;
      })}</nav>}
      {full && tab !== "Materiał" && <h1 className="px-3 py-2 font-semibold">Reklama #{adId} · {adTitle(data)}</h1>}
      {full ? tab === "Materiał" && <MaterialWorkspace key={adId} ad={data} edges={edges.data ?? undefined} /> : <div className="flex flex-col gap-2 border-b border-line p-2">
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
      {full && tab === "Ślady" && <Expert fallback={<div className="border-b border-line p-3"><KeyTraces genome={data.genome} /></div>}>{null}</Expert>}
      {(!full || tab === "Powiązania") && <><p className="cap flex h-7 items-center border-b border-line px-2">Powiązania</p>
      {edges.loading ? <Loading /> : edges.error ? <ErrorBox message={edges.error} onRetry={edges.reload} /> : <EdgeRows edges={edges.data ?? []} adId={adId} onEdge={onEdge} selected={selectedEdge} />}</>}
      {(!full || tab === "Ślady") && <Expert fallback={<div className="border-b border-line p-3">
        <Fold title={`Wszystkie ślady (${data.genome.reduce((sum, band) => sum + band.markers.length, 0)})`}><MarkerList videos={data.videos} genome={data.genome} initiallyOpen={full} /></Fold>
      </div>}><p className="cap flex h-7 items-center border-y border-line px-2">Markery</p>
      <MarkerList videos={data.videos} genome={data.genome} initiallyOpen={full} /></Expert>}
      {full && tab === "Historia" && <dl className="p-4"><Field label="Pierwsza obserwacja">{dateTime(data.first_seen) || "Brak daty"}</Field><Field label={lastSeenLabel(data.source)}>{dateTime(data.last_seen) || "Brak daty"}</Field></dl>}
    </div>
  );
}
