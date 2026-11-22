"use client";

import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { ContextSection } from "./context-section";

export function EdgeSuggestions({ edgeId, open, onToggle }: { edgeId: number; open: boolean; onToggle: () => void }) {
  const result = useApi(open ? String(edgeId) : null, () => api.edgeSuggestions(edgeId));
  const data = result.data;
  return <ContextSection title="Co sprawdzić dalej" hint="Kroki, które mogą potwierdzić albo obalić hipotezę." open={open} onToggle={onToggle}>
    {result.loading ? <p>Pobieranie wskazówek…</p> : result.error ? <p>
      {/API (404|405|501)\b/.test(result.error) ? "Wskazówki dla tej pary są niedostępne." : "Nie udało się pobrać wskazówek."}
      {" "}<button type="button" className="text-accent underline" onClick={result.reload}>Ponów</button>
    </p> : !Array.isArray(data?.suggestions) ? <p>Brak danych o wskazówkach.</p> : <>
      {data.note && <p>{data.note}</p>}
      {data.suggestions.length === 0 && <p>Brak dalszych kroków wskazanych przez API dla tej pary.</p>}
      {data.suggestions.map(item => <article key={item.code} className="grid gap-1 border-t border-line py-2">
        <h3 className="font-semibold">{item.next_step}</h3>
        {item.sides.length > 0 && <p>{item.sides.join(" · ")}</p>}
        <dl className="grid gap-1">
          <div><dt className="text-muted">Hipoteza do sprawdzenia</dt><dd>{item.missing}</dd></div>
          <div><dt className="text-muted">Dlaczego ten krok może pomóc</dt><dd>{item.why}</dd></div>
          <div><dt className="text-muted">Ograniczenie</dt><dd>{item.limitation}</dd></div>
        </dl>
      </article>)}
      {data.warnings.map(note => <p key={note}>{note}</p>)}
    </>}
  </ContextSection>;
}
