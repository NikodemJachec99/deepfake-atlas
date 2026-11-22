"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { api, campaignPackageUrl, operatorPackageUrl } from "@/lib/api";
import { bits, markerValue, adTitle, hostOf, SOURCE_LABELS } from "@/lib/format";
import { allGroups as loadGroups } from "@/lib/group-pages";
import { useApi } from "@/lib/hooks";
import { ObservationTimeline } from "./observation-timeline";
import { ErrorBox, FamilyDot, GroupLink, Loading } from "./ui";

type GroupKind = "operators" | "campaigns";

export function GroupList({ kind }: { kind: GroupKind }) {
  const [all, setAll] = useState(false);
  const source = all ? undefined : "capture";
  const totals = useApi("group-totals", api.stats);
  const groups = useApi(kind + ":" + source, () => loadGroups(kind, source));
  return <main className="atlas-page">
    <h1 className="atlas-title">{kind === "operators" ? "Operatorzy" : "Kampanie"}</h1>
    <label className="flex items-center gap-2"><input type="checkbox" checked={all} onChange={e => setAll(e.target.checked)} />Wszystkie grupy</label>
    <p className="text-muted">{groups.data && totals.data && `Pokazano ${groups.data.results.length} z ${totals.data[kind]} grup · `}{all ? "wszystkie źródła" : "tylko sprawy"}</p>
    {groups.loading ? <Loading /> : groups.error ? <ErrorBox message={groups.error} onRetry={groups.reload} /> : groups.data?.count ? <div className="atlas-table"><table className="dense"><thead><tr><th>Grupa</th><th>Nazwa</th><th>Reklamy</th><th>Źródła reklam</th><th>Sprawy</th><th>Reklamy z domeną na liście CERT</th></tr></thead>
      <tbody>{groups.data.results.map(group => <tr key={group.id}>
        <td><Link className="text-accent" href={`/${kind}/${group.id}`}>{group.key}</Link></td>
        <td>{group.label}</td><td>{group.size}</td>
        <td>{Object.entries(group.sources ?? {}).map(([key, count]) => `${SOURCE_LABELS[key] ?? key}: ${count}`).join(" · ") || "Brak danych"}</td><td>{group.cases ?? "—"}</td><td>{group.cert_pl ?? "—"}</td>
      </tr>)}</tbody></table></div> : <p>Brak grup w wybranym zakresie.</p>}
  </main>;
}

