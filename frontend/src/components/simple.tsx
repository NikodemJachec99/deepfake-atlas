"use client";

// Pomocniki widoku prostego: w trybie prostym szczegóły dla specjalisty są zwinięte,
// w trybie eksperckim widać je od razu, tak jak dotąd.
import type { CoreMarker } from "@/lib/api";
import { useExpert } from "@/lib/expert";

/** W trybie prostym zwija treść pod nagłówkiem `title`; w eksperckim pokazuje ją bez zmian. */
export function Fold({ title, children, open = false }: { title: React.ReactNode; children: React.ReactNode; open?: boolean }) {
  const { expert } = useExpert();
  if (expert) return <>{children}</>;
  return <details open={open} className="group min-w-0">
    <summary className="flex cursor-pointer list-none items-center gap-2 font-medium text-accent [&::-webkit-details-marker]:hidden">
      <span aria-hidden className="inline-block transition-transform group-open:rotate-90">›</span>{title}
    </summary>
    <div className="mt-3 grid min-w-0 gap-3">{children}</div>
  </details>;
}

/** Sekcja karty: w trybie prostym zwinięta pod tytułem, w eksperckim otwarta z nagłówkiem jak dotąd. */
export function FoldSection({ title, children, open = false }: { title: React.ReactNode; children: React.ReactNode; open?: boolean }) {
  const { expert } = useExpert();
  if (expert) return <section><h2>{title}</h2>{children}</section>;
  return <section><details open={open} className="group min-w-0">
    <summary className="flex cursor-pointer list-none items-center gap-2 [&::-webkit-details-marker]:hidden">
      <span aria-hidden className="inline-block text-muted transition-transform group-open:rotate-90">›</span>
      <h2 className="text-[1.05rem] font-semibold">{title}</h2>
    </summary>
    <div className="mt-3 grid min-w-0 gap-3">{children}</div>
  </details></section>;
}

/** Jedno zdanie o śladzie wspólnym dla grupy: ile reklam grupy go ma i czy pojawia się poza nią. */
export function markerSentence(marker: Pick<CoreMarker, "in_group" | "ad_count">, size: number) {
  const share = marker.in_group >= size ? `wspólny dla wszystkich ${size} reklam` : `wspólny dla ${marker.in_group} z ${size} reklam`;
  const outside = marker.ad_count - marker.in_group;
  const rarity = outside <= 0 ? "poza tą grupą nie występuje" : `poza grupą ${outside < 10 ? "tylko " : ""}w ${outside} ${outside === 1 ? "reklamie" : "reklamach"}`;
  return `${share}, ${rarity}`;
}

/** Okres obserwacji reklam jako „od X do Y” (same dni). */
export function period(ads: { first_seen: string | null; last_seen: string | null }[]): string | null {
  const days = ads.flatMap(ad => [ad.first_seen, ad.last_seen]).filter((value): value is string => !!value).map(value => value.slice(0, 10)).sort();
  if (!days.length) return null;
  const [first, last] = [days[0], days[days.length - 1]];
  return first === last ? first : `${first} do ${last}`;
}
