"use client";

import { useState } from "react";
import { api, type KindWeights } from "@/lib/api";
import { num } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import { Loading, ErrorBox } from "@/components/ui";

function difference(kind: KindWeights) {
  return kind.learned && kind.learned.source !== "expert" ? kind.learned.bits - kind.expert.bits : null;
}

export default function WeightsPage() {
  const [sortByDifference, setSortByDifference] = useState(false);
  const result = useApi("weights", api.weights);
  if (result.loading) return <Loading />;
  if (result.error) return <ErrorBox message={result.error} onRetry={result.reload} />;
  const data = result.data;
  if (!data) return null;
  const families = new Map<string, KindWeights[]>();
  for (const kind of data.kinds) {
    const rows = families.get(kind.family_label) ?? [];
    rows.push(kind);
    families.set(kind.family_label, rows);
  }
  if (sortByDifference) {
    for (const rows of families.values()) rows.sort((a, b) => Math.abs(difference(b) ?? 0) - Math.abs(difference(a) ?? 0));
  }
  return <main className="atlas-page"><h1 className="atlas-title">Wagi markerów</h1>
    <p>Waga określa, jak mocno zgodność markera przemawia za powiązaniem reklam. Jeden dodatkowy bit podwaja iloraz wiarygodności. Wagi eksperckie ustalono ręcznie, a wagi uczone oszacowano metodą EM w modelu Fellegiego–Suntera na parach reklam bez etykiet.</p>
    <p>Aktywne wagi: <strong>{data.active === "learned" ? "uczone" : "eksperckie"}</strong> · Wersja modelu oceny powiązań · {data.model_version}</p>
    {!data.learned_available && <p>Wagi uczone niedostępne. {data.learned_error}</p>}
    <label><input type="checkbox" checked={sortByDifference} onChange={e => setSortByDifference(e.target.checked)}/> Największe różnice najpierw w każdej rodzinie</label>
    <p className="text-muted">Myślnik oznacza brak odrębnej wagi uczonej. Wyróżniono różnice powyżej 0,5 bita w obu kierunkach.</p>
    <div className="atlas-table"><table className="dense"><thead><tr><th>Typ markera</th><th>Eksperckie (bity)</th><th>Uczone (bity)</th><th>Różnica (bity)</th></tr></thead>
      {Array.from(families, ([family, rows]) => <tbody key={family}>
        <tr><th colSpan={4} scope="rowgroup" className="bg-raised text-left">{family}</th></tr>
        {rows.map(kind => {
          const delta = difference(kind);
          return <tr key={kind.code} className={delta !== null && Math.abs(delta) > 0.5 ? "bg-accent-soft font-semibold" : undefined}>
            <td>{kind.label}</td><td>{num(kind.expert.bits)}</td><td>{delta !== null && kind.learned ? num(kind.learned.bits) : "—"}</td>
            <td>{delta === null ? "—" : (delta > 0 ? "+" : "") + num(delta)}</td>
          </tr>;
        })}
      </tbody>)}
    </table></div></main>;
}