function HuntProfile({ id }: { id: number }) {
  const [open, setOpen] = useState(false);
  const result = useApi(open ? String(id) : null, () => api.huntProfile(id));
  return <details onToggle={event => setOpen(event.currentTarget.open)}><summary>Profil łowiecki operatora</summary>
    {result.loading ? <Loading/> : result.error ? <ErrorBox message={result.error} onRetry={result.reload}/> :
      <ul>{result.data?.patterns.map((pattern, index) => <li key={index}>{pattern.label} · {pattern.value} · {pattern.ad_count} reklam {pattern.ad_ids.map(ad => <Link className="mr-2 text-accent" key={ad} href={`/ads/${ad}`}>#{ad}</Link>)}</li>)}</ul>}
  </details>;
}

export function GroupCard({ kind }: { kind: GroupKind }) {
  const { id } = useParams<{id: string}>();
  const [includeRaw, setIncludeRaw] = useState(false);
  const valid = /^[1-9]\d*$/.test(id) && Number.isSafeInteger(Number(id));
  const operator = kind === "operators";
  const result = useApi(valid ? kind + id : null, () => operator ? api.operator(Number(id)) : api.campaign(Number(id)));
  const pending = useApi(result.data ? "group-review:" + kind + id : null, async () => {
    const members = new Set(result.data!.ads.map(ad => ad.id));
    const rows = [];
    for (let page = 1; ; page++) {
      const queue = await api.review({ page });
      for (const row of queue.results) {
        if (members.has(row.ad_a.id) || members.has(row.ad_b.id)) rows.push({ row, page });
      }
      if (!queue.next) return rows;
    }
  });
  if (!valid) return <p>Nieprawidłowy identyfikator grupy.</p>;
  if (result.loading) return <Loading />;
  if (result.error) return <ErrorBox message={result.error} onRetry={result.reload} missing={result.status === 404 ? {
    description: operator ? `Nie ma takiego operatora (#${id}).` : `Nie ma takiej kampanii (#${id}).`,
    href: `/${kind}`, link: operator ? "Lista operatorów" : "Lista kampanii",
  } : undefined} />;
  const group = result.data;
  if (!group) return null;
  const metrics = [
    ["Reklamy", group.size],
    ["Kampanie", new Set(group.ads.map(ad => ad.campaign).filter(Boolean)).size],
    ["Domeny", new Set(group.ads.map(ad => hostOf(ad.landing_url)).filter(Boolean)).size],
    ["Sprawy", new Set(group.ads.map(ad => ad.case).filter(Boolean)).size],
    ["Domeny na liście CERT", new Set(group.ads.map(ad => ad.labels.cert_pl?.domain).filter(Boolean)).size],
  ] as const;
  const sorted = [...group.core_markers].sort((a,b) => (b.bits ?? -1) - (a.bits ?? -1) || Number(b.decisive) - Number(a.decisive) || b.in_group - a.in_group || a.ad_count - b.ad_count);
  const paths = sorted.filter(marker => marker.kind === "kit_path");
  const markers = sorted.filter(marker => marker.kind !== "kit_path");
  const top = sorted[0];
  return <main className="atlas-page atlas-group">
    <header className="flex flex-wrap items-center justify-between gap-3"><h1 className="atlas-title">{group.key} {group.label}</h1>
      <Link className="rounded-md bg-accent px-3 py-2 font-medium text-white" href={`/investigation?${operator ? "operator" : "campaign"}=${id}`}>Otwórz graf grupy</Link></header>
    <section><dl className="flex flex-wrap gap-x-8 gap-y-3">{metrics.map(([name,value]) => <div key={name}><dt className="text-muted">{name}</dt><dd className="text-2xl font-semibold">{value}</dd></div>)}</dl>
      {top && <p className="mt-3">Wspólny ślad: {top.label} · {markerValue(top.value, top.display_value)} ({top.in_group} z {group.size} reklam{top.bits != null && `, ${bits(top.bits)} bita`}).</p>}
    </section>
    <ObservationTimeline key={kind + id} id={Number(id)} operator={operator} />
    <section>
      <h2>Pary ze spraw wymagające oceny</h2>
      {pending.loading ? <Loading/> : pending.error ? <ErrorBox message={pending.error} onRetry={pending.reload}/> :
        !pending.data?.length ? <p>Brak par do oceny dla tej grupy.</p> :
          <details><summary>Pokaż pary ({pending.data.length})</summary>
            <ul>{pending.data.map(({ row, page }) => <li key={row.id} className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
              <span className="grow">#{row.ad_a.id} ↔ #{row.ad_b.id} · {row.reason_label}</span>
              <Link className="text-accent underline" href={`/review?page=${page}&edge=${row.id}&view=compare`}>Oceń parę</Link>
              <Link className="text-accent underline" href={`/investigation?${operator ? "operator" : "campaign"}=${id}&edge=${row.id}`}>Pokaż na grafie</Link>
            </li>)}</ul>
          </details>}
    </section>
    <section><h2>Markery rdzeniowe</h2>
      {markers.length ? <>
        <dl className="grid gap-3 md:hidden">{markers.map(marker => <div key={JSON.stringify([marker.kind, marker.value])} className="min-w-0 border-b border-line pb-3">
          <dt className="font-medium"><FamilyDot family={marker.family} /> {marker.label}</dt>
          <dd className="break-all font-mono">{markerValue(marker.value, marker.display_value)}</dd>
          <dd className="text-sm text-muted">Reklamy w grupie: {marker.in_group} · W korpusie: {marker.ad_count}</dd>
        </div>)}</dl>
        <table className="dense hidden md:table"><thead><tr><th>Marker</th><th>Wartość</th><th>Reklamy w grupie</th><th>W korpusie</th></tr></thead>
        <tbody>{markers.map(marker => <tr key={JSON.stringify([marker.kind, marker.value])}>
          <td><FamilyDot family={marker.family} /> {marker.label}</td><td className="break-all font-mono">{markerValue(marker.value, marker.display_value)}</td>
          <td>{marker.in_group}</td><td>{marker.ad_count}</td></tr>)}</tbody></table></> : !paths.length && <p>Brak markerów rdzeniowych.</p>}
      {!!paths.length && <details><summary>Ścieżki zaplecza ({paths.length})</summary><ul>{paths.map(m => <li key={m.value} className="break-all">{m.display_value || m.value} · w grupie {m.in_group}, w korpusie {m.ad_count}</li>)}</ul></details>}
    </section>
    {operator && <HuntProfile id={Number(id)}/>}
    {"campaigns" in group && Array.isArray(group.campaigns) && <section><h2>Kampanie operatora</h2>
      {group.campaigns.length ? <ul>{group.campaigns.map(key => <li key={key}><GroupLink group={key} /></li>)}</ul> : <p>Brak przypisanych kampanii.</p>}</section>}
    <section className="grid justify-items-start gap-2">
      <h2>Pakiet dowodowy</h2>
      {group.ads.length === 0 ? <p>Grupa nie ma reklam. Pakiet dowodowy jest niedostępny.</p> : <>
        <label><input type="checkbox" checked={includeRaw} onChange={e => setIncludeRaw(e.target.checked)} /> Dołącz surowe pliki HAR i HTML</label>
        {includeRaw && <p>Surowe pliki zawierają niezredagowaną treść ze stron oszustów.</p>}
        <a className="rounded-md border border-line-strong px-3 py-2 text-accent" href={(operator ? operatorPackageUrl : campaignPackageUrl)(Number(id), { raw: includeRaw })} download>Pobierz pakiet dowodowy (ZIP)</a>
        <p className="text-sm text-muted">Po rozpakowaniu sprawdź sumy plików poleceniem <code>python weryfikuj.py</code>. Skrót SHA-256 całego ZIP do osobnego porównania podaje API w nagłówku <code>X-Package-SHA256</code>.</p>
      </>}
    </section>
    <section><h2>Reklamy ({group.size})</h2><ul>{group.ads.map(ad =>
      <li key={ad.id}><Link className="text-accent" href={`/ads/${ad.id}`}>#{ad.id} · {adTitle(ad)}</Link></li>)}</ul></section>
  </main>;
}
