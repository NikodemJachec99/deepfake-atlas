"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { api, exportCorpusUrl } from "@/lib/api";
import { adTitle, SOURCE_LABELS } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import { ErrorBox, GroupLink, Loading } from "@/components/ui";

const filters = [
  ["q", "Szukaj"], ["source", "Źródło"], ["campaign", "ID kampanii"],
  ["operator", "ID operatora"], ["case", "Sprawa"],
] as const;

export default function Archive() {
  const [wholeCorpus, setWholeCorpus] = useState(false);
  const params = useSearchParams();
  const router = useRouter();
  const query = params.toString();
  const data = useApi("archive:" + query, () => api.ads(query ? "?" + query : ""));
  const previous = data.data?.previous;
  const page = previous ? Number(new URL(previous, "http://localhost").searchParams.get("page") || "1") + 1 : 1;
  const lastPage = new URLSearchParams(params);
  lastPage.set("page", "last");
  function navigate(next: URLSearchParams) {
    router.push(next.size ? "/archive?" + next : "/archive");
  }
  function turnPage(number: number) {
    const next = new URLSearchParams(params);
    next.set("page", String(number));
    navigate(next);
  }
  return <main className="atlas-page">
    <h1 className="atlas-title">Archiwum reklam</h1>
    <details className="rounded-md border border-line p-3">
      <summary className="font-medium">Pobierz wzbogacony korpus</summary>
      <p className="my-2 text-muted">ZIP zawiera reklamy z markerami, powiązania z dowodami, grupy i opis danych. Tokeny zapisano wyłącznie jako skróty.</p>
      <label>Zakres eksportu <select className="border border-line p-1" value={wholeCorpus ? "all" : "capture"} onChange={event => setWholeCorpus(event.target.value === "all")}>
        <option value="capture">Materiały spraw</option><option value="all">Cały korpus</option>
      </select></label>
      <a className="ml-3 text-accent underline" download href={exportCorpusUrl(wholeCorpus ? undefined : "capture")}>Pobierz ZIP</a>
    </details>
    <form key={query} onReset={() => { if (query) router.push("/archive"); }} className="atlas-filters" onSubmit={event => {
      event.preventDefault();
      const form = new FormData(event.currentTarget);
      const next = new URLSearchParams();
      for (const [key] of filters) {
        const value = String(form.get(key) ?? "").trim();
        if (value) next.set(key, value);
      }
      navigate(next);
    }}>
      {filters.map(([key, label]) => <label key={key} className="grid gap-1 text-sm font-medium text-muted">
        {label}{key === "source" ? <select name={key} defaultValue={params.get(key) ?? ""} className="rounded-md border border-line-strong bg-raised px-2 py-2">
          <option value="">Wszystkie</option>{Object.entries(SOURCE_LABELS).map(([value, name]) => <option key={value} value={value}>{name}</option>)}
        </select> : <input name={key} defaultValue={params.get(key) ?? ""} className="w-40 rounded-md border border-line-strong bg-raised px-2 py-2 text-fg"
          type={key === "campaign" || key === "operator" ? "number" : "text"} min="1" />}
      </label>)}
      <button className="rounded-md bg-accent px-3 py-2 font-medium text-white">Zastosuj filtry</button>
      <button type="reset" className="p-1 text-accent">Wyczyść</button>
    </form>
    {data.loading ? <Loading /> : data.error ? <ErrorBox message={data.error} onRetry={data.reload}
      missing={data.status === 404 && params.has("page") && params.get("page") !== "last" ? {
        description: "Ta strona wyników jest niedostępna.",
        href: "/archive?" + lastPage,
        link: "Otwórz ostatnią stronę wyników",
      } : undefined}/> : data.data &&
      <><p>Wyniki: {data.data.count}</p>
      {data.data.results.length ? <div className="atlas-table"><table className="dense"><thead><tr>
        <th>Reklama</th><th>Źródło</th><th>Sprawa</th><th>Kampania</th><th>Operator</th>
      </tr></thead><tbody>{data.data.results.map(ad => <tr key={ad.id}>
        <td><Link className="text-accent" href={`/ads/${ad.id}`}>#{ad.id} · {adTitle(ad)}</Link></td>
        <td>{SOURCE_LABELS[ad.source] ?? ad.source}</td><td>{ad.case ?? "—"}</td>
        <td><GroupLink group={ad.campaign} /></td><td><GroupLink group={ad.operator} /></td>
      </tr>)}</tbody></table></div> : <div className="grid justify-items-start gap-2"><p>{query ? "Brak reklam odpowiadających filtrom." : "Archiwum jest puste."}</p>
        <Link className="text-accent underline" href={query ? "/archive" : "/#input-kind"}>{query ? "Wyczyść filtry" : "Dodaj materiał"}</Link></div>}
      <nav aria-label="Strony wyników" className="flex gap-3">
        <button disabled={!data.data.previous} className="disabled:opacity-40" onClick={() => turnPage(page - 1)}>Poprzednia</button>
        <span>Strona {page}</span>
        <button disabled={!data.data.next} className="disabled:opacity-40" onClick={() => turnPage(page + 1)}>Następna</button>
      </nav></>}
  </main>;
}
