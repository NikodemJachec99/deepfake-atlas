"use client";

// Genom reklamy: siedem pasm, każde to rodzina markerów. Znacznik na paśmie to jeden marker z API.

import { ChevronDown, ChevronRight, Download } from "lucide-react";
import { useState } from "react";

import { API_URL, artifactImageUrl, artifactDownloadUrl, type AdDetail, type Marker } from "@/lib/api";
import { markerValue, famVar, plural } from "@/lib/format";

import { FamilyDot, Mono, Tag, cx } from "./ui";

type Genome = AdDetail["genome"];

const reklam = (n: number) => `${n} ${plural(n, "reklamie", "reklamach", "reklamach")}`;

function Tick({ marker, color, matched }: { marker: Marker; color: string; matched?: boolean }) {
  const shared = marker.ad_count > 1;
  return (
    <span
      title={`${marker.label}: ${markerValue(marker.value, marker.display_value)}\nwystępuje w ${reklam(marker.ad_count)}${marker.decisive ? "\nmarker rozstrzygający" : ""}`}
      className="w-1.5 shrink-0 rounded-[1px] border"
      style={{
        height: marker.decisive ? 16 : 10,
        borderColor: color,
        background: shared ? color : "transparent",
        opacity: matched === false ? 0.3 : 1,
      }}
    />
  );
}

// `other`: drugi genom do porównania. Znaczniki bez odpowiednika po drugiej stronie są przygaszone.
export function GenomeBands({ genome, other, caption }: { genome: Genome; other?: Genome; caption?: string }) {
  const otherValues = other ? new Set(other.flatMap((band) => band.markers.map((m) => `${m.kind}\u0000${m.value}`))) : null;
  return (
    <div className="flex flex-col">
      {caption && <p className="cap pb-1">{caption}</p>}
      {genome.map((band) => (
        <div key={band.family} className="flex h-6 items-center gap-2 border-b border-line last:border-b-0">
          <span className="flex w-32 shrink-0 items-center gap-1.5 truncate text-muted">
            <FamilyDot family={band.family} />
            {band.label}
          </span>
          <div className="flex min-w-0 flex-1 items-center gap-[3px] overflow-hidden">
            {band.markers.length === 0 && <span className="h-px w-full bg-line" />}
            {band.markers.map((marker, index) => (
              <Tick key={index} marker={marker} color={famVar(band.family)} matched={otherValues ? otherValues.has(`${marker.kind}\u0000${marker.value}`) : undefined} />
            ))}
          </div>
          <Mono className="w-6 shrink-0 text-right text-muted">{band.markers.length}</Mono>
        </div>
      ))}
      <p className="pt-1 text-xs text-faint">
        Wypełniony znacznik: marker wspólny z inną reklamą. Pusty: tylko w tej reklamie. Wysoki: rozstrzygający.
      </p>
    </div>
  );
}

// Widok prosty: najmocniejsze ślady wspólne z innymi reklamami, słowami. Rozstrzygające pierwsze, potem rzadsze.
export function KeyTraces({ genome, limit = 6 }: { genome: Genome; limit?: number }) {
  const shared = genome.flatMap((band) => band.markers.filter((marker) => marker.ad_count > 1).map((marker) => ({ marker, family: band.family })))
    .sort((a, b) => Number(b.marker.decisive) - Number(a.marker.decisive) || a.marker.ad_count - b.marker.ad_count);
  const seen = new Set<string>();
  const top = shared.filter(({ marker }) => !seen.has(marker.label) && !!seen.add(marker.label)).slice(0, limit);
  return (
    <section className="grid gap-2">
      <h2 className="text-lg font-semibold">Najważniejsze wspólne ślady</h2>
      <p className="text-muted">Te ślady ta reklama dzieli z innymi. Im rzadszy ślad, tym mocniej łączy reklamy.</p>
      {top.length ? <ul className="grid gap-2 md:grid-cols-2">{top.map(({ marker, family }) => (
        <li key={marker.kind + marker.value} className="min-w-0 rounded-md border border-line bg-panel p-2">
          <p className="flex items-center gap-1.5 font-medium"><FamilyDot family={family} />{marker.label}{marker.decisive && <Tag tone="accent">rozstrzyga</Tag>}</p>
          {marker.display_value && marker.display_value !== marker.value && <p className="truncate">{marker.display_value}</p>}
          <p className="text-sm text-muted">wspólny z {marker.ad_count - 1} {plural(marker.ad_count - 1, "inną reklamą", "innymi reklamami", "innymi reklamami")}</p>
        </li>
      ))}</ul> : <p className="text-muted">Ta reklama nie dzieli śladów z innymi reklamami.</p>}
    </section>
  );
}

// Chip markera: kolor rodziny, nazwa, wartość w mono, rzadkość.
export function MarkerChip({ marker, family }: { marker: Marker; family: AdDetail["genome"][number]["family"] }) {
  return (
    <span className="inline-flex h-5 max-w-full items-center gap-1.5 rounded-sm border border-line bg-raised px-1.5">
      <FamilyDot family={family} size={7} />
      <span className="shrink-0 text-muted">{marker.label}</span>
      <Mono className="truncate" title={markerValue(marker.value, marker.display_value)}>
        {markerValue(marker.value, marker.display_value)}
      </Mono>
      <Mono className="shrink-0 text-faint" title={`występuje w ${reklam(marker.ad_count)}`}>
        ×{marker.ad_count}
      </Mono>
    </span>
  );
}

