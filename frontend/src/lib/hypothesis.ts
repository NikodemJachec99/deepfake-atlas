// Prosty język dla stanowiska oceny: hipoteza jednym zdaniem i siła śladu słowem.
// Wszystko liczone z pól API (relacja, wynik modelu, wagi i rzadkość śladów), bez dopisywania faktów.
import type { Relation } from "./api";

type Trace = { label: string; weight_bits: number; decisive?: boolean; df?: number; corpus_n?: number };

const LEAD: Record<Relation, string> = {
  same_campaign: "Prawdopodobnie ta sama kampania",
  same_operator: "Prawdopodobnie ten sam operator",
  similar: "Podobne reklamy, ale bez dowodu wspólnego zaplecza",
};
const CAUTIOUS_LEAD: Record<Relation, string> = {
  same_campaign: "Możliwe, że to ta sama kampania",
  same_operator: "Możliwe, że to ten sam operator",
  similar: LEAD.similar,
};

// Ślad obecny w co najmniej co dziesiątym źródle korpusu słabo wyróżnia parę, więc nie trafia do zdania.
const isCommon = (trace: Trace) => !!trace.df && !!trace.corpus_n && trace.df / trace.corpus_n >= 0.1;

/** Dwie najmocniejsze różne nazwy śladów, malejąco po wadze, bez śladów częstych w korpusie. */
export function topLabels(traces: Trace[], count = 2): string[] {
  const labels: string[] = [];
  for (const trace of [...traces].sort((a, b) => b.weight_bits - a.weight_bits)) {
    if (trace.weight_bits <= 0 || isCommon(trace) || labels.includes(trace.label)) continue;
    labels.push(trace.label);
    if (labels.length === count) break;
  }
  return labels;
}

const q = (label: string) => `„${label}”`;

/** Hipoteza modelu po ludzku, np. "Prawdopodobnie ten sam operator. Obie reklamy mają wspólne rzadkie ślady: „Meta Pixel” i …". */
export function hypothesisSentence(relation: Relation, traces: Trace[], options: { duplicate?: boolean; crossDomain?: boolean; cautious?: boolean } = {}): string {
  const labels = topLabels(traces);
  const parts = [(options.cautious ? CAUTIOUS_LEAD : LEAD)[relation] + "."];
  if (options.duplicate) parts.push("To ta sama strona przechwycona ponownie.");
  else if (labels.length) {
    const decisive = labels.map(label => traces.some(trace => trace.label === label && trace.decisive));
    if (labels.length === 1) parts.push(`Obie reklamy mają ${decisive[0] ? "wspólny rzadki ślad" : "wspólny ślad"}: ${q(labels[0])}.`);
    else if (decisive.every(Boolean)) parts.push(`Obie reklamy mają wspólne rzadkie ślady: ${q(labels[0])} i ${q(labels[1])}.`);
    else if (decisive[0]) parts.push(`Obie reklamy mają wspólny rzadki ślad ${q(labels[0])} oraz ślad ${q(labels[1])}.`);
    else parts.push(`Obie reklamy mają wspólne ślady: ${q(labels[0])} i ${q(labels[1])}.`);
  }
  if (options.crossDomain && !options.duplicate && relation !== "similar") parts.push("Prowadzą do różnych domen.");
  return parts.join(" ");
}

export type Strength = "decisive" | "strong" | "medium" | "weak";

/** Siła pojedynczego śladu. Progi na wadze po zniżce za korelację w rodzinie. */
export function traceStrength(trace: Trace): Strength {
  if (trace.decisive) return "decisive";
  if (trace.weight_bits >= 8) return "strong";
  if (trace.weight_bits >= 3) return "medium";
  return "weak";
}

export const STRENGTH_LABELS: Record<Strength, string> = {
  decisive: "Rozstrzygający ślad",
  strong: "Mocny ślad",
  medium: "Średni ślad",
  weak: "Słaby ślad",
};

// Rodziny motywu (treść, osoby i marki) nie wskazują zaplecza, więc ich nie kwestionujemy jako przesłanki.
const MOTIF_FAMILIES = new Set(["narr", "pers"]);

/** Ślad twardy: jedna konkretna wartość techniczna, która coś wnosi do wyniku. Tylko taki ma sens kwestionować. */
export function isHardTrace(trace: Trace & { df: number; family: string }): boolean {
  return trace.df > 0 && trace.weight_bits > 0 && (trace.decisive || !MOTIF_FAMILIES.has(trace.family));
}

/** Rzadkość słowem zamiast "w 5 z 92 źródeł". */
export function rarityWords(df: number, corpus: number): string {
  if (df <= 0) return "porównanie przez podobieństwo";
  if (df <= 2) return "występuje tylko w tej parze źródeł";
  if (corpus > 0 && df / corpus >= 0.2) return "częsty w korpusie, słabo odróżnia operatorów";
  if (df <= 5) return "rzadki w korpusie";
  return "spotykany w kilku miejscach korpusu";
}

/** Ogólna siła dowodów pary. */
export function overallStrength(probability: number, decisive: boolean): { label: string; tone: "confirmed" | "unsure" | "neutral" } {
  if (decisive) return { label: "Jest ślad rozstrzygający", tone: "confirmed" };
  if (probability >= 0.9) return { label: "Silne dowody", tone: "confirmed" };
  if (probability >= 0.5) return { label: "Dowody na granicy", tone: "unsure" };
  return { label: "Słabe dowody", tone: "neutral" };
}

/** Ograniczenie z API w spokojniejszym brzmieniu; liczby reklam zostają, bo to fakt z API. */
export function plainLimitation(text: string): string {
  const shared = text.match(/^ślad (.+) współdzielony przez (\d+) reklam$/);
  if (shared) return `Ślad ${shared[1]} dzieli ${shared[2]} reklam, więc sam słabo odróżnia operatorów.`;
  const sentence = text.charAt(0).toUpperCase() + text.slice(1);
  return /[.!?]$/.test(sentence) ? sentence : sentence + ".";
}
