"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { api } from "@/lib/api";
import { markerValue, adTitle, hostOf, SOURCE_LABELS } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import { ObservationTimeline } from "./observation-timeline";
import { ErrorBox, FamilyDot, GroupLink, Loading } from "./ui";

type GroupKind = "operators" | "campaigns";

export function GroupList({ kind }: { kind: GroupKind }) {
  const [all, setAll] = useState(false);
  const source = all ? undefined : "capture";
  const groups = useApi(kind + ":" + source, () => api[kind](source));
  return <main className="atlas-page">
    <h1 className="atlas-title">{kind === "operators" ? "Operatorzy" : "Kampanie"}</h1>
    <label className="flex items-center gap-2"><input type="checkbox" checked={all} onChange={e => setAll(e.target.checked)} />Wszystkie grupy</label>
    <p className="text-muted">{all ? "Wszystkie źródła" : "Grupy zawierające materiały spraw"}</p>
    {groups.loading ? <Loading /> : groups.error ? <ErrorBox message={groups.error} onRetry={groups.reload} /> : groups.data?.count ? <div className="atlas-table"><table className="dense"><thead><tr><th>Grupa</th><th>Nazwa</th><th>Reklamy</th><th>Źródła reklam</th><th>Sprawy</th><th>Reklamy z domeną na liście CERT</th></tr></thead>
      <tbody>{groups.data.results.map(group => <tr key={group.id}>
        <td><Link className="text-accent" href={`/${kind}/${group.id}`}>{group.key}</Link></td>
        <td>{group.label}</td><td>{group.size}</td>
        <td>{Object.entries(group.sources ?? {}).map(([key, count]) => `${SOURCE_LABELS[key] ?? key}: ${count}`).join(" · ") || "Brak danych"}</td><td>{group.cases ?? "—"}</td><td>{group.cert_pl ?? "—"}</td>
      </tr>)}</tbody></table></div> : <p>Brak grup w wybranym zakresie.</p>}
  </main>;
}

export function GroupCard({ kind }: { kind: GroupKind }) {
  const { id } = useParams<{id: string}>();
  const valid = /^[1-9]\d*$/.test(id) && Number.isSafeInteger(Number(id));
  const operator = kind === "operators";
  const result = useApi(valid ? kind + id : null, () => operator ? api.operator(Number(id)) : api.campaign(Number(id)));
  if (!valid) return <p>Nieprawidłowy identyfikator grupy.</p>;
  if (result.loading) return <Loading />;
  if (result.error) return <ErrorBox message={result.error} onRetry={result.reload} />;
  const group = result.data;
  if (!group) return null;
  const metrics = [
    ["Reklamy", group.size],
    ["Kampanie", new Set(group.ads.map(ad => ad.campaign).filter(Boolean)).size],
    ["Domeny", new Set(group.ads.map(ad => hostOf(ad.landing_url)).filter(Boolean)).size],
    ["Sprawy", new Set(group.ads.map(ad => ad.case).filter(Boolean)).size],
    ["Domeny na liście CERT", new Set(group.ads.map(ad => ad.labels.cert_pl?.domain).filter(Boolean)).size],
  ] as const;
  const sorted = [...group.core_markers].sort((a,b) => Number(b.decisive) - Number(a.decisive) || b.in_group - a.in_group || a.ad_count - b.ad_count);
  const paths = sorted.filter(marker => marker.kind === "kit_path");
  const markers = sorted.filter(marker => marker.kind !== "kit_path");
  const top = markers[0] ?? paths[0];
  return <main className="atlas-page atlas-group">
    <header className="flex flex-wrap items-center justify-between gap-3"><h1 className="atlas-title">{group.key} {group.label}</h1>
      <Link className="rounded-md bg-accent px-3 py-2 font-medium text-white" href={`/investigation?${operator ? "operator" : "campaign"}=${id}`}>Otwórz graf grupy</Link></header>
    <section><dl className="flex flex-wrap gap-x-8 gap-y-3">{metrics.map(([name,value]) => <div key={name}><dt className="text-muted">{name}</dt><dd className="text-2xl font-semibold">{value}</dd></div>)}</dl>
      {top && <p className="mt-3">Wspólny ślad: {top.label} · {markerValue(top.value, top.display_value)} ({top.in_group} z {group.size} reklam).</p>}
    </section>
    <section><h2>Markery rdzeniowe</h2>
      {markers.length ? <table className="dense"><thead><tr><th>Marker</th><th>Wartość</th><th>Reklamy w grupie</th><th>W korpusie</th></tr></thead>
        <tbody>{markers.map(marker => <tr key={JSON.stringify([marker.kind, marker.value])}>
          <td><FamilyDot family={marker.family} /> {marker.label}</td><td className="break-all font-mono">{markerValue(marker.value, marker.display_value)}</td>
          <td>{marker.in_group}</td><td>{marker.ad_count}</td></tr>)}</tbody></table> : !paths.length && <p>Brak markerów rdzeniowych.</p>}
      {!!paths.length && <details><summary>Ścieżki zaplecza ({paths.length})</summary><ul>{paths.map(m => <li key={m.value} className="break-all">{m.display_value || m.value} · w grupie {m.in_group}, w korpusie {m.ad_count}</li>)}</ul></details>}
    </section>
    <ObservationTimeline key={kind + id} id={Number(id)} operator={operator} />
    {"campaigns" in group && Array.isArray(group.campaigns) && <section><h2>Kampanie operatora</h2>
      {group.campaigns.length ? <ul>{group.campaigns.map(key => <li key={key}><GroupLink group={key} /></li>)}</ul> : <p>Brak przypisanych kampanii.</p>}</section>}
    <section><h2>Reklamy ({group.size})</h2><ul>{group.ads.map(ad =>
      <li key={ad.id}><Link className="text-accent" href={`/ads/${ad.id}`}>#{ad.id} · {adTitle(ad)}</Link></li>)}</ul></section>
  </main>;
}
