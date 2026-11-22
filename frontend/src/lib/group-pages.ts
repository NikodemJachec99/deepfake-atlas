import { api, API_URL } from "./api";

export async function allGroups(kind: "operators" | "campaigns", source?: string) {
  const first = await api[kind](source);
  const results = [...first.results];
  let next = first.next;
  while (next) {
    const url = new URL(API_URL + "/api/" + kind);
    url.search = new URL(next, url).search;
    const response = await fetch(url);
    if (!response.ok) throw new Error(`API ${response.status}: pobranie kolejnej strony grup`);
    const page: typeof first = await response.json();
    results.push(...page.results);
    next = page.next;
  }
  return { ...first, results, next: null };
}
