"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/api";
import { dateTime, errorText } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import { ErrorBox, Loading } from "@/components/ui";

export default function Alerts() {
  const router = useRouter();
  const params = useSearchParams();
  const unseen = params.get("unseen") !== "0";
  const requested = Number(params.get("page"));
  const page = Number.isSafeInteger(requested) && requested > 0 ? requested : 1;
  function listUrl(onlyUnseen: boolean, target: number) {
    const next = new URLSearchParams(params.toString());
    if (onlyUnseen) next.delete("unseen");
    else next.set("unseen", "0");
    if (target > 1) next.set("page", String(target));
    else next.delete("page");
    return next.size ? `/alerts?${next}` : "/alerts";
  }
  function navigate(onlyUnseen: boolean, target: number, replace = false) {
    const href = listUrl(onlyUnseen, target);
    if (replace) router.replace(href);
    else router.push(href);
  }
  const [saving, setSaving] = useState<number | null>(null);
  const [error, setError] = useState("");
  const list = useApi(`alerts:${unseen}:${page}`, () => api.alerts(unseen, page));

  async function markSeen(id: number) {
    setSaving(id);
    setError("");
    try {
      await api.markAlertSeen(id);
      if (unseen && page > 1 && list.data?.results.length === 1) navigate(unseen, page - 1, true);
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
      onChange={event => { navigate(event.target.checked, 1); setError(""); }} /> Tylko nieprzejrzane</label>
    {error && <p role="alert" className="text-rejected">{error}</p>}
    {list.loading ? <Loading /> : list.error ? <ErrorBox message={list.error} onRetry={list.reload}
      missing={page > 1 && list.status === 404 ? {
        description: "Ta strona alertów jest niedostępna.",
        href: listUrl(unseen, 1),
        link: "Otwórz pierwszą stronę alertów",
      } : undefined}/> :
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
      {!list.data?.results.length && <div className="grid justify-items-start gap-2"><p>{unseen ? "Brak nieprzejrzanych alertów." : "Brak alertów w korpusie."}</p>
        {unseen ? <button className="text-accent underline" onClick={() => navigate(false, 1)}>Pokaż wszystkie alerty</button> : <button className="text-accent underline" onClick={list.reload}>Odśwież alerty</button>}</div>}
      {(page > 1 || list.data?.next) && <nav aria-label="Strony alertów" className="flex gap-3">
        <button disabled={page <= 1 || saving !== null} onClick={() => navigate(unseen, page - 1)}>Poprzednia</button>
        <span>Strona {page}</span>
        <button disabled={!list.data?.next || saving !== null} onClick={() => navigate(unseen, page + 1)}>Następna</button>
      </nav>}</>}
  </main>;
}
