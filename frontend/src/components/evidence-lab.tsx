"use client";
import { SourceLink } from "./har-overview";

import { ContentSimilarity } from "./content-similarity";

import { WeakestLinkTest } from "./weakest-link-test";
import { useState } from "react";
import { api, type EdgeDetail } from "@/lib/api";
import { useExpert } from "@/lib/expert";
import { bits, markerValue, utcEdgeVersion } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import { ContextSection } from "./context-section";

export function EvidenceLab({ edge, refresh, open, onToggle }: { edge: EdgeDetail; refresh: () => void; open: boolean; onToggle: () => void }) {
  const { expert } = useExpert();
  const [excluded, setExcluded] = useState<number[]>([]);
  const ready = edge.updated_at && edge.evidence.length > 0 && edge.evidence.every(item => Number.isInteger(item.id));
  const query = useApi(open && ready ? JSON.stringify([edge.id, edge.updated_at, excluded]) : null,
    () => api.simulateEdge(edge.id, excluded, utcEdgeVersion(edge.updated_at)));
  const result = query.data;
  return <ContextSection title="Laboratorium dowodów" hint="Sprawdź bez zapisu, co zostanie z hipotezy, gdy pominiesz wybrane ślady." open={open} onToggle={onToggle}>
    {expert && <p>Symulacja bez zapisu. Wyłącz dowody, aby sprawdzić ich wpływ.</p>}
    {!ready ? <p>Brak danych wymaganych do symulacji.</p> : <>
      <WeakestLinkTest edge={edge} apply={setExcluded} refresh={refresh} />
      <fieldset className="max-h-48 overflow-auto"><legend>Wybierz dowody do wyłączenia · zaznaczono {excluded.length} z {edge.evidence.length}</legend>
        {edge.evidence.map(item => <div key={item.id} className="border-b border-line py-1">
          <label className={expert ? "break-all" : "break-words"}><input type="checkbox" checked={excluded.includes(item.id)}
            onChange={event => setExcluded(event.target.checked ? [...excluded, item.id] : excluded.filter(id => id !== item.id))} />
            {" "}{item.label}{expert && <> · {markerValue(item.value_a, item.display_value)}{item.value_a !== item.value_b && " / " + markerValue(item.value_b)}</>}</label>

          {expert && <ContentSimilarity kind={item.kind} similarity={item.similarity} />}
          <div className="flex gap-2 text-muted">{item.family_label}
            {([["A", item.artifact_a], ["B", item.artifact_b]] as const).map(([side, sha]) => sha &&
              <SourceLink key={side} sha={sha} side={side}>Źródło {side}</SourceLink>)}
          </div>
        </div>)}
      </fieldset>
      <button type="button" className="justify-self-start text-accent underline disabled:opacity-50" disabled={!excluded.length}
        onClick={() => setExcluded([])}>Przywróć wszystkie dowody</button>
      <div aria-live="polite">
        {query.loading ? "Przeliczanie pary…" : query.error ?
          query.status === 409 ? <p>Dane krawędzi zmieniły się. <button type="button" className="underline" onClick={refresh}>Odśwież dowody</button></p> :
            <p>Symulacja niedostępna. <button type="button" className="underline" onClick={query.reload}>Ponów</button></p> :
          result?.baseline && result.simulated && Array.isArray(result.simulated.reasons) ? <>
            <h3 className="font-semibold">Wpływ na parę</h3>
            {([["Przed", result.baseline], ["Po", result.simulated]] as const).map(([label, value]) => {
              return <p key={String(label)}>{String(label)} · {value.relation === null ? "Brak powiązania" : value.relation_label}{expert && <> · {value.bits == null ? "—" : `${bits(value.bits)} bita`}</>}</p>;
            })}
            <ul>{result.simulated.reasons.map(reason => <li key={reason}>{reason}</li>)}</ul>
            <h3 className="mt-2 font-semibold">Wpływ na grupy</h3>
            <p>Kampania · {result.group_impact?.campaign?.note || "Dane niedostępne"}</p>
            <p>Operator · {result.group_impact?.operator?.note || "Dane niedostępne"}</p>
            {result.warnings?.map(note => <p key={note}>{note}</p>)}
          </> : <p>Brak wyniku symulacji.</p>}
      </div>
    </>}
  </ContextSection>;
}
