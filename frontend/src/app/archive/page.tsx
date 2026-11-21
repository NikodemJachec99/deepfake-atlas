"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import { adTitle, SOURCE_LABELS } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import { ErrorBox, GroupLink, Loading } from "@/components/ui";

const filters = [
  ["q", "Szukaj"], ["source", "Źródło"], ["campaign", "ID kampanii"],
  ["operator", "ID operatora"], ["case", "Sprawa"],
] as const;

export default function Archive() {
  const params = useSearchParams();
  const router = useRouter();
  const query = params.toString();
  const data = useApi("archive:" + query, () => api.ads(query ? "?" + query : ""));
  const page = Number(params.get("page") || "1");
  function navigate(next: URLSearchParams) {
    router.push(next.size ? "/archive?" + next : "/archive");
  }
  function turnPage(number: number) {
    const next = new URLSearchParams(params);
    next.set("page", String(number));
    navigate(next);
  }
  return <main className="flex flex-col gap-4 p-4">
    <h1 className="text-lg">Archiwum reklam</h1>
    <form key={query} className="flex flex-wrap items-end gap-2" onSubmit={event => {
      event.preventDefault();
      const form = new FormData(event.currentTarget);
      const next = new URLSearchParams();
      for (const [key] of filters) {
        const value = String(form.get(key) ?? "").trim();
        if (value) next.set(key, value);
      }
      navigate(next);
    }}>
      {filters.map(([key, label]) => <label key={key} className="flex flex-col text-muted">
        {label}{key === "source" ? <select name={key} defaultValue={params.get(key) ?? ""} className="border border-line bg-panel p-1">
          <option value="">Wszystkie</option>{Object.entries(SOURCE_LABELS).map(([value, name]) => <option key={value} value={value}>{name}</option>)}
        </select> : <input name={key} defaultValue={params.get(key) ?? ""} className="w-40 border border-line bg-panel p-1 text-fg"
          type={key === "campaign" || key === "operator" ? "number" : "text"} min="1" />}
      </label>)}
      <button className="border border-line p-1">Zastosuj filtry</button>
      <Link href="/archive" className="p-1 text-accent">Wyczyść</Link>
    </form>
    {data.loading ? <Loading /> : data.error ? <ErrorBox message={data.error} onRetry={data.reload} /> : data.data &&
      <><p>Wyniki: {data.data.count}</p>
      {data.data.results.length ? <div className="overflow-x-auto"><table className="dense"><thead><tr>
        <th>Reklama</th><th>Źródło</th><th>Sprawa</th><th>Kampania</th><th>Operator</th>
      </tr></thead><tbody>{data.data.results.map(ad => <tr key={ad.id}>
        <td><Link className="text-accent" href={`/ads/${ad.id}`}>#{ad.id} · {adTitle(ad)}</Link></td>
        <td>{SOURCE_LABELS[ad.source] ?? ad.source}</td><td>{ad.case ?? "—"}</td>
        <td><GroupLink group={ad.campaign} /></td><td><GroupLink group={ad.operator} /></td>
      </tr>)}</tbody></table></div> : <p>Brak reklam odpowiadających filtrom.</p>}
      <nav aria-label="Strony wyników" className="flex gap-3">
        <button disabled={!data.data.previous} className="disabled:opacity-40" onClick={() => turnPage(page - 1)}>Poprzednia</button>
        <span>Strona {page}</span>
        <button disabled={!data.data.next} className="disabled:opacity-40" onClick={() => turnPage(page + 1)}>Następna</button>
      </nav></>}
  </main>;
}
