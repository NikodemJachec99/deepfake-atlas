"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { EdgePanel, regroupMessage } from "@/components/edge-panel";
import { ErrorBox, Loading } from "@/components/ui";

export default function ReviewPage() {
  const [page, setPage] = useState(1);
  const queue = useApi("review:" + page, () => api.review({ page }));
  const [selected, setSelected] = useState<number | null>(null);
  const [message, setMessage] = useState("");
  const rows = queue.data?.results ?? [];
  const current = rows.find(row => row.id === selected) ?? rows[0];
  return <main className="grid min-h-0 flex-1 gap-3 overflow-auto p-3 text-sm lg:grid-cols-[minmax(15rem,24%)_minmax(0,1fr)]">
    <aside className="min-h-0 rounded-lg border border-line bg-panel p-3 lg:overflow-auto">
      <h1 className="mb-3 text-xl font-semibold">Do oceny {queue.data && <span className="text-muted">({queue.data.count})</span>}</h1>
      {queue.loading ? <Loading/> : queue.error ? <ErrorBox message={queue.error} onRetry={queue.reload}/> : <>
        {rows.length === 0 && <p>Brak par do oceny.</p>}
        {rows.map(row => <button key={row.id} aria-pressed={row.id === current?.id} onClick={() => setSelected(row.id)}
          className="grid w-full gap-1 border-b border-line px-2 py-3 text-left aria-pressed:bg-accent-soft">
          <strong className="line-clamp-2">{row.ad_a.domain || row.ad_a.title} ↔ {row.ad_b.domain || row.ad_b.title}</strong><span className="text-xs text-muted">{row.reason_label}</span></button>)}
        <nav className="mt-3 flex justify-between"><button disabled={page === 1} onClick={() => setPage(page-1)}>Poprzednia</button><span>{page}</span><button disabled={!queue.data?.next} onClick={() => setPage(page+1)}>Następna</button></nav>
      </>}
    </aside>
    <section className="flex min-h-0 flex-col rounded-lg border border-line bg-panel">
      {message && <p role="status" className="border-b border-line p-3">{message}</p>}
      {current && <EdgePanel key={current.id} edgeId={current.id} review={current} onVerdict={saved => {
        setMessage(regroupMessage(saved.regroup));
        const index = rows.findIndex(row => row.id === saved.id);
        setSelected((rows[index+1] ?? rows.find(row => row.id !== saved.id))?.id ?? null);
        if (rows.length === 1 && page > 1) setPage(page-1);
        else queue.reload();
      }}/>}
    </section>
  </main>;
}
