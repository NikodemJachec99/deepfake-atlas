"use client";

import { api } from "@/lib/api";
import { num } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import { Loading, ErrorBox } from "@/components/ui";

export default function WeightsPage() {
  const result = useApi("weights", api.weights);
  if (result.loading) return <Loading />;
  if (result.error) return <ErrorBox message={result.error} onRetry={result.reload} />;
  const data = result.data;
  if (!data) return null;
  return <main className="atlas-page"><h1 className="atlas-title">Wagi markerów</h1>
    <p>Aktywne wagi: <strong>{data.active === "learned" ? "uczone" : "eksperckie"}</strong> · Wersja modelu oceny powiązań · {data.model_version}</p>
    {!data.learned_available && <p>Wagi uczone niedostępne. {data.learned_error}</p>}
    <div className="atlas-table"><table className="dense"><thead><tr><th>Typ markera</th><th>Rodzina</th><th>Eksperckie (bity)</th><th>Uczone (bity)</th></tr></thead>
      <tbody>{data.kinds.map(kind => <tr key={kind.code}><td>{kind.label}</td><td>{kind.family_label}</td><td>{num(kind.expert.bits, 2)}</td>
        <td>{kind.learned ? num(kind.learned.bits, 2) + (kind.learned.source === "expert" ? " (wartość ekspercka)" : "") : "—"}</td></tr>)}</tbody>
    </table></div></main>;
}
