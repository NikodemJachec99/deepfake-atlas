"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { EdgePanel, regroupMessage } from "@/components/edge-panel";
import { ErrorBox, Loading } from "@/components/ui";

export default function ReviewPage() {
  const params = useSearchParams();
  const requested = Number(params.get("page"));
  const page = Number.isSafeInteger(requested) && requested > 0 ? requested : 1;
  const requestedEdge = params.get("edge");
  const selected = requestedEdge === null ? null : Number(requestedEdge);
  const comparing = params.get("view") === "compare";
  const queue = useApi("review:" + page, () => api.review({ page }));

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
  const [message, setMessage] = useState("");
  const rows = queue.data?.results ?? [];
  const current = selected === null ? rows[0] : rows.find(row => row.id === selected);
  const missing = selected !== null && queue.data && !current;
  return <main className="grid min-h-0 min-w-0 flex-1 grid-cols-[minmax(0,1fr)] grid-rows-[auto_minmax(0,1fr)] gap-3 lg:grid-rows-1 overflow-hidden p-3 text-sm lg:grid-cols-[minmax(15rem,24%)_minmax(0,1fr)]">
    <nav aria-label="Widok stanowiska oceny" className="flex gap-2 lg:hidden">
      <button aria-pressed={!comparing} className="rounded px-3 aria-pressed:bg-accent-soft" onClick={() => navigate(page, selected, false)}>Kolejka</button>
      <button disabled={!current} aria-pressed={comparing} className="rounded px-3 aria-pressed:bg-accent-soft" onClick={() => navigate(page, current?.id ?? null, true)}>Porównanie</button>
    </nav>
    <aside className={`min-h-0 min-w-0 overflow-auto rounded-lg border border-line bg-panel p-3 lg:block ${comparing ? "hidden" : "block"}`}>
      <h1 className="mb-3 text-xl font-semibold">Do oceny {queue.data && <span className="text-muted">({queue.data.count})</span>}</h1>
      {queue.loading ? <Loading/> : queue.error ? <ErrorBox message={queue.error} onRetry={queue.reload}/> : <>
        {rows.length === 0 && <p>Brak par do oceny.</p>}
        {rows.map(row => <button key={row.id} aria-pressed={row.id === current?.id} onClick={() => navigate(page, row.id, true)}
          className="grid w-full gap-1 border-b border-line px-2 py-3 text-left aria-pressed:bg-accent-soft">
          <strong className="line-clamp-2">{row.ad_a.domain || row.ad_a.title} ↔ {row.ad_b.domain || row.ad_b.title}</strong><span className="text-xs text-muted">{row.reason_label}</span></button>)}
        <nav className="mt-3 flex justify-between"><button disabled={page === 1} onClick={() => navigate(page-1, null, false)}>Poprzednia</button><span>{page}</span><button disabled={!queue.data?.next} onClick={() => navigate(page+1, null, false)}>Następna</button></nav>
      </>}
    </aside>
    <section className={`min-h-0 min-w-0 flex-col overflow-hidden rounded-lg border border-line bg-panel lg:flex ${comparing ? "flex" : "hidden"}`}>
      {message && <p role="status" className="border-b border-line p-3">{message}</p>}
      {missing && <div role="status" className="grid justify-items-start gap-3 p-4">
        <h2 className="font-semibold">Wskazanej pary nie ma na tej stronie kolejki.</h2>
        {Number.isSafeInteger(selected) && selected > 0 && <Link className="text-accent underline" href={`/investigation?scope=all&edge=${selected}`}>Sprawdź krawędź #{selected} w śledztwie</Link>}
        <button className="text-accent underline" onClick={() => navigate(page, null, false)}>Wybierz parę z kolejki</button>
      </div>}
      {!current && comparing && !missing && (queue.loading ? <Loading/> : queue.error ? <ErrorBox message={queue.error} onRetry={queue.reload}/> : <button onClick={() => navigate(page, null, false)}>Wróć do kolejki</button>)}
      {current && <EdgePanel key={current.id} edgeId={current.id} review={current} onVerdict={saved => {
        setMessage(regroupMessage(saved.regroup));
        const index = rows.findIndex(row => row.id === saved.id);
        const next = (rows[index+1] ?? rows.find(row => row.id !== saved.id))?.id ?? null;
        if (rows.length === 1 && page > 1) navigate(page-1, null, true, true);
        else {
          navigate(page, next, comparing, true);
          queue.reload();
        }
      }}/>}
    </section>
  </main>;
}
