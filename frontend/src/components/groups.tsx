"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { api, artifactImageUrl, campaignPackageUrl, operatorPackageUrl } from "@/lib/api";
import { bits, dateTime, markerValue, adTitle, hostOf, lastSeenLabel, plural, SOURCE_LABELS } from "@/lib/format";
import { Expert, useExpert } from "@/lib/expert";
import { allGroups as loadGroups } from "@/lib/group-pages";
import { useApi } from "@/lib/hooks";
import { ObservationTimeline } from "./observation-timeline";
import { FoldSection, markerSentence, period } from "./simple";
import { ErrorBox, FamilyDot, GroupLink, Loading } from "./ui";

type GroupKind = "operators" | "campaigns";

const LIST_INTRO: Record<GroupKind, string> = {
  campaigns: "Kampania to reklamy jednej akcji: łączy je ta sama strona docelowa, zestaw stron albo te same materiały.",
  operators: "Operator to prawdopodobnie ten sam wykonawca kilku kampanii: wspólne zaplecze, konta albo identyfikatory.",
};

export function GroupList({ kind }: { kind: GroupKind }) {
  const params = useSearchParams();
  const { expert } = useExpert();
  const all = params.get("scope") === "all";
  const query = params.get("q") ?? "";
  const searchInput = useRef<HTMLInputElement>(null);
  useEffect(() => {
    const current = new URLSearchParams(window.location.search).get("q") ?? "";
    if (searchInput.current && searchInput.current.value !== current) searchInput.current.value = current;
  }, [query]);

  function updateFilter(key: "scope" | "q", value: string) {
    const url = new URL(window.location.href);
    if (value) url.searchParams.set(key, value);
    else url.searchParams.delete(key);
    window.history.replaceState(null, "", url);
  }
  const source = all ? undefined : "capture";
  const totals = useApi("group-totals", api.stats);
  const groups = useApi(kind + ":" + source, () => loadGroups(kind, source));
  const term = query.trim().toLocaleLowerCase("pl");
  const matches = (groups.data?.results ?? []).filter(group =>
    !term || group.key.toLowerCase().includes(term) || group.label.toLocaleLowerCase("pl").includes(term)
  );
  const sources = (group: (typeof matches)[number]) =>
    Object.entries(group.sources ?? {}).map(([key, count]) => `${SOURCE_LABELS[key] ?? key}: ${count}`).join(" · ") || "Brak danych";
  return <main className="atlas-page">
    <header className="grid gap-2">
      <h1 className="atlas-title">{kind === "operators" ? "Operatorzy" : "Kampanie"}</h1>
      <p className="max-w-3xl text-pretty text-muted">{LIST_INTRO[kind]}</p>
    </header>
    <div className="flex flex-wrap items-end gap-x-6 gap-y-3">
      <label className="grid w-full max-w-sm gap-1">Szukaj po identyfikatorze lub nazwie
        <input type="search" className="rounded-md border border-line bg-panel px-3 py-2" ref={searchInput} defaultValue={query} onChange={e => updateFilter("q", e.target.value)} />
      </label>
      <label className="flex items-center gap-2 py-2"><input type="checkbox" checked={all} onChange={e => updateFilter("scope", e.target.checked ? "all" : "")} />Wszystkie grupy, także z bibliotek reklam</label>
    </div>
    <p className="text-muted">{groups.data && totals.data && `Pokazano ${matches.length} z ${totals.data[kind]} grup · `}{all ? "wszystkie źródła" : "tylko sprawy"}</p>
    {groups.loading ? <Loading /> : groups.error ? <ErrorBox message={groups.error} onRetry={groups.reload} /> : matches.length ? expert ? <div className="atlas-table">
      <table className="dense"><thead><tr><th>Grupa</th><th>Nazwa</th><th>Reklamy</th><th>Źródła reklam</th><th>Sprawy</th><th>Reklamy z domeną na liście CERT</th></tr></thead>
        <tbody>{matches.map(group => <tr key={group.id}>
          <td><Link className="text-accent" href={`/${kind}/${group.id}`}>{group.key}</Link></td>
          <td>{group.label || <span className="text-faint">bez nazwy</span>}</td><td>{group.size}</td>
          <td>{sources(group)}</td><td>{group.cases ?? "—"}</td><td>{group.cert_pl ?? "—"}</td>
        </tr>)}</tbody></table></div> :
      <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">{matches.map(group => <li key={group.id}>
        <Link href={`/${kind}/${group.id}`} className="grid h-full gap-1 rounded-xl border border-line bg-panel p-4 transition hover:border-accent">
          <span className="font-semibold text-accent">{group.label || group.key}</span>
          <span className="text-lg">{group.size} {plural(group.size, "reklama", "reklamy", "reklam")}</span>
          <span className="text-sm text-muted">{group.label ? `${group.key} · ` : ""}{sources(group)}{group.cert_pl ? ` · ${group.cert_pl} na liście CERT` : ""}</span>
        </Link>
      </li>)}</ul> : <p>{term ? "Brak grup pasujących do wyszukiwania." : all ? "Brak grup w bazie. Dodaj materiał albo zaimportuj paczkę." : "Brak grup ze spraw. Zaznacz „Wszystkie grupy”, żeby zobaczyć grupy z bibliotek reklam."}</p>}
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
  const { expert } = useExpert();
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
  const domains = new Set(group.ads.map(ad => hostOf(ad.landing_url)).filter(Boolean)).size;
  const campaigns = new Set(group.ads.map(ad => ad.campaign).filter(Boolean)).size;
  const cases = new Set(group.ads.map(ad => ad.case).filter(Boolean)).size;
  const cert = new Set(group.ads.map(ad => ad.labels.cert_pl?.domain).filter(Boolean)).size;
  const metrics = [
    ["Reklamy", group.size],
    ["Kampanie", campaigns],
    ["Domeny", domains],
    ["Sprawy", cases],
    ["Domeny na liście CERT", cert],
  ] as const;
  const sorted = [...group.core_markers].sort((a,b) => (b.bits ?? -1) - (a.bits ?? -1) || Number(b.decisive) - Number(a.decisive) || b.in_group - a.in_group || a.ad_count - b.ad_count);
  const paths = sorted.filter(marker => marker.kind === "kit_path");
  const markers = sorted.filter(marker => marker.kind !== "kit_path");
  const strongest = sorted.filter(marker => marker.bits != null).slice(0, 3);
  const representative = group.ads.find(ad => ad.title?.trim());
  const name = group.label.trim() || (representative ? adTitle(representative) : operator ? "Operator" : "Kampania");
  const latest = group.ads.filter(ad => ad.last_seen).sort((a,b) => Date.parse(b.last_seen!) - Date.parse(a.last_seen!))[0];
  const packageUrl = (operator ? operatorPackageUrl : campaignPackageUrl)(Number(id), { raw: includeRaw });
  const seen = period(group.ads);
  const summary = [
    `${group.size} ${plural(group.size, "reklama", "reklamy", "reklam")}`,
    operator && campaigns > 0 && `${campaigns} ${plural(campaigns, "kampania", "kampanie", "kampanii")}`,
    domains > 0 && `${domains} ${plural(domains, "domena", "domeny", "domen")}`,
    cases > 0 && `${cases} ${plural(cases, "sprawa", "sprawy", "spraw")}`,
  ].filter(Boolean).join(", ");
  return <main className="atlas-page atlas-group">
    <header className="flex flex-wrap items-center justify-between gap-3"><div className="min-w-0 grow basis-72">
      <p className="text-sm text-muted">{expert
        ? <>{group.key}{!group.label && representative && " · nazwa robocza według tytułu reklamy"}</>
        : <>{operator ? "Operator" : "Kampania"} {group.key}{!group.label && representative && " · nazwa robocza z tytułu reklamy"}</>}</p>
      <h1 className="atlas-title text-pretty">{name}</h1></div>
      {group.ads.length > 0 && <a className="rounded-md border border-line-strong px-3 py-2 text-accent" href={packageUrl} download>Pobierz pakiet (ZIP)</a>}
      <Link className="rounded-md bg-accent px-3 py-2 font-medium text-white" href={`/investigation?${operator ? "operator" : "campaign"}=${id}`}>Otwórz graf grupy</Link></header>
    <Expert fallback={<section className="grid gap-1">
      <p className="text-lg text-pretty"><strong>{summary}</strong>{seen && <>, widziane {seen.includes(" do ") ? `od ${seen}` : seen}</>}.</p>
      {cert > 0 && <p className="text-muted">{cert} {plural(cert, "domena jest", "domeny są", "domen jest")} na liście ostrzeżeń CERT Polska.</p>}
      {latest && <p className="text-sm text-muted">Ostatnio: <Link href={`/ads/${latest.id}`} className="text-accent underline">{adTitle(latest)}</Link></p>}
    </section>}>
      <section><dl className="flex flex-wrap gap-x-8 gap-y-3">{metrics.map(([name,value]) => <div key={name}><dt className="text-muted">{name}</dt><dd className="text-2xl font-semibold">{value}</dd></div>)}</dl>
        {latest?.last_seen && <p className="mt-2 text-sm text-muted">{lastSeenLabel(latest.source)} · reklama <Link href={`/ads/${latest.id}`} className="text-accent underline">#{latest.id}</Link> · {dateTime(latest.last_seen)}</p>}
      </section>
    </Expert>
    <section><h2>Dlaczego razem</h2>
      {strongest.length ? <ol className="grid gap-3 md:grid-cols-3">{strongest.map(marker => <li key={JSON.stringify([marker.kind, marker.value])} className="min-w-0">
        <Expert fallback={<>
          <strong className="text-pretty"><FamilyDot family={marker.family} /> {marker.label}</strong>
          <p className="text-pretty text-muted">{markerSentence(marker, group.size)}.</p>
        </>}>
          <strong>{bits(marker.bits!)} bita</strong> · {marker.label}
          <p className="line-clamp-2 break-all font-mono text-sm" title={markerValue(marker.value, marker.display_value)}>{markerValue(marker.value, marker.display_value)}</p>
          <p className="text-sm text-muted">Powiązania: {marker.edges} · Reklamy: {marker.in_group} z {group.size}</p>
        </Expert>
      </li>)}</ol> : <p>Brak śladów z wyliczonym wkładem w powiązania.</p>}
    </section>
    <section><h2>Materiały grupy</h2>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-[repeat(auto-fill,minmax(8.5rem,1fr))]">{group.ads.map(ad => <Link key={ad.id} href={`/ads/${ad.id}`} className="group/ad grid min-w-0 content-start gap-1" title={adTitle(ad)}>
        {ad.thumbnail ? (
          // eslint-disable-next-line @next/next/no-img-element -- Obrazy pochodzą z serwera artefaktów demo.
          <img src={artifactImageUrl(ad.thumbnail.sha256)} alt={`Podgląd reklamy #${ad.id}`} loading="lazy" className="aspect-[4/3] w-full rounded-md border border-line bg-panel object-contain transition group-hover/ad:border-accent" />
        ) : <span className="grid aspect-[4/3] place-items-center overflow-hidden rounded-md border border-line bg-panel px-2 text-sm leading-tight text-muted transition group-hover/ad:border-accent" title="Brak zrzutu w materiale, pokazujemy tytuł"><span className="line-clamp-4 break-words">{adTitle(ad)}</span></span>}
        <span className="truncate text-sm text-accent">#{ad.id}{!expert && <span className="text-muted"> · {hostOf(ad.landing_url) || adTitle(ad)}</span>}</span>
      </Link>)}</div>
    </section>
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
    {"campaigns" in group && Array.isArray(group.campaigns) && <section><h2>Kampanie operatora</h2>
      {group.campaigns.length ? <ul>{group.campaigns.map(key => <li key={key}><GroupLink group={key} /></li>)}</ul> : <p>Brak przypisanych kampanii.</p>}</section>}
    <FoldSection title="Oś obserwacji"><ObservationTimeline key={kind + id} id={Number(id)} operator={operator} bare /></FoldSection>
    <FoldSection title={expert ? "Markery rdzeniowe" : `Wszystkie wspólne ślady (${markers.length + paths.length})`}>
      {markers.length ? <>
        <dl className="grid gap-3 md:hidden">{markers.map(marker => <div key={JSON.stringify([marker.kind, marker.value])} className="min-w-0 border-b border-line pb-3">
          <dt className="font-medium"><FamilyDot family={marker.family} /> {marker.label}</dt>
          <dd className="break-all font-mono">{markerValue(marker.value, marker.display_value)}</dd>
          <dd className="text-sm text-muted">Bity: {marker.bits == null ? "—" : bits(marker.bits)} · Powiązania: {marker.edges} · Reklamy w grupie: {marker.in_group} · W korpusie: {marker.ad_count}</dd>
        </div>)}</dl>
        <table className="dense hidden md:table"><thead><tr><th>Marker</th><th>Wartość</th><th>Bity</th><th>Powiązania</th><th className="whitespace-normal!">Reklamy w grupie</th><th>W korpusie</th></tr></thead>
        <tbody>{markers.map(marker => <tr key={JSON.stringify([marker.kind, marker.value])}>
          <td className="whitespace-normal!"><FamilyDot family={marker.family} /> {marker.label}</td><td className="whitespace-normal! break-all font-mono">{markerValue(marker.value, marker.display_value)}</td>
          <td>{marker.bits == null ? "—" : bits(marker.bits)}</td><td>{marker.edges}</td><td>{marker.in_group}</td><td>{marker.ad_count}</td></tr>)}</tbody></table></> : !paths.length && <p>Brak markerów rdzeniowych.</p>}
      {!!paths.length && <details><summary>Ścieżki zaplecza ({paths.length})</summary><ul>{paths.map(m => <li key={m.value} className="break-all">{m.display_value || m.value} · bity: {m.bits == null ? "—" : bits(m.bits)} · powiązania: {m.edges} · w grupie {m.in_group}, w korpusie {m.ad_count}</li>)}</ul></details>}
      {operator && <HuntProfile id={Number(id)}/>}
    </FoldSection>
    <section className="grid justify-items-start gap-2">
      <h2>Pakiet dowodowy</h2>
      {group.ads.length === 0 ? <p>Grupa nie ma reklam. Pakiet dowodowy jest niedostępny.</p> : <>
        {!expert && <p className="text-muted">ZIP z materiałami, śladami i opisem powiązań, gotowy do przekazania dalej.</p>}
        <label><input type="checkbox" checked={includeRaw} onChange={e => setIncludeRaw(e.target.checked)} /> Dołącz surowe pliki HAR i HTML</label>
        {includeRaw && <p>Surowe pliki zawierają niezredagowaną treść ze stron oszustów.</p>}
        <a className="rounded-md border border-line-strong px-3 py-2 text-accent" href={packageUrl} download>Pobierz pakiet dowodowy (ZIP)</a>
        <Expert><p className="text-sm text-muted">Po rozpakowaniu sprawdź sumy plików poleceniem <code>python weryfikuj.py</code>. Skrót SHA-256 całego ZIP do osobnego porównania podaje API w nagłówku <code>X-Package-SHA256</code>.</p></Expert>
      </>}
    </section>
    <FoldSection title={`Reklamy (${group.size})`}><ul>{group.ads.map(ad =>
      <li key={ad.id}><Link className="text-accent" href={`/ads/${ad.id}`}>#{ad.id} · {adTitle(ad)}</Link></li>)}</ul></FoldSection>
  </main>;
}
