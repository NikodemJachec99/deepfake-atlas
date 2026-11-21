"use client";

import { useState } from "react";
import { api, artifactDownloadUrl, type EdgeDetail } from "@/lib/api";
import { useApi } from "@/lib/hooks";

export function EvidenceLab({ edge, refresh }: { edge: EdgeDetail; refresh: () => void }) {
  const [open, setOpen] = useState(false);
  const [excluded, setExcluded] = useState<number[]>([]);
  const ready = edge.updated_at && edge.evidence.length > 0 && edge.evidence.every(item => Number.isInteger(item.id));
  const query = useApi(open && ready ? JSON.stringify([edge.id, edge.updated_at, excluded]) : null,
    () => api.simulateEdge(edge.id, excluded, edge.updated_at));
  const result = query.data;
  return <section className="border-b border-line p-2">
    <button type="button" aria-expanded={open} className="text-accent underline" onClick={() => setOpen(!open)}>Laboratorium dowodów</button>
    {open && <div className="mt-2 grid gap-2">
      <p>Symulacja bez zapisu. Wyłącz dowody, aby sprawdzić ich wpływ.</p>
      {!ready ? <p>Brak danych wymaganych do symulacji.</p> : <>
        <fieldset className="max-h-48 overflow-auto"><legend>Wyłączone dowody</legend>
          {edge.evidence.map(item => <div key={item.id} className="border-b border-line py-1">
            <label className="break-all"><input type="checkbox" checked={excluded.includes(item.id)}
              onChange={event => setExcluded(event.target.checked ? [...excluded, item.id] : excluded.filter(id => id !== item.id))} />
              {" "}{item.label} · {item.value_a}{item.value_a !== item.value_b && " / " + item.value_b}</label>
            <div className="flex gap-2 text-muted">{item.family_label}
              {([["A", item.artifact_a], ["B", item.artifact_b]] as const).map(([side, sha]) => sha &&
                <a key={side} href={artifactDownloadUrl(sha)} className="text-accent underline">Źródło {side}</a>)}
            </div>
          </div>)}
        </fieldset>
        <button type="button" className="justify-self-start text-accent underline disabled:opacity-50" disabled={!excluded.length}
          onClick={() => setExcluded([])}>Przywróć wszystkie dowody</button>
        <div aria-live="polite">
          {query.loading ? "Przeliczanie pary…" : query.error ?
            query.error.includes("409") ? <p>Dane krawędzi zmieniły się. <button type="button" className="underline" onClick={refresh}>Odśwież dowody</button></p> :
              <p>Symulacja niedostępna. <button type="button" className="underline" onClick={query.reload}>Ponów</button></p> :
            result?.baseline && result.simulated && Array.isArray(result.simulated.reasons) ? <>
              <h3 className="font-semibold">Wpływ na parę</h3>
              {([["Przed", result.baseline], ["Po", result.simulated]] as const).map(([label, value]) => {
                return <p key={String(label)}>{String(label)} · {value.relation === null ? "Brak powiązania" : value.relation_label} · {value.bits?.toFixed(1) ?? "—"} bitów</p>;
              })}
              <ul>{result.simulated.reasons.map(reason => <li key={reason}>{reason}</li>)}</ul>
              <h3 className="mt-2 font-semibold">Wpływ na grupy</h3>
              <p>Kampania · {result.group_impact?.campaign?.note || "Dane niedostępne"}</p>
              <p>Operator · {result.group_impact?.operator?.note || "Dane niedostępne"}</p>
              {result.warnings?.map(note => <p key={note}>{note}</p>)}
            </> : <p>Brak wyniku symulacji.</p>}
        </div>
      </>}
    </div>}
  </section>;
}
