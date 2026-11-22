"use client";

import Link from "next/link";
import { api, type EdgeDetail } from "@/lib/api";
import { useExpert } from "@/lib/expert";
import { dateTime, VERDICT_LABELS } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import { ContextSection } from "./context-section";

export function DecisionHistory({ edge, open, onToggle }: { edge: EdgeDetail; open: boolean; onToggle: () => void }) {
  const { expert } = useExpert();
  const key = open ? JSON.stringify([edge.id, edge.verdict_at, edge.updated_at]) : null;
  const history = useApi(key, () => api.edgeDecisions(edge.id));
  const prior = useApi(key, () => api.edgePrecedents(edge.id));
  return <ContextSection title="Historia decyzji i precedensy" hint="Co już postanowiono przy tej parze i przy podobnych parach." open={open} onToggle={onToggle}>
    <h3 className="font-semibold">Historia tej pary</h3>
    {history.loading ? "Pobieranie historii…" : history.error || !Array.isArray(history.data?.decisions) ?
      <p>Historia niedostępna. <button className="underline" onClick={history.reload}>Ponów odczyt historii</button></p> :
      history.data.decisions.length ? <ul>{history.data.decisions.map(d => <li key={d.id} className="border-t border-line py-1">
        {dateTime(d.created_at)} · {VERDICT_LABELS[d.verdict]} · {d.reason === "unknown" || !d.reason_label ? "Brak podanego powodu" : d.reason_label}
        {d.note && <p>{d.note}</p>}
      </li>)}</ul> : <p className="text-muted">Tej pary nikt jeszcze nie oceniał.</p>}
    <h3 className="font-semibold">Rozstrzygnięcia podobnych par</h3>
    {expert && <p>Wcześniejsze decyzje stanowią kontekst do oceny tej pary.</p>}
    {prior.loading ? "Pobieranie precedensów…" : prior.error || !Array.isArray(prior.data?.precedents) ?
      <p>Precedensy niedostępne. <button className="underline" onClick={prior.reload}>Ponów odczyt precedensów</button></p> : <>
      {prior.data.notice && <p className="text-muted">{prior.data.notice}</p>}
      {!prior.data.precedents.length && <p className="text-muted">Brak podobnych rozstrzygnięć.</p>}
      {prior.data.precedents.map(d => <article key={d.decision} className="border-t border-line py-1">
        <h4 className="font-medium">{dateTime(d.created_at)} · {VERDICT_LABELS[d.verdict]}</h4>
        <p>{d.reason_known ? d.reason_label : "Brak podanego powodu"}</p>{d.note && <p>{d.note}</p>}
        <dl><dt className="font-semibold">Podobieństwa</dt><dd>{d.why.join(" ") || "Brak wskazanych podobieństw."}</dd>
        <dt className="mt-1 font-semibold">Różnice</dt><dd>{d.differences.join(" ") || "Brak wskazanych różnic."}</dd></dl>
        {d.edge && <Link className="text-accent underline" href={`/investigation?scope=all&edge=${d.edge}`}>{expert ? `Dowody powiązania #${d.edge}` : "Zobacz dowody tamtej pary"}</Link>}
      </article>)}
    </>}
  </ContextSection>;
}