function FaceObservation({ marker, videos }: { marker: Marker; videos: AdDetail["videos"] }) {
  const [size, setSize] = useState<{ width: number; height: number } | null>(null);
  const box = marker.detail?.box;
  const score = marker.detail?.score;
  const image = marker.detail?.artifact;
  const at = marker.detail?.at_s;
  const recording = videos.find(video => video.name === marker.detail?.file);
  const seconds = typeof at === "number" && Number.isFinite(at) && at >= 0 ? at : null;
  const [playing, setPlaying] = useState(false);
  const stamp = seconds === null ? "" : Math.floor(seconds / 60) + ":" + String(Math.floor(seconds % 60)).padStart(2, "0");
  const showBox = typeof image === "string" && /^[a-f0-9]{64}$/.test(image) && Array.isArray(box) && box.length === 4 && box.every(Number.isFinite) && box[2] > 0 && box[3] > 0;
  return <div className="whitespace-normal text-xs">
    {typeof score === "number" && <p>Podobieństwo modelu · {score.toLocaleString("pl-PL")}</p>}
    {seconds !== null && <div>
      <p>{typeof marker.detail.name === "string" && marker.detail.name} · w nagraniu {stamp}</p>
      {recording?.playable && recording.url ? <>
        <button type="button" aria-expanded={playing} className="text-accent underline" onClick={() => setPlaying(!playing)}>
          {playing ? "Zamknij odtwarzacz" : "Odtwórz od " + stamp}
        </button>
        {playing && <video controls autoPlay preload="metadata" className="max-h-64 w-full" aria-label={recording.name}
          src={API_URL + recording.url + "#t=" + seconds} />}
      </> : <p>Nagranie niedostępne do odtworzenia.</p>}
    </div>}
    {showBox && <details><summary>Pokaż twarz na zrzucie</summary>
      <span className="relative inline-block max-w-full overflow-hidden">
        {/* eslint-disable-next-line @next/next/no-img-element -- współrzędne detekcji dotyczą oryginalnego artefaktu */}
        <img src={artifactImageUrl(image)} loading="lazy" alt="Zrzut z zaznaczonym obszarem dopasowania"
          className="block h-auto max-w-full" onLoad={event => setSize({width: event.currentTarget.naturalWidth, height: event.currentTarget.naturalHeight})} />
        {size && <span aria-hidden className="absolute border-2 border-yellow-400" style={{
          left: box[0] / size.width * 100 + "%", top: box[1] / size.height * 100 + "%",
          width: box[2] / size.width * 100 + "%", height: box[3] / size.height * 100 + "%",
        }} />}
      </span></details>}
  </div>;
}

export function MarkerList({ genome, videos = [], initiallyOpen = false }: { genome: Genome; videos?: AdDetail["videos"]; initiallyOpen?: boolean }) {
  const [open, setOpen] = useState<Record<string, boolean>>({});
  return (
    <div className="flex flex-col">
      {genome
        .filter((band) => band.markers.length > 0)
        .map((band) => {
          const isOpen = open[band.family] ?? initiallyOpen;
          const markers = [...band.markers].sort((a, b) => Number(b.decisive) - Number(a.decisive) || b.ad_count - a.ad_count);
          return (
            <div key={band.family} className="border-b border-line last:border-b-0">
              <button type="button" onClick={() => setOpen({ ...open, [band.family]: !isOpen })} className="flex h-7 w-full items-center gap-1.5 px-2 text-left hover:bg-hover" aria-expanded={isOpen}>
                {isOpen ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                <FamilyDot family={band.family} />
                <span>{band.label}</span>
                <Mono className="text-muted">{band.markers.length}</Mono>
              </button>
              {isOpen && (
                <table className="dense max-md:block">
                  <tbody className="max-md:block">
                    {markers.map((marker, index) => (
                      <tr key={index} className="max-md:block max-md:border-b max-md:border-line max-md:px-3 max-md:py-1.5">
                        <td className="w-[34%] pl-7! text-muted max-md:block max-md:h-auto max-md:w-auto! max-md:max-w-none! max-md:border-0 max-md:p-0! max-md:whitespace-normal! max-md:break-all ">
                          {marker.label} {marker.decisive && <Tag tone="accent">rozstrzyga</Tag>}
                        </td>
                        <td className="max-w-0 font-mono text-[0.92rem] max-md:block max-md:h-auto max-md:w-auto! max-md:max-w-none! max-md:border-0 max-md:p-0! max-md:whitespace-normal! max-md:break-all " title={markerValue(marker.value, marker.display_value)}>
                          {markerValue(marker.value, marker.display_value)}
                          {marker.kind === "face_match" && <FaceObservation marker={marker} videos={videos} />}
                        </td>
                        <td className={cx("w-24 text-right font-mono text-[0.92rem] max-md:block max-md:h-auto max-md:w-auto! max-md:max-w-none! max-md:border-0 max-md:p-0! max-md:whitespace-normal! max-md:break-all max-md:text-left", marker.ad_count > 1 ? "text-fg" : "text-faint")} title="W ilu reklamach korpusu występuje ta wartość">
                          {reklam(marker.ad_count)}
                        </td>
                        <td className="w-7 max-md:block max-md:h-auto max-md:border-0 max-md:p-0! max-md:empty:hidden">
                          {marker.artifact && (
                            <a href={artifactDownloadUrl(marker.artifact)} title="Pobierz artefakt źródłowy (plik, nie otwiera się w przeglądarce)" className="text-muted hover:text-fg">
                              <Download size={12} />
                            </a>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          );
        })}
    </div>
  );
}
