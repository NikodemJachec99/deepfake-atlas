"use client";

// Karta reklamy z GET /api/ads/{id}: zrzuty, metadane, genom w siedmiu pasmach, powiązania.
// Adres strony pokazujemy jako tekst. Strona oszusta nigdy nie otwiera się z interfejsu.

import Link from "next/link";

import { api, artifactImageUrl, type AdDetail, type Edge } from "@/lib/api";
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

export function Labels({ ad }: { ad: Pick<AdDetail, "labels"> }) {
  const topics = ad.labels.topics ?? [];
  const keywords = ad.labels.keywords ?? [];
  if (topics.length + keywords.length === 0) return null;
  return (
    <div className="flex flex-wrap items-center gap-1">
      {topics.map((topic) => (
        <Tag key={topic} tone="accent">{topic}</Tag>
      ))}
      {keywords.map((keyword) => (
        <Link key={keyword} href={`/archive?q=${encodeURIComponent(keyword)}`} className="rounded-sm border border-line px-1 text-[0.85rem] text-muted hover:border-line-strong hover:text-fg" title="Słowo kluczowe. Kliknij, aby szukać w archiwum.">
          {keyword}
        </Link>
      ))}
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
      <Field label="Widziana">
        <Mono>{dateTime(ad.first_seen) || "?"}</Mono> <span className="text-faint">do</span> <Mono>{dateTime(ad.last_seen) || "?"}</Mono>
      </Field>
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
          <th>Pewność</th>
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
  const ad = useApi(`ad:${adId}`, () => api.ad(adId));
  const edges = useApi(`ad-edges:${adId}`, () => api.adEdges(adId));
  if (ad.loading) return <Loading label="Pobieranie karty reklamy" />;
  if (ad.error) return <ErrorBox message={ad.error} onRetry={ad.reload} />;
  const data = ad.data;
  if (!data) return null;
  return (
    <div className="flex flex-col">
      <div className="flex flex-col gap-2 border-b border-line p-2">
        <div className="flex items-center justify-between gap-2">
          <Mono className="text-muted">reklama #{data.id}</Mono>
          {!full && <Link href={`/ads/${data.id}`} className="text-accent hover:underline">
            Pełna karta
          </Link>}
        </div>
        <h1 className="text-[1.08rem] font-medium">{adTitle(data)}</h1>
        <Labels ad={data} />
        <Creatives shas={data.creatives} size="h-32" />
        <AdMeta ad={data} />
        {full && <ObservationPanel key={adId} adId={adId} />}
        {data.text && <p className="max-h-24 overflow-auto border-l border-line-strong pl-2 whitespace-pre-wrap text-muted">{data.text}</p>}
      </div>
      <div className="border-b border-line p-2">
        <GenomeBands genome={data.genome} caption="Genom reklamy" />
      </div>
      <p className="cap flex h-7 items-center border-b border-line px-2">Powiązania</p>
      {edges.loading ? <Loading /> : edges.error ? <ErrorBox message={edges.error} onRetry={edges.reload} /> : <EdgeRows edges={edges.data ?? []} adId={adId} onEdge={onEdge} selected={selectedEdge} />}
      <p className="cap flex h-7 items-center border-y border-line px-2">Markery</p>
      <MarkerList genome={data.genome} initiallyOpen={full} />
    </div>
  );
}
