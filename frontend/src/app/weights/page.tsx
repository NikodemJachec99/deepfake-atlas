"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useState } from "react";
import { api, type KindWeights } from "@/lib/api";
import { num } from "@/lib/format";
import { useExpert } from "@/lib/expert";
import { useApi } from "@/lib/hooks";
import { Loading, ErrorBox, FamilyDot, Tag } from "@/components/ui";

const STRENGTH: [number, string][] = [[16, "bardzo silny"], [8, "silny"], [4, "umiarkowany"], [0, "słaby"]];

function strength(bits: number) {
  return STRENGTH.find(([min]) => bits >= min)?.[1] ?? "słaby";
}

function difference(kind: KindWeights) {
  return kind.learned && kind.learned.source !== "expert" ? kind.learned.bits - kind.expert.bits : null;
}

export default function WeightsPage() {
  const kindCode = useSearchParams().get("kind");
  const [sortByDifference, setSortByDifference] = useState(false);
  const { expert } = useExpert();
  const result = useApi("weights", api.weights);
  if (result.loading) return <Loading />;
  if (result.error) return <ErrorBox message={result.error} onRetry={result.reload} />;
  const data = result.data;
  if (!data) return null;
  const families = new Map<string, KindWeights[]>();
  for (const kind of data.kinds) {
    if (kindCode && kind.code !== kindCode) continue;
    const rows = families.get(kind.family_label) ?? [];
    rows.push(kind);
    families.set(kind.family_label, rows);
  }
  if (sortByDifference) {
    for (const rows of families.values()) rows.sort((a, b) => Math.abs(difference(b) ?? 0) - Math.abs(difference(a) ?? 0));
  }
  if (!expert) {
    const active = (kind: KindWeights) => data.active === "learned" && kind.learned ? kind.learned.bits : kind.expert.bits;
    const max = Math.max(1, ...data.kinds.map(active));
    return <main className="atlas-page">
      <header className="grid gap-2">
        <h1 className="atlas-title">Wagi markerów</h1>
        <p className="max-w-3xl text-pretty text-muted">Każdy rodzaj śladu ma swoją wagę. Im silniejszy ślad, tym mocniej to, że dwie reklamy go dzielą, przemawia za wspólnym źródłem. Ślad „rozstrzyga”, gdy sam wystarcza do powiązania.</p>
      </header>
      {kindCode && <Link href="/weights" className="w-fit text-accent underline">Pokaż wagi wszystkich markerów</Link>}
      {!families.size && <p>Brak tego typu markera w bieżącym modelu.</p>}
      <div className="grid gap-4 lg:grid-cols-2">{Array.from(families, ([family, rows]) => <section key={family} className="min-w-0 rounded-xl border border-line p-4">
        <h2 className="mb-2 flex items-center gap-2 text-lg font-semibold"><FamilyDot family={rows[0].family} />{family}</h2>
        <ul className="grid gap-2">{[...rows].sort((a, b) => active(b) - active(a)).map(kind => <li key={kind.code} className="grid gap-1">
          <p className="flex flex-wrap items-center justify-between gap-x-3"><span className="flex items-center gap-2">{kind.label}{kind.decisive && <Tag tone="accent">rozstrzyga</Tag>}</span><span className="text-sm text-muted">{strength(active(kind))}</span></p>
          <span aria-hidden className="h-1.5 overflow-hidden rounded-full bg-panel"><span className="block h-full rounded-full bg-accent" style={{ width: `${Math.max(4, active(kind) / max * 100)}%` }} /></span>
        </li>)}</ul>
      </section>)}</div>
    </main>;
  }
  return <main className="atlas-page"><h1 className="atlas-title">Wagi markerów</h1>
    <p>Waga określa, jak mocno zgodność markera przemawia za powiązaniem reklam. Jeden dodatkowy bit podwaja iloraz wiarygodności. Wagi eksperckie ustalono ręcznie, a wagi uczone oszacowano metodą EM w modelu Fellegiego–Suntera na parach reklam bez etykiet.</p>
    <p>Aktywne wagi: <strong>{data.active === "learned" ? "uczone" : "eksperckie"}</strong> · Wersja modelu oceny powiązań · {data.model_version}</p>
    {!data.learned_available && <p>Wagi uczone niedostępne. {data.learned_error}</p>}
    {kindCode && <Link href="/weights" className="w-fit text-accent underline">Pokaż wagi wszystkich markerów</Link>}
    {!families.size && <p>Brak tego typu markera w bieżącym modelu.</p>}
    {!kindCode && <label><input type="checkbox" checked={sortByDifference} onChange={e => setSortByDifference(e.target.checked)}/> Największe różnice najpierw w każdej rodzinie</label>}
    <p className="text-muted">Myślnik oznacza brak odrębnej wagi uczonej. Wyróżniono różnice powyżej 0,5 bita w obu kierunkach.</p>
    {families.size > 0 && <div className="atlas-table"><table className="dense"><thead><tr><th>Typ markera</th><th>Eksperckie (bity)</th><th>Uczone (bity)</th><th>Różnica (bity)</th></tr></thead>
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
    </table></div>}</main>;
}
