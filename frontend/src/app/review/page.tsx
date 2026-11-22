"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { useApi, useStored } from "@/lib/hooks";
import type { ReviewReason } from "@/lib/api";

// Kolejka zwraca 50 par na stronę (docs/api.md, "Kolejka Do oceny").
const PAGE_SIZE = 50;
// Powody, przy których coś się zmieniło albo brakuje podstaw: wyróżniamy je kolorem.
const URGENT = new Set<ReviewReason>(["challenged", "changed_after_decision", "unbacked"]);
import { EdgePanel, regroupMessage } from "@/components/edge-panel";
import { ErrorBox, Loading } from "@/components/ui";
import { plural, VERDICT_LABELS } from "@/lib/format";
import { useExpert } from "@/lib/expert";
import { CircleCheck, Lightbulb, X } from "lucide-react";

  function navigate(targetPage: number, edge: number | null, compare: boolean, replace = false) {
    const url = new URL(window.location.href);
    if (targetPage > 1) url.searchParams.set("page", String(targetPage));
    else url.searchParams.delete("page");
    if (edge !== null) url.searchParams.set("edge", String(edge));
    else url.searchParams.delete("edge");
    if (compare) url.searchParams.set("view", "compare");
    else url.searchParams.delete("view");
    if (url.href === window.location.href) return;
    if (replace) window.history.replaceState(null, "", url);
    else window.history.pushState(null, "", url);
  }

