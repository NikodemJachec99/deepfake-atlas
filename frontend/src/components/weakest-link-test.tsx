"use client";

import { useState } from "react";
import { api, artifactDownloadUrl, type EdgeDetail } from "@/lib/api";
import { useApi } from "@/lib/hooks";

export function WeakestLinkTest({ edge, apply, refresh }: { edge: EdgeDetail; apply: (ids: number[]) => void; refresh: () => void }) {
  const [run, setRun] = useState(0);
  const request = useApi(run ? JSON.stringify([edge.id, edge.updated_at, run]) : null,
    () => api.weakestLink(edge.id, { edge_version: edge.updated_at }));
  const result = request.data;
  return <section className="grid gap-2 border-y border-line py-2">
    <button className="justify-self-start text-accent underline disabled:opacity-50" disabled={!!run && request.loading}
      onClick={() => setRun(run + 1)}>Sprawdź najsłabszy punkt</button>
    {run > 0 && <div aria-live="polite">
      {request.loading ? "Sprawdzanie scenariuszy…" : request.error ?
        request.error.includes("409") ? <p>Dane krawędzi zmieniły się. <button className="underline" onClick={refresh}>Odśwież dowody</button></p> :
        <p>Test niedostępny. Spróbuj ponownie.</p> :
        result?.searched && Array.isArray(result.solutions) ? <>
          <p>{result.message}</p>
          <p>Sprawdzone scenariusze {result.searched.scenarios_checked} · do {result.searched.max_group_size} grup · limit {result.searched.scenario_limit} scenariuszy i {result.searched.time_limit_ms} ms</p>
          <p>{result.searched.complete ? "Przeszukano cały zadany zakres." : `Przeszukiwanie niepełne: ${result.searched.stopped_reason}`}</p>
          {result.solutions.map((solution, index) => <details key={solution.groups.join("|")} className="border-t border-line py-1">
            <summary>Scenariusz {index + 1} · {solution.labels.join(", ")}</summary>
            <p>Przed · {result.baseline.relation_label}</p>
            <p>Po · {solution.simulated.relation ? solution.simulated.relation_label : "Brak powiązania"}</p>
            <p>{solution.change}</p>
            {solution.simulated.reasons.map(reason => <p key={reason}>{reason}</p>)}
            <ul>{edge.evidence.filter(item => solution.excluded_evidence.includes(item.id)).map(item => <li key={item.id}>
              {item.family_label} · {item.label}{" "}
              {([["A", item.artifact_a], ["B", item.artifact_b]] as const).map(([side, sha]) => sha && <a key={side} href={artifactDownloadUrl(sha)} className="mr-2 text-accent underline">Źródło {side}</a>)}
            </li>)}</ul>
            <button className="text-accent underline" onClick={() => apply(solution.excluded_evidence)}>Otwórz w ręcznej symulacji</button>
          </details>)}
        </> : <p>Brak danych o przeszukaniu.</p>}
    </div>}
  </section>;
}
