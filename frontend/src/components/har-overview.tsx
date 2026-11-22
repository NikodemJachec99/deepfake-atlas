"use client";

import { Download, FileSearch } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { api, artifactDownloadUrl, type HarEntry, type HarOverview } from "@/lib/api";
import { dateTime, plural } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import { ErrorBox, Loading } from "./ui";

const zadan = (n: number) => `${n} ${plural(n, "żądanie", "żądania", "żądań")}`;

function size(bytes: number | null) {
  if (bytes === null) return "";
  return bytes >= 1024 * 1024 ? `${(bytes / 1024 / 1024).toLocaleString("pl-PL", { maximumFractionDigits: 1 })} MB` : bytes >= 1024 ? `${Math.round(bytes / 1024)} kB` : `${bytes} B`;
}

function statusClass(status: number) {
  return status >= 400 || status === 0 ? "text-rejected" : status >= 300 ? "text-unsure" : "text-fg";
}

function Row({ entry, labels }: { entry: HarEntry; labels: Record<string, string> }) {
  return <li className="grid gap-1 border-b border-line py-2 text-sm">
    <p className="break-all">
      <span className={`mr-2 font-mono font-semibold ${statusClass(entry.status)}`}>{entry.status || "brak"}</span>
      <span className="mr-2 font-mono text-muted">{entry.method}</span>
      <strong className="font-medium">{entry.host}</strong>
      <span className="text-muted">{entry.path}</span>
    </p>
    <p className="text-muted">
      {entry.main && <strong className="mr-2 text-fg">strona główna</strong>}
      {entry.type}{entry.size !== null && ` · ${size(entry.size)}`}{entry.ms !== null && ` · ${entry.ms} ms`}{entry.ip && ` · ${entry.ip}`}
      {entry.redirect_to && <span className="break-all"> · przekierowuje na {entry.redirect_to}</span>}
    </p>
    {entry.traces.length > 0 && <p className="flex flex-wrap gap-1">
      {entry.traces.map(code => <span key={code} className="rounded border border-accent/50 px-1.5 text-xs text-accent">{labels[code] ?? code}</span>)}
    </p>}
  </li>;
}

function Summary({ data }: { data: HarOverview }) {
  const [all, setAll] = useState(data.with_traces === 0);
  const shown = all ? data.entries : data.entries.filter(entry => entry.traces.length > 0);
  return <div className="grid gap-3">
    <p>
      Zapis ruchu sieciowego strony z chwili przechwycenia{data.started_at && <>: {dateTime(data.started_at)}</>}. {zadan(data.total)} do {data.hosts.length}{data.hosts.length >= 30 ? "+" : ""} {plural(data.hosts.length, "hosta", "hostów", "hostów")}.
      {data.with_traces > 0 ? <> {zadan(data.with_traces)} niesie ślady, które system porównuje między reklamami (znaczniki poniżej).</> : " Żadne żądanie nie niesie śladów używanych do porównań."}
    </p>
    {data.chain.length > 0 && <section>
      <h3 className="font-semibold">Droga do strony</h3>
      <ol className="list-decimal pl-5">{data.chain.map((hop, index) => <li key={index} className="break-all">
        <span className={`font-mono font-semibold ${statusClass(hop.status)}`}>{hop.status}</span> {hop.url}
      </li>)}</ol>
    </section>}
    <details><summary className="cursor-pointer text-accent">Hosty, z którymi strona się łączyła</summary>
      <ul className="mt-1 grid gap-0.5">{data.hosts.map(item => <li key={item.host} className="break-all"><span className="font-mono">{item.host || "(bez hosta)"}</span> · {zadan(item.requests)}</li>)}</ul>
    </details>
    <section>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="font-semibold">{all ? "Wszystkie żądania" : "Żądania ze śladami"} ({shown.length})</h3>
        {data.with_traces > 0 && <button type="button" className="text-accent underline" onClick={() => setAll(!all)}>{all ? "Pokaż tylko ze śladami" : `Pokaż wszystkie (${data.total})`}</button>}
      </div>
      <ul>{shown.map(entry => <Row key={entry.n} entry={entry} labels={data.trace_labels} />)}</ul>
      {data.truncated && <p className="text-muted">Lista skrócona do pierwszych {data.entries.length} żądań. Pełny zapis jest w pliku do pobrania.</p>}
    </section>
  </div>;
}

// Odnośnik "Sprawdź źródło": zamiast surowego pliku otwiera czytelne streszczenie HAR.
// Artefakt, który nie jest HAR (np. zapis HTML), pokazuje tylko link do pobrania. Surowy plik zawsze jest pod ręką jako drugi odnośnik.
export function SourceLink({ sha, side, className = "text-accent underline", title, children }: {
  sha: string; side?: string; className?: string; title?: string; children?: React.ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDialogElement>(null);
  const overview = useApi(open ? sha : null, () => api.harOverview(sha));
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);
  const label = side ? `źródło ${side}` : "źródło";
  const notHar = overview.status === 404;
  return <>
    <button type="button" className={className} title={title ?? "Czytelne streszczenie pliku z dowodem"} aria-haspopup="dialog" onClick={() => setOpen(true)}>
      {children ?? <>Sprawdź {label}</>}
    </button>
    <dialog ref={ref} aria-label={`Podgląd: ${label}`} onClose={() => setOpen(false)}
      onClick={event => { if (event.target === event.currentTarget) setOpen(false); }}
      className="m-auto max-h-[92dvh] w-[min(56rem,calc(100vw-1.5rem))] max-w-none overflow-y-auto rounded-lg border border-line bg-panel p-0 text-fg backdrop:bg-black/70">
      {open && <div className="grid gap-3 p-4">
        <div className="flex items-center justify-between gap-3">
          <h2 className="inline-flex items-center gap-2 text-lg font-semibold"><FileSearch size={18} aria-hidden /> Ruch sieciowy strony ({label})</h2>
          <button type="button" autoFocus onClick={() => setOpen(false)} className="rounded-md border border-line px-3 py-1.5 font-medium">Zamknij</button>
        </div>
        {overview.loading ? <Loading label="Czytanie pliku HAR" /> : notHar
          ? <p>To nie jest zapis ruchu sieciowego (HAR), tylko inny plik dowodowy, który da się odczytać po pobraniu.</p>
          : overview.error ? <ErrorBox message={overview.error} onRetry={overview.reload} />
          : overview.data && <Summary data={overview.data} />}
        <p className="border-t border-line pt-2 text-sm text-muted">
          <a href={artifactDownloadUrl(sha)} download className="inline-flex items-center gap-1 text-accent underline"><Download size={12} aria-hidden /> Pobierz surowy plik</a>
          {" "}(tekst techniczny, może zawierać tokeny z przechwycenia; nie otwiera się w przeglądarce).
        </p>
      </div>}
    </dialog>
  </>;
}
