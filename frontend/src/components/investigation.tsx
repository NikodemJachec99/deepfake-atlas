"use client";

// Tryb Investigation: graf z GET /api/graph, filtry, inspektor (panel dowodów albo karta reklamy), tabela krawędzi.

import Link from "next/link";
import { CampaignTree } from "./campaign-tree";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";

import { FAMILY_LABELS, RELATION_LABELS, api, type Family, type Graph, type Relation } from "@/lib/api";
import { allGroups as loadGroups } from "@/lib/group-pages";
import { FAMILIES, RELATIONS, RELATION_HINT, bits, groupId, plural, prob } from "@/lib/format";
import { useExpert } from "@/lib/expert";
import { isTyping, useApi, useHotkey } from "@/lib/hooks";

import { AdCard } from "./ad-card";
import { EdgePanel, EdgePanelEmpty } from "./edge-panel";
import { GraphCanvas, type GEdge } from "./graph-canvas";
import { Fold } from "./simple";
import { TopBar, type Crumb } from "./shell";
import { Btn, Empty, ErrorBox, FamilyBar, FamilyDot, GroupLink, Loading, Meter, Mono, Panel, RelationLine, RelationTag, Split, Tabs, Tag, VerdictTag } from "./ui";

export function useQuery() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const set = (patch: Record<string, string | number | null | undefined>, replaceAll = false) => {
    const next = new URLSearchParams(replaceAll ? "" : params.toString());
    for (const [key, value] of Object.entries(patch)) {
      if (value === null || value === undefined || value === "") next.delete(key);
      else next.set(key, String(value));
    }
    const query = next.toString();
    router.push(query ? `${pathname}?${query}` : pathname, { scroll: false });
  };
  const int = (key: string) => {
    const value = Number.parseInt(params.get(key) ?? "", 10);
    return Number.isFinite(value) ? value : null;
  };
  return { params, set, int };
}

function Check({ checked, onChange, children, title }: { checked: boolean; onChange: (checked: boolean) => void; children: React.ReactNode; title?: string }) {
  return (
    <label className="flex h-6 cursor-pointer items-center gap-2 px-2 hover:bg-hover" title={title}>
      <input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} className="accent-(--accent)" />
      {children}
    </label>
  );
}

function toggle<T>(set: Set<T>, value: T, on: boolean): Set<T> {
  const next = new Set(set);
  if (on) next.add(value);
  else next.delete(value);
  return next;
}

/** Filtry dla specjalisty: w trybie prostym zwinięte pod „Więcej filtrów”. */
function FiltersMore({ expert, children }: { expert: boolean; children: React.ReactNode }) {
  if (expert) return <>{children}</>;
  return <div className="px-2"><Fold title="Więcej filtrów"><div className="-mx-2 flex flex-col gap-3">{children}</div></Fold></div>;
}

