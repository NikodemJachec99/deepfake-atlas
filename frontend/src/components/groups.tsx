"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { api } from "@/lib/api";
import { markerValue, adTitle } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import { ObservationTimeline } from "./observation-timeline";
import { ErrorBox, FamilyDot, GroupLink, Loading } from "./ui";

type GroupKind = "operators" | "campaigns";

export function GroupList({ kind }: { kind: GroupKind }) {
  const groups = useApi(kind, api[kind]);
  if (groups.loading) return <Loading />;
  if (groups.error) return <ErrorBox message={groups.error} onRetry={groups.reload} />;
  return <main className="p-4">
    <h1 className="mb-3 text-lg">{kind === "operators" ? "Operatorzy" : "Kampanie"}</h1>
    {groups.data?.count ? <table className="dense"><thead><tr><th>Grupa</th><th>Nazwa</th><th>Reklamy</th></tr></thead>
      <tbody>{groups.data.results.map(group => <tr key={group.id}>
        <td><Link className="text-accent" href={`/${kind}/${group.id}`}>{group.key}</Link></td>
        <td>{group.label}</td><td>{group.size}</td>
      </tr>)}</tbody></table> : <p>Brak grup w korpusie.</p>}
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
  return <main className="flex flex-col gap-4 p-4">
    <header><h1 className="text-lg">{group.key} {group.label}</h1>
      <Link className="text-accent" href={`/investigation?${operator ? "operator" : "campaign"}=${id}`}>Otwórz graf grupy</Link></header>
    <ObservationTimeline key={kind + id} id={Number(id)} operator={operator} />
    {"campaigns" in group && Array.isArray(group.campaigns) && <section><h2>Kampanie operatora</h2>
      {group.campaigns.length ? <ul>{group.campaigns.map(key => <li key={key}><GroupLink group={key} /></li>)}</ul> : <p>Brak przypisanych kampanii.</p>}</section>}
    <section><h2>Reklamy ({group.size})</h2><ul>{group.ads.map(ad =>
      <li key={ad.id}><Link className="text-accent" href={`/ads/${ad.id}`}>#{ad.id} · {adTitle(ad)}</Link></li>)}</ul></section>
    <section><h2>Markery rdzeniowe</h2>
      {group.core_markers.length ? <table className="dense"><thead><tr><th>Marker</th><th>Wartość</th><th>Reklamy w grupie</th><th>W korpusie</th></tr></thead>
        <tbody>{group.core_markers.map(marker => <tr key={JSON.stringify([marker.kind, marker.value])}>
          <td><FamilyDot family={marker.family} /> {marker.label}</td><td className="break-all font-mono">{markerValue(marker.value, marker.display_value)}</td>
          <td>{marker.in_group}</td><td>{marker.ad_count}</td></tr>)}</tbody></table> : <p>Brak markerów rdzeniowych.</p>}</section>
  </main>;
}
