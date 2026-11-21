"use client";

import Link from "next/link";
import { useState } from "react";
import { API_URL, api, type Alert, type Page } from "@/lib/api";
import { dateTime, errorText } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import { ErrorBox, Loading } from "@/components/ui";

export default function Alerts() {
  const [unseen, setUnseen] = useState(true);
  const [page, setPage] = useState(1);
  const [saving, setSaving] = useState<number | null>(null);
  const [error, setError] = useState("");
  const list = useApi(`alerts:${unseen}:${page}`, async () => {
    if (page === 1) return api.alerts(unseen);
    const query = new URLSearchParams({ page: String(page) });
    if (unseen) query.set("unseen", "1");
    const response = await fetch(API_URL + "/api/alerts?" + query);
    if (!response.ok) throw new Error(`Odczyt alertów: HTTP ${response.status}`);
    return await response.json() as Page<Alert>;
  });

  async function markSeen(id: number) {
    setSaving(id);
    setError("");
    try {
      await api.markAlertSeen(id);
      if (unseen && page > 1 && list.data?.results.length === 1) setPage(page - 1);
      else list.reload();
      window.dispatchEvent(new Event("atlas-alerts-updated"));
    } catch (reason) {
      setError(errorText(reason));
    } finally {
      setSaving(null);
    }
  }

  return <main className="atlas-page">
    <h1 className="atlas-title">Alerty</h1>
    <label><input type="checkbox" checked={unseen} disabled={saving !== null}
      onChange={event => { setUnseen(event.target.checked); setPage(1); setError(""); }} /> Tylko nieprzejrzane</label>
    {error && <p role="alert" className="text-rejected">{error}</p>}
    {list.loading ? <Loading /> : list.error ? <ErrorBox message={list.error} onRetry={list.reload} /> :
      <><ul>{list.data?.results.map(item => <li key={item.id} className="grid gap-2 border-b border-line py-3">
        <h2 className="text-lg font-semibold">{item.kind_label}</h2>
        <p>{item.description}</p>
        <p className="flex flex-wrap gap-3 text-accent underline">
          {item.ad != null && <Link href={`/ads/${item.ad}`}>Reklama #{item.ad} {item.ad_title}</Link>}
          {item.hunt_candidate != null && <Link href={`/hunt#kandydat-${item.hunt_candidate}`}>{item.domain || "Kandydat domenowy"}</Link>}
          {item.campaign_id != null && <Link href={`/campaigns/${item.campaign_id}`}>Kampania {item.campaign ?? item.campaign_id}</Link>}
          {item.operator_id != null && <Link href={`/operators/${item.operator_id}`}>Operator {item.operator ?? item.operator_id}</Link>}
        </p>
        <p className="text-muted">{dateTime(item.created_at)} · {item.seen ? "Przejrzany" : "Nowy"}</p>
        {!item.seen && <button className="justify-self-start text-accent underline" disabled={saving !== null}
          onClick={() => void markSeen(item.id)}>Oznacz jako przejrzany</button>}
      </li>)}</ul>
      {!list.data?.results.length && <p>{unseen ? "Brak nieprzejrzanych alertów." : "Brak alertów."}</p>}
      {(page > 1 || list.data?.next) && <nav aria-label="Strony alertów" className="flex gap-3">
        <button disabled={page <= 1 || saving !== null} onClick={() => setPage(page - 1)}>Poprzednia</button>
        <span>Strona {page}</span>
        <button disabled={!list.data?.next || saving !== null} onClick={() => setPage(page + 1)}>Następna</button>
      </nav>}</>}
  </main>;
}