export default function ReviewPage() {
  const params = useSearchParams();
  const requested = Number(params.get("page"));
  const page = Number.isSafeInteger(requested) && requested > 0 ? requested : 1;
  const requestedEdge = params.get("edge");
  const selected = requestedEdge === null ? null : Number(requestedEdge);
  const comparing = params.get("view") === "compare";
  const { expert } = useExpert();
  const queue = useApi("review:" + page, () => api.review({ page }));

  const outOfRange = page > 1 && queue.status === 404;
  const first = useApi(outOfRange ? "review-bounds:" + page : null, () => api.review({ page: 1 }));
  useEffect(() => {
    if (!outOfRange || !first.data) return;
    const last = Math.max(1, Math.ceil(first.data.count / Math.max(1, first.data.results.length)));
    if (last < page) navigate(last, selected, comparing, true);
  }, [outOfRange, first.data, page, selected, comparing]);
  const [message, setMessage] = useState("");
  const rows = queue.data?.results ?? [];
  const current = selected === null ? rows[0] : rows.find(row => row.id === selected);
  const missing = selected !== null && queue.data && !current;
  const queuePanel = useRef<HTMLElement>(null);
  // Po zapisie kolejka przechodzi do następnej pary; jej wiersz ma być widoczny bez szukania.
  useEffect(() => {
    queuePanel.current?.querySelector<HTMLElement>('[aria-pressed="true"]')?.scrollIntoView({ block: "nearest" });
  }, [current?.id]);
  const [hint, setHint] = useStored("scamdna.review-hint", "1");
  const [hintClosed, setHintClosed] = useState(false); // gdy przeglądarka nie zapisuje localStorage
  const pages = queue.data ? Math.max(page, Math.ceil(queue.data.count / PAGE_SIZE)) : 1;
  return <main className="grid min-h-0 min-w-0 flex-1 grid-cols-[minmax(0,1fr)] grid-rows-[auto_minmax(0,1fr)] gap-3 lg:grid-rows-1 overflow-hidden p-3 text-sm lg:grid-cols-[minmax(15rem,24%)_minmax(0,1fr)]">
    <nav aria-label="Widok stanowiska oceny" className="flex gap-2 lg:hidden">
      <button aria-pressed={!comparing} className="min-h-9 rounded-md px-3 aria-pressed:bg-accent-soft" onClick={() => navigate(page, selected, false)}>Kolejka</button>
      <button disabled={!current} aria-pressed={comparing} className="min-h-9 rounded-md px-3 aria-pressed:bg-accent-soft" onClick={() => navigate(page, current?.id ?? null, true)}>Porównanie</button>
    </nav>
    <aside ref={queuePanel} className={`min-h-0 min-w-0 overflow-auto rounded-lg border border-line bg-panel p-3 lg:block ${comparing ? "hidden" : "block"}`}>
      <h1 className="mb-3 flex items-baseline gap-2 px-1 text-xl font-semibold">Do oceny {queue.data && <span className="rounded-full bg-accent-soft px-2 py-0.5 text-sm font-medium text-accent">{queue.data.count} {plural(queue.data.count, "para", "pary", "par")}</span>}</h1>
      {hint === "1" && !hintClosed && <div className="mb-3 flex items-start gap-2 rounded-lg border border-line bg-bg p-3">
        <Lightbulb size={16} aria-hidden className="mt-0.5 shrink-0 text-accent" />
        <p className="min-w-0 flex-1">Wybierz parę z listy, sprawdź przesłanki i materiały, a potem zdecyduj: potwierdź, oznacz do wyjaśnienia albo odrzuć.</p>
        <button type="button" aria-label="Zamknij wskazówkę" onClick={() => { setHintClosed(true); setHint("0"); }} className="shrink-0 text-muted hover:text-fg"><X size={16} aria-hidden /></button>
      </div>}
      {queue.loading || first.loading ? <Loading/> : first.error ? <ErrorBox message={first.error} onRetry={first.reload}/> : queue.error ? <ErrorBox message={queue.error} onRetry={queue.reload}/> : <>
        {rows.length === 0 && <p className="p-2 text-muted">Brak par do oceny. Wszystkie pary w kolejce mają już decyzję.</p>}
        <ul className="grid gap-1">{rows.map(row => <li key={row.id}><button aria-pressed={row.id === current?.id} onClick={() => navigate(page, row.id, true)}
          className="grid w-full gap-1.5 rounded-md border border-transparent px-3 py-2.5 text-left transition-colors hover:bg-hover aria-pressed:border-accent aria-pressed:bg-accent-soft">
          <span className="flex items-baseline justify-between gap-2">
            <span className="min-w-0 font-medium break-words">{row.ad_a.domain && row.ad_a.domain === row.ad_b.domain
              ? `${row.ad_a.domain} · ta sama domena`
              : `${row.ad_a.domain || "Brak domeny"} ↔ ${row.ad_b.domain || "Brak domeny"}`}</span>
            {expert && <span className="shrink-0 font-mono text-xs text-muted">#{row.ad_a.id} ↔ #{row.ad_b.id}</span>}
          </span>
          {(!row.ad_a.domain || !row.ad_b.domain) && <span className="line-clamp-2 text-muted">{[!row.ad_a.domain && row.ad_a.title, !row.ad_b.domain && row.ad_b.title].filter(Boolean).join(" ↔ ")}</span>}
          <span className={`justify-self-start rounded-full border px-2 py-0.5 text-xs ${URGENT.has(row.reason) ? "border-unsure text-unsure" : "border-line-strong text-muted"}`}>{row.reason_label}</span></button></li>)}</ul>
        {pages > 1 && <nav aria-label="Strony kolejki" className="mt-3 flex items-center justify-between gap-2 px-1">
          <button className="min-h-9 rounded-md border border-line-strong px-3 hover:bg-hover disabled:opacity-40" disabled={page === 1} onClick={() => navigate(page-1, null, false)}>Poprzednia</button>
          <span className="text-muted">Strona {page} z {pages}</span>
          <button className="min-h-9 rounded-md border border-line-strong px-3 hover:bg-hover disabled:opacity-40" disabled={!queue.data?.next} onClick={() => navigate(page+1, null, false)}>Następna</button>
        </nav>}
      </>}
    </aside>
    <section className={`min-h-0 min-w-0 flex-col overflow-hidden rounded-lg border border-line bg-panel lg:flex ${comparing ? "flex" : "hidden"}`}>
      {message && <div role="status" className="flex items-start gap-2 border-b border-line border-l-4 border-l-confirmed bg-confirmed/10 p-3">
        <CircleCheck size={18} aria-hidden className="mt-0.5 shrink-0 text-confirmed" />
        <p className="min-w-0 flex-1">{message}</p>
        <button type="button" aria-label="Zamknij komunikat" onClick={() => setMessage("")} className="shrink-0 text-muted hover:text-fg"><X size={16} aria-hidden /></button>
      </div>}
      {missing && <div role="status" className="grid justify-items-start gap-3 p-4">
        <h2 className="font-semibold">Wskazanej pary nie ma na tej stronie kolejki.</h2>
        {Number.isSafeInteger(selected) && selected > 0 && <Link className="text-accent underline" href={`/investigation?scope=all&edge=${selected}`}>{expert ? `Sprawdź krawędź #${selected} w śledztwie` : "Zobacz tę parę w śledztwie"}</Link>}
        <button className="text-accent underline" onClick={() => navigate(page, null, false)}>Wybierz parę z kolejki</button>
      </div>}
      {!current && comparing && !missing && (queue.loading ? <Loading/> : queue.error ? <ErrorBox message={queue.error} onRetry={queue.reload}/> : <button onClick={() => navigate(page, null, false)}>Wróć do kolejki</button>)}
      {current && <EdgePanel key={current.id} edgeId={current.id} review={current} onVerdict={saved => {
        const index = rows.findIndex(row => row.id === saved.id);
        const next = (rows[index+1] ?? rows.find(row => row.id !== saved.id))?.id ?? null;
        const verdict = saved.verdict ? VERDICT_LABELS[saved.verdict].toLowerCase() : "";
        setMessage(regroupMessage(saved.regroup, expert
          ? `Zapisano ocenę pary #${saved.ad_a} ↔ #${saved.ad_b}${verdict ? ": " + verdict : ""}.`
          : `Ocena zapisana${verdict ? ": " + verdict : ""}. ${next !== null || page > 1 ? "Otwarto następną parę." : "To była ostatnia para na tej stronie."}`));
        if (rows.length === 1 && page > 1) navigate(page-1, null, true, true);
        else {
          navigate(page, next, comparing, true);
          queue.reload();
        }
      }}/>}
    </section>
  </main>;
}
