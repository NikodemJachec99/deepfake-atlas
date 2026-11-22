// Prosty język dla stanowiska oceny: hipoteza jednym zdaniem i siła śladu słowem.
// Wszystko liczone z pól API (relacja, wynik modelu, wagi i rzadkość śladów), bez dopisywania faktów.
import type { Relation } from "./api";

type Trace = { label: string; weight_bits: number; decisive?: boolean };

const LEAD: Record<Relation, string> = {
  same_campaign: "Prawdopodobnie ta sama kampania",
  same_operator: "Prawdopodobnie ten sam operator",
  similar: "Podobne reklamy, ale bez dowodu wspólnego zaplecza",
};

/** Dwie najmocniejsze różne nazwy śladów, malejąco po wadze. */
export function topLabels(traces: Trace[], count = 2): string[] {
  const labels: string[] = [];
  for (const trace of [...traces].sort((a, b) => b.weight_bits - a.weight_bits)) {
    if (trace.weight_bits <= 0 || labels.includes(trace.label)) continue;
    labels.push(trace.label);
    if (labels.length === count) break;
  }
  return labels;
}

const quoted = (labels: string[]) => labels.map(label => `„${label}”`).join(" i ");

/** Hipoteza modelu po ludzku, np. "Prawdopodobnie ten sam operator. Obie reklamy mają wspólne ślady: „Meta Pixel” i …". */
export function hypothesisSentence(relation: Relation, traces: Trace[], options: { duplicate?: boolean; crossDomain?: boolean } = {}): string {
  const labels = topLabels(traces);
  const parts = [LEAD[relation] + "."];
  if (options.duplicate) parts.push("To ta sama strona przechwycona ponownie.");
  else if (labels.length) {
    const decisive = traces.some(trace => trace.decisive && labels.includes(trace.label));
    const noun = labels.length === 1 ? (decisive ? "wspólny rzadki ślad" : "wspólny ślad") : (decisive ? "wspólne rzadkie ślady" : "wspólne ślady");
    parts.push(`Obie reklamy mają ${noun}: ${quoted(labels)}.`);
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
