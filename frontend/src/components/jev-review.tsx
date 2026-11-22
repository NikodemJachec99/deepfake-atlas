"use client";

import { api, RELATION_LABELS, type AssistStatus, type EdgeDetail } from "@/lib/api";
import { useExpert } from "@/lib/expert";
import { bits, dateTime } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import { ContextSection } from "./context-section";

const statusLabel: Record<AssistStatus, string> = {
  disabled: "Model wyłączony", none: "Brak zapisanego wyniku", shadow: "Wynik ukryty w trybie obserwacji",
  ok: "Zapisana sugestia", abstain: "Model wstrzymał się od odpowiedzi",
  unavailable: "Model niedostępny", timeout: "Przekroczono czas oczekiwania", error: "Błąd modelu",
  unauthorized: "Brak uprawnień do modelu", payment: "Problem z rozliczeniem modelu",
  rate_limited: "Osiągnięto limit zapytań",
};

export function JevReview({ edge, open, onToggle }: { edge: EdgeDetail; open: boolean; onToggle: () => void }) {
  const { expert } = useExpert();
  const result = useApi(open ? JSON.stringify([edge.id, edge.updated_at, edge.verdict_at]) : null, () => api.edgeAssist(edge.id));
  const data = result.data;
  const suggestion = data?.suggestion;
  return <ContextSection title="Sugestia przeglądu Jev" hint="Podpowiedź modelu pomocniczego. Decyzję i tak podejmujesz Ty." open={open} onToggle={onToggle}>
    {result.loading ? "Pobieranie sugestii…" : result.error || !data ? <p>Sugestia niedostępna. <button className="text-accent underline" onClick={result.reload}>Ponów odczyt</button></p> : <>
      <strong>{statusLabel[data.status]}</strong>
      {data.visible && suggestion?.label && <p>{suggestion.label}</p>}
      {suggestion?.stale && <p className="font-semibold">Wynik nieaktualny względem bieżących przesłanek.</p>}
      {suggestion?.uncertain && <p>Model oznaczył odpowiedź jako niepewną.</p>}
      {expert && <p className="text-muted">Jev to model pomocniczy. Panel odczytuje zapisaną sugestię bez uruchamiania modelu.</p>}
      {expert && data.status !== "disabled" && <p>Model · {suggestion?.served_model || suggestion?.model || data.model || "brak informacji"} · wersja pytania {suggestion?.question_version ?? data.question_version}</p>}
      {suggestion && <p className="text-muted">Zapis sugestii · {dateTime(suggestion.created_at)}</p>}
      <p>{data.notice}</p>
      {expert && <details><summary>Bieżące przesłanki przeglądu</summary>
        <p>{RELATION_LABELS[data.premises.relacja]} · {bits(data.premises.bity)} bita · niezależne grupy śladów {data.premises.niezalezne_grupy} (zaplecze {data.premises.niezalezne_grupy_zaplecza})</p>
        {data.premises.grupy_sladow.length ? <ul>{data.premises.grupy_sladow.map(g =>
          <li key={g.grupa}>{g.grupa} · ślady {g.slady} · {bits(g.bity)} bita{g.rozstrzygajacy && " · ślad rozstrzygający"}</li>)}</ul> : <p>Brak grup śladów w danych wejściowych.</p>}
      </details>}
      <p className="text-muted">Decyzję zapisuje analityk. Jev nie ustala kolejności precedensów.</p>
    </>}
  </ContextSection>;
}