export function Investigation() {
  const { params, set, int } = useQuery();
  const { expert } = useExpert();
  const [mobileView, setMobileView] = useState<string | null>(null);
  const [mobileFilters, setMobileFilters] = useState(false);
  const operatorId = int("operator");
  const campaignId = int("campaign");
  const adId = int("ad");
  const all = params.get("scope") === "all";
  const edgeId = int("edge");
  const nodeId = int("node");

  const overview = !all && [operatorId, campaignId, adId, edgeId, nodeId].every(id => id === null);
  const operators = useApi(overview ? null : "operators", () => loadGroups("operators"));
  const allGroups = params.get("groups") === "all";
  const expanded = new Set((params.get("expanded") ?? "").split(",").map(Number).filter(id => Number.isSafeInteger(id) && id > 0));
  function toggleCampaign(id: number) {
    const next = toggle(expanded, id, !expanded.has(id));
    set({ expanded: [...next].join(",") });
  }
  const captureOnly = overview && !allGroups;
  const overviewOperators = useApi(overview ? "operators:" + captureOnly : null, () => loadGroups("operators", captureOnly ? "capture" : undefined));
  const campaigns = useApi("campaigns:" + captureOnly, () => loadGroups("campaigns", captureOnly ? "capture" : undefined));
  const scopeOperator = operatorId;
  const query = campaignId !== null ? `?campaign=${campaignId}` : scopeOperator !== null ? `?operator=${scopeOperator}` : adId !== null ? `?ad=${adId}` : "";
  const graph = useApi<Graph>(overview ? null : `graph:${query}`, () => api.graph(query));

  const [relations, setRelations] = useState<Set<Relation>>(new Set(RELATIONS));
  const [families, setFamilies] = useState<Set<Family>>(new Set(FAMILIES));
  const [minP, setMinP] = useState(0);
  const [colorBy, setColorBy] = useState<"operator" | "campaign">("campaign");
  const [table, setTable] = useState<"edges" | "ads">("edges");

  const nodes = useMemo(() => graph.data?.nodes ?? [], [graph.data]);
  const edges = useMemo<(GEdge & Graph["edges"][number])[]>(
    () =>
      (graph.data?.edges ?? []).map((edge) => ({
        ...edge,
        hidden: !relations.has(edge.relation) || edge.probability < minP || !FAMILIES.some((f) => families.has(f) && (edge.families[f] ?? 0) > 0),
      })),
    [graph.data, relations, families, minP],
  );
  const filtersChanged = relations.size !== RELATIONS.length || families.size !== FAMILIES.length || minP !== 0;
  const resetFilters = filtersChanged && (
    <button type="button" className="text-accent underline" onClick={() => {
      setRelations(new Set(RELATIONS));
      setFamilies(new Set(FAMILIES));
      setMinP(0);
    }}>Przywróć domyślne filtry</button>
  );
  const visible = edges.filter((e) => !e.hidden);
  const scoped = campaignId !== null || operatorId !== null;
  const belongs = (n: (typeof nodes)[number]) => n.member ?? (campaignId !== null ? groupId(n.campaign) === campaignId : groupId(n.operator) === operatorId);
  const sections: [string, typeof nodes][] = scoped ? [["Członkowie grupy", nodes.filter(belongs)], ["Sąsiedzi spoza grupy", nodes.filter(n => !belongs(n))]] : [["", nodes]];
  const nodeById = useMemo(() => new Map(nodes.map((n) => [n.id, n])), [nodes]);
  const selectedNode = nodeId !== null ? nodeById.get(nodeId) : undefined;

  const operatorKey = operators.data?.results.find((g) => g.id === scopeOperator)?.key;
  const campaignKey = campaigns.data?.results.find((g) => g.id === campaignId)?.key;
  const campaignOperator = campaignKey ? nodes.find((n) => n.campaign === campaignKey)?.operator : undefined;

  const crumbs: Crumb[] = [{ label: "Śledztwo", href: "/investigation" }];
  if (campaignId !== null) {
    if (campaignOperator) crumbs.push({ label: <Mono>{campaignOperator}</Mono>, href: `/investigation?operator=${groupId(campaignOperator)}` });
    crumbs.push({ label: <Mono>{campaignKey ?? `kampania ${campaignId}`}</Mono> });
  } else if (scopeOperator !== null) crumbs.push({ label: <Mono>{operatorKey ?? `operator ${scopeOperator}`}</Mono> });
  else if (adId !== null) crumbs.push({ label: `sąsiedztwo reklamy #${adId}` });
  else crumbs.push({ label: "cały graf" });
  if (selectedNode) {
    if (selectedNode.campaign && campaignId === null) crumbs.push({ label: <Mono>{selectedNode.campaign}</Mono>, href: `/investigation?campaign=${groupId(selectedNode.campaign)}` });
    crumbs.push({ label: `reklama #${selectedNode.id}` });
  }

  const scopeValue = campaignId !== null ? `c:${campaignId}` : scopeOperator !== null ? `o:${scopeOperator}` : adId !== null ? `a:${adId}` : "all";
  function changeScope(value: string) {
    const [kind, id] = value.split(":");
    if (kind === "o") set({ operator: id }, true);
    else if (kind === "c") set({ campaign: id }, true);
    else set({ scope: "all" }, true);
  }

  useHotkey((event) => {
    if (event.key === "Escape" && !isTyping(event) && (edgeId !== null || nodeId !== null)) set({ edge: null, node: null });
  });

  if (overview) return <main className="flex min-h-full flex-col gap-3 p-4">
    <header className="flex flex-wrap items-center justify-between gap-3">
      <div className="grid gap-1">
        <h1 className="atlas-title">Śledztwo</h1>
        <p className="max-w-3xl text-pretty text-muted">Wybierz operatora albo kampanię: zobaczysz jej reklamy, powiązania między nimi i dowody każdego powiązania. Graf pokazuje to samo jako sieć.</p>
      </div>
      <Link href="/investigation?scope=all" className="rounded-md border border-line-strong px-3 py-2 text-accent hover:bg-panel">Cały graf</Link>
    </header>
    <label><input type="checkbox" checked={allGroups} onChange={event => set({ groups: event.target.checked ? "all" : null })} /> Wszystkie grupy (również z bibliotek reklam)</label>
    {!expert && !!overviewOperators.data?.results.length && <section aria-label="Operatorzy" className="grid gap-2">
      <h2 className="text-lg font-semibold">Operatorzy{captureOnly && " ze spraw"}</h2>
      <ul className="flex flex-wrap gap-2">{overviewOperators.data.results.slice(0, 24).map(group => <li key={group.id}>
        <Link href={`/investigation?operator=${group.id}`} className="grid rounded-lg border border-line bg-panel px-3 py-2 hover:border-accent">
          <span className="font-semibold text-accent">{group.label || group.key}</span>
          <span className="text-sm text-muted">{group.size} {plural(group.size, "reklama", "reklamy", "reklam")}</span>
        </Link></li>)}</ul>
      {overviewOperators.data.results.length > 24 && <Link href="/operators?scope=all" className="text-accent underline">Wszyscy operatorzy ({overviewOperators.data.results.length})</Link>}
      <h2 className="mt-2 text-lg font-semibold">Kampanie{captureOnly && " ze spraw"}</h2>
    </section>}
    {campaigns.loading ? <Loading label="Pobieranie kampanii" /> : campaigns.error ?
      <ErrorBox message={campaigns.error} onRetry={campaigns.reload} /> : campaigns.data?.results.length ? <CampaignTree map={params.get("view") === "map"} onMapChange={map => set({ view: map ? "map" : null })}
      expanded={expanded} toggleCampaign={toggleCampaign} groups={[...campaigns.data.results].sort((a,b) => Number(b.cases > 0) - Number(a.cases > 0))} /> : <Empty title="Brak kampanii">Wszystkie dostępne reklamy znajdziesz w całym grafie.</Empty>}
  </main>;

  const filters = (
    <Panel title="Zakres i filtry" className="w-full">
      <div className="flex flex-col gap-3 py-2">
        <div className="flex flex-col gap-1 px-2">
          <label htmlFor="scope" className="cap">
            Zakres grafu
          </label>
          <select id="scope" value={scopeValue} onChange={(event) => changeScope(event.target.value)} className="h-6 w-full min-w-0 rounded-sm border border-line-strong bg-raised px-1">
            <option value="all">Cały graf</option>
            {adId !== null && <option value={`a:${adId}`}>Sąsiedztwo reklamy #{adId}</option>}
            <optgroup label="Operatorzy">
              {(operators.data?.results ?? []).map((g) => (
                <option key={g.id} value={`o:${g.id}`}>
                  {g.key} · {g.size} reklam
                </option>
              ))}
            </optgroup>
            <optgroup label="Kampanie">
              {(campaigns.data?.results ?? []).map((g) => (
                <option key={g.id} value={`c:${g.id}`}>
                  {g.key} · {g.size} reklam
                </option>
              ))}
            </optgroup>
          </select>
          {scoped && (
            <Link
              className="text-xs text-accent underline"
              href={campaignId !== null ? `/campaigns/${campaignId}` : `/operators/${scopeOperator}`}
            >
              {campaignId !== null ? `Karta kampanii ${campaignKey ?? "#" + campaignId}` : `Karta operatora ${operatorKey ?? "#" + scopeOperator}`}
            </Link>
          )}
        </div>

        <div>
          <p className="cap px-2 pb-1">Relacja</p>
          {RELATIONS.map((relation) => (
            <Check key={relation} checked={relations.has(relation)} onChange={(on) => setRelations(toggle(relations, relation, on))} title={RELATION_HINT[relation]}>
              <RelationLine relation={relation} />
              <span className="min-w-0 flex-1 truncate" title={RELATION_LABELS[relation]}>{RELATION_LABELS[relation]}</span>
              <Mono className="text-muted">{edges.filter((e) => e.relation === relation).length}</Mono>
            </Check>
          ))}
        </div>

        <FiltersMore expert={expert}>
        <div>
          <p className="cap px-2 pb-1">Rodziny markerów</p>
          {FAMILIES.map((family) => (
            <Check key={family} checked={families.has(family)} onChange={(on) => setFamilies(toggle(families, family, on))}>
              <FamilyDot family={family} />
              <span className="min-w-0 flex-1 truncate" title={FAMILY_LABELS[family]}>{FAMILY_LABELS[family]}</span>
              <Mono className="text-muted">{edges.filter((e) => (e.families[family] ?? 0) > 0).length}</Mono>
            </Check>
          ))}
          <p className="px-2 pt-1 text-xs text-faint">Krawędź zostaje, gdy wkład ma choć jedna zaznaczona rodzina. Kolor krawędzi to rodzina o największym wkładzie.</p>
        </div>

        <div className="flex flex-col gap-1 px-2">
          <label htmlFor="min-p" className="cap flex justify-between">
            Próg wyniku modelu (niekalibrowanego) <Mono className="text-fg normal-case">{prob(minP)}</Mono>
          </label>
          <input id="min-p" type="range" min={0} max={1} step={0.01} value={minP} onChange={(event) => setMinP(Number(event.target.value))} className="accent-(--accent)" />
          <div className="flex gap-1">
            {[0, 0.5, 0.9].map((value) => (
              <Btn key={value} active={minP === value} onClick={() => setMinP(value)} className="flex-1">
                {prob(value)}
              </Btn>
            ))}
          </div>
        </div>

        <div className="flex flex-col gap-1 px-2">
          <p className="cap">Kolor węzła</p>
          <div className="flex gap-1">
            <Btn active={colorBy === "campaign"} onClick={() => setColorBy("campaign")} className="flex-1">
              Kampania
            </Btn>
            <Btn active={colorBy === "operator"} onClick={() => setColorBy("operator")} className="flex-1">
              Operator
            </Btn>
          </div>
        </div>
        </FiltersMore>

        {resetFilters && <div className="px-2">{resetFilters}</div>}
        {scoped && <p className="border-t border-line px-2 pt-2 text-xs text-faint">
          Oś obserwacji grupy jest na jej karcie.
        </p>}
      </div>
    </Panel>
  );

  const canvas = graph.loading ? (
    <Loading label="Pobieranie grafu" />
  ) : graph.error ? (
    <ErrorBox message={graph.error} onRetry={graph.reload} />
  ) : nodes.length === 0 ? (
    <Empty title="Graf jest pusty">W tym zakresie nie ma reklam ani powiązań. Zmień zakres albo dodaj materiał w Analizie.</Empty>
  ) : (
    <GraphCanvas
      nodes={nodes}
      edges={edges}
      colorBy={colorBy}
      layout="force"
      selectedEdge={edgeId}
      selectedNode={nodeId}
      onEdge={(id) => { setMobileView("Porównanie"); set({ edge: id }); }}
      onNode={(id) => { setMobileView("Porównanie"); set({ node: id, edge: null }); }}
      onClear={() => set({ edge: null, node: null })}
    />
  );

  const bottom = (
    <div className="flex min-h-0 w-full flex-col bg-panel">
      <Tabs
        value={table}
        onChange={setTable}
        items={[
          { id: "edges", label: graph.data ? `Krawędzie · pokazano ${visible.length} z ${edges.length}` : "Krawędzie" },
          { id: "ads", label: `Reklamy ${nodes.length}` },
        ]}
      />
      {table === "edges" && graph.data?.truncated && <p className="border-b border-line px-3 py-1 text-sm text-muted">
        Pobrano {edges.length} z {graph.data.total} krawędzi w wybranym zakresie. Filtry działają na pobranej części.
      </p>}
      <div className="min-h-0 flex-1 overflow-auto">
        {table === "edges" && !expert ? (
          <table className="dense w-full">
            <thead><tr><th>Reklama</th><th>Powiązana z</th><th>Relacja</th><th>Decyzja</th></tr></thead>
            <tbody>
              {graph.data && !visible.length && <tr><td colSpan={4} className="text-muted">
                {edges.length ? "Brak powiązań spełniających kryteria filtrów." : "Brak powiązań w wybranym zakresie."}
                {edges.length > 0 && resetFilters && <> {resetFilters}</>}
              </td></tr>}
              {visible.map((edge) => (
                <tr key={edge.id} data-selected={edge.id === edgeId} onClick={() => { setMobileView("Porównanie"); set({ edge: edge.id }); }} className="cursor-pointer">
                  <td className="max-w-64 truncate">
                    <button type="button" className="table-action" aria-label={`Dowody powiązania reklam #${edge.source} i #${edge.target}`}>#{edge.source}</button>{" "}
                    <span className="text-muted" title={nodeById.get(edge.source)?.label}>{nodeById.get(edge.source)?.label}</span>
                  </td>
                  <td className="max-w-64 truncate"><Mono className="text-muted">#{edge.target}</Mono> <span className="text-muted" title={nodeById.get(edge.target)?.label}>{nodeById.get(edge.target)?.label}</span></td>
                  <td><RelationTag relation={edge.relation} duplicate={edge.duplicate} /></td>
                  <td>{edge.verdict ? <VerdictTag verdict={edge.verdict} /> : <span className="text-faint">do oceny</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : table === "edges" ? (
          <table className="dense min-w-max">
            <thead>
              <tr>
                <th>A</th>
                <th>B</th>
                <th>Relacja</th>
                <th>Wynik modelu (niekalibrowany)</th>
                <th className="text-right">Bity</th>
                <th className="w-40">Rodziny</th>
                <th>Decyzja</th>
              </tr>
            </thead>
            <tbody>
              {graph.data && !visible.length && <tr><td colSpan={7} className="text-muted">
                {edges.length ? "Brak powiązań spełniających kryteria filtrów." : "Brak powiązań w wybranym zakresie."}
                {edges.length > 0 && resetFilters && <> {resetFilters}</>}
              </td></tr>}
              {visible.map((edge) => (
                <tr key={edge.id} data-selected={edge.id === edgeId} onClick={() => { setMobileView("Porównanie"); set({ edge: edge.id }); }} className="cursor-pointer">
                  <td className="max-w-56">
                    <button type="button" className="table-action" aria-label={`Dowody powiązania reklam #${edge.source} i #${edge.target}`}>
                      #{edge.source}
                    </button> {nodeById.get(edge.source)?.case && <span className="text-muted">spr. {nodeById.get(edge.source)?.case}</span>}
                  </td>
                  <td className="max-w-56">
                    <Mono className="text-muted">#{edge.target}</Mono> {nodeById.get(edge.target)?.case && <span className="text-muted">spr. {nodeById.get(edge.target)?.case}</span>}
                  </td>
                  <td>
                    <RelationTag relation={edge.relation} duplicate={edge.duplicate} />
                  </td>
                  <td>
                    <Meter value={edge.probability} width={56} />
                  </td>
                  <td className="text-right font-mono text-[0.92rem]">{bits(edge.bits)}</td>
                  <td>
                    <FamilyBar families={edge.families} height={6} />
                  </td>
                  <td>
                    <VerdictTag verdict={edge.verdict} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <table className="dense">
            <thead>
              <tr>
                <th>{expert ? "ID" : "Reklama"}</th>
                {expert && <th>Sprawa</th>}
                <th>Tytuł</th>
                <th>Kampania</th>
                {expert && <th>Operator</th>}
                <th>CERT</th>
              </tr>
            </thead>
            <tbody>
              {sections.flatMap(([heading, rows]) => [
                ...(heading ? [<tr key={heading}><th scope="rowgroup" colSpan={expert ? 6 : 4}>{heading} ({rows.length})</th></tr>] : []),
                ...rows.map((node) => (
                <tr key={node.id} data-selected={node.id === nodeId} onClick={event => {
                  if (!(event.target instanceof Element && event.target.closest("a"))) { setMobileView("Porównanie"); set({ node: node.id, edge: null }); }
                }} className="cursor-pointer">
                  <td><button type="button" className="table-action" aria-label={`Otwórz reklamę #${node.id}`}>#{node.id}</button></td>
                  {expert && <td className="font-mono text-[0.92rem]">{node.case ?? ""}</td>}
                  <td className="max-w-0 w-full">{node.label}</td>
                  <td>
                    <GroupLink group={node.campaign} />
                  </td>
                  {expert && <td>
                    <GroupLink group={node.operator} />
                  </td>}
                  <td>{node.listed && <Tag tone="rejected">Lista Ostrzeżeń</Tag>}</td>
                </tr>
               ))])}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );

  const inspector = (
    <Panel
      title={edgeId !== null ? "Dowody krawędzi" : nodeId !== null ? "Karta reklamy" : "Inspektor"}
      className="w-full"
      bodyClassName={edgeId !== null ? "overflow-hidden!" : undefined}
      actions={
        <>
          {edgeId !== null && nodeId !== null && (
            <Btn variant="ghost" onClick={() => set({ edge: null })}>
              Wróć do reklamy #{nodeId}
            </Btn>
          )}
          {(edgeId !== null || nodeId !== null) && (
            <Btn variant="ghost" onClick={() => set({ edge: null, node: null })} title="Esc">
              Zamknij
            </Btn>
          )}
        </>
      }
    >
      {edgeId !== null ? (
        <EdgePanel key={edgeId} edgeId={edgeId} onOpenAd={(id) => set({ node: id, edge: null })} onVerdict={graph.reload} />
      ) : nodeId !== null ? (
        <AdCard key={nodeId} adId={nodeId} selectedEdge={edgeId} onEdge={(edge) => set({ edge: edge.id })} />
      ) : (
        <EdgePanelEmpty />
      )}
    </Panel>
  );

  const mode = mobileView === "Porównanie" && edgeId === null && nodeId === null ? "Lista" : mobileView ?? (edgeId !== null || nodeId !== null ? "Porównanie" : "Lista");
  const graphAndTable = (
    <Split id="inv-table" dir="col" fixed="second" initial={236} min={90} max={560}>
            <div className="flex min-h-0 min-w-0 flex-1">{canvas}</div>
            {bottom}
          </Split>
  );

  return (
    <>
      <TopBar crumbs={crumbs} />
      <nav aria-label="Widok śledztwa" className="flex gap-2 px-3 min-[1000px]:hidden">{["Lista", "Porównanie", "Graf"].map(view => <button key={view} disabled={view === "Porównanie" && edgeId === null && nodeId === null} aria-pressed={view === mode} onClick={() => setMobileView(view)} className="rounded px-2 aria-pressed:bg-accent-soft disabled:opacity-50">{view}</button>)}</nav>
      <div className="atlas-investigation" data-mode={mode}><Split id="inv-filters" dir="row" fixed="first" initial={242} min={208} max={360}>
        <div className="flex h-full min-h-0 w-full min-w-0 flex-col">
          <button type="button" className="self-start px-3 py-2 text-accent md:hidden" aria-expanded={mobileFilters} aria-controls="investigation-filters" onClick={() => setMobileFilters(!mobileFilters)}>{mobileFilters ? "Zwiń filtry" : "Zakres i filtry"}</button>
          <div id="investigation-filters" className={`min-h-0 overflow-auto md:block ${mobileFilters ? "block" : "hidden"}`}>{filters}</div>
        </div>
        {edgeId === null && nodeId === null ? graphAndTable : <Split id="inv-inspector" dir="row" fixed="second" initial={560} min={280} max={820}>
          {graphAndTable}
          {inspector}
        </Split>}
      </Split></div>
    </>
  );
}
