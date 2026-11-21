// Formatowanie wartości z API. Nic tu nie jest liczone poza zapisem liczb i dat.

import type { AdSummary, Family, Relation, Verdict } from "./api";

export const FAMILIES: Family[] = ["infra", "track", "tmpl", "crea", "narr", "pers", "beh"];
export const RELATIONS: Relation[] = ["same_campaign", "same_operator", "similar"];

export const famVar = (family: Family | null | undefined) => (family ? `var(--fam-${family})` : "var(--faint)");

export const RELATION_HINT: Record<Relation, string> = {
  same_campaign: "to samo źródło i ta sama opowieść",
  same_operator: "to samo zaplecze, inna opowieść",
  similar: "podobna koncepcja, brak dowodu wspólnego zaplecza",
};

export const VERDICT_LABELS: Record<Exclude<Verdict, "">, string> = {
  confirmed: "Potwierdzone",
  unsure: "Niepewne",
  rejected: "Odrzucone",
};

export const SOURCE_LABELS: Record<string, string> = {
  manual: "Ręcznie",
  meta: "Meta",
  google: "Google",
  tiktok: "TikTok",
  microsoft: "Microsoft",
  native: "Sieć natywna",
  capture: "Przechwycenie",
};

export function hostOf(url: string): string {
  if (!url) return "";
  try {
    return new URL(url).hostname;
  } catch {
    return url.split("/")[2] ?? url;
  }
}

// "K-0033" -> 33. Identyfikator liczbowy grupy jest zaszyty w kluczu.
export function groupId(key: string | null | undefined): number | null {
  if (!key) return null;
  const n = Number.parseInt(key.split("-")[1] ?? "", 10);
  return Number.isFinite(n) ? n : null;
}

export const num = (value: number, digits = 2) => value.toFixed(digits).replace(".", ",");
export const prob = (value: number) => num(value, 2);
export const bits = (value: number) => num(value, 1);

const pad = (n: number) => String(n).padStart(2, "0");

export function dateTime(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function clock(iso: string): string {
  const d = new Date(iso);
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}.${String(d.getMilliseconds()).padStart(3, "0")}`;
}

export const day = (iso: string | null | undefined) => dateTime(iso).slice(0, 10);

export function duration(ms: number): string {
  if (ms < 1000) return `${Math.max(0, Math.round(ms))} ms`;
  return `${num(ms / 1000, 1)} s`;
}

export function plural(n: number, one: string, few: string, many: string): string {
  if (n === 1) return one;
  const d = n % 10;
  const h = n % 100;
  return d >= 2 && d <= 4 && !(h >= 12 && h <= 14) ? few : many;
}

export const adTitle = (ad: Pick<AdSummary, "id" | "title" | "landing_url">) => ad.title || hostOf(ad.landing_url) || `Reklama ${ad.id}`;

// Paleta grup (operator, kampania). Osobna od rodzin markerów: rodziny kolorują krawędzie, grupy węzły.
const GROUP_DARK = ["#7aa6f0", "#f0a35e", "#6fcf97", "#e88fb4", "#c9c35a", "#a48cf0", "#5fc8d8", "#e2816f", "#9fb86a", "#c79be0"];
const GROUP_LIGHT = ["#2f5fb8", "#b0621a", "#2a8552", "#b04a78", "#807a14", "#6a4fc2", "#177d8c", "#b34a38", "#5f7a26", "#8a55ad"];

export function groupColor(key: string | null | undefined, theme: "dark" | "light"): string {
  const id = groupId(key);
  if (id === null) return theme === "dark" ? "#6b7585" : "#8a94a3";
  const palette = theme === "dark" ? GROUP_DARK : GROUP_LIGHT;
  return palette[(id - 1 + palette.length * 1000) % palette.length];
}

export function errorText(reason: unknown): string {
  const text = reason instanceof Error ? reason.message : String(reason);
  if (/Failed to fetch|NetworkError|Load failed/i.test(text)) return "Brak połączenia z API. Sprawdź, czy backend działa i czy adres w NEXT_PUBLIC_API_URL jest poprawny.";
  return text;
}

// Python zapisuje UTC z offsetem i sześcioma cyframi ułamka, jeśli ułamek jest niezerowy.
// Date potrafi przeliczyć offset, lecz zachowuje tylko milisekundy.
export function utcEdgeVersion(version: string): string {
  const parts = /^(.*T\d{2}:\d{2}:\d{2})(?:\.(\d{1,6}))?(Z|[+-]\d{2}:\d{2})$/.exec(version);
  if (!parts) return version;
  const instant = new Date(parts[1] + parts[3]);
  if (!Number.isFinite(instant.getTime())) return version;
  const fraction = (parts[2] ?? "").padEnd(6, "0");
  return instant.toISOString().slice(0, 19) + (fraction === "000000" ? "" : "." + fraction) + "+00:00";
}
