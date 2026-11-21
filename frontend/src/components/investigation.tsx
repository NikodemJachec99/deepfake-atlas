"use client";

// Tryb Investigation: graf z GET /api/graph, filtry, inspektor (panel dowodów albo karta reklamy), tabela krawędzi.

import Link from "next/link";
import { CampaignTree } from "./campaign-tree";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";

import { FAMILY_LABELS, RELATION_LABELS, api, type Family, type Graph, type Relation } from "@/lib/api";
import { FAMILIES, RELATIONS, RELATION_HINT, bits, groupId, prob } from "@/lib/format";
import { isTyping, useApi, useHotkey } from "@/lib/hooks";

import { AdCard } from "./ad-card";
import { EdgePanel, EdgePanelEmpty } from "./edge-panel";
import { GraphCanvas, type GEdge } from "./graph-canvas";
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
    router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false });
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

export function Investigation() {
  const { params, set, int } = useQuery();
  const operatorId = int("operator");
  const campaignId = int("campaign");
  const adId = int("ad");
  const all = params.get("scope") === "all";
  const edgeId = int("edge");
  const nodeId = int("node");

  const overview = !all && [operatorId, campaignId, adId, edgeId, nodeId].every(id => id === null);
  const operators = useApi(overview ? null : "operators", api.operators);
  const [allGroups, setAllGroups] = useState(false);
  const captureOnly = overview && !allGroups;
  const campaigns = useApi("campaigns:" + captureOnly, () => api.campaigns(captureOnly ? "capture" : undefined));
  const stats = useApi(all ? "graph-stats" : null, api.stats);
  const totalEdges = stats.data ? Object.values(stats.data.edges).reduce((sum, n) => sum + n, 0) : null;
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
  const visible = edges.filter((e) => !e.hidden);
  const nodeById = useMemo(() => new Map(nodes.map((n) => [n.id, n])), [nodes]);
  const selectedNode = nodeId !== null ? nodeById.get(nodeId) : undefined;

  const operatorKey = operators.data?.results.find((g) => g.id === scopeOperator)?.key;
  const campaignKey = campaigns.data?.results.find((g) => g.id === campaignId)?.key;
  const campaignOperator = campaignKey ? nodes.find((n) => n.campaign === campaignKey)?.operator : undefined;

  const crumbs: Crumb[] = [{ label: "Kampanie", href: "/investigation" }];
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
      <h1 className="atlas-title">Kampanie</h1>
      <Link href="/investigation?scope=all" className="rounded-md border border-line-strong px-3 py-2 text-accent hover:bg-panel">Cały graf</Link>
    </header>
    <label><input type="checkbox" checked={allGroups} onChange={event => setAllGroups(event.target.checked)} /> Wszystkie grupy (również z bibliotek reklam)</label>
    {campaigns.loading ? <Loading label="Pobieranie kampanii" /> : campaigns.error ?
      <ErrorBox message={campaigns.error} onRetry={campaigns.reload} /> : campaigns.data?.results.length ? <CampaignTree groups={[...campaigns.data.results].sort((a,b) => Number(b.cases > 0) - Number(a.cases > 0))} /> : <Empty title="Brak kampanii">Wszystkie dostępne reklamy znajdziesz w całym grafie.</Empty>}
  </main>;

  const filters = (
    <Panel title="Zakres i filtry" className="w-full">
      <div className="flex flex-col gap-3 py-2">
        <div className="flex flex-col gap-1 px-2">
          <label htmlFor="scope" className="cap">
            Zakres grafu
          </label>
          <select id="scope" value={scopeValue} onChange={(event) => changeScope(event.target.value)} className="h-6 rounded-sm border border-line-strong bg-raised px-1">
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
          {scopeOperator !== null && campaignId === null && (
            <span className="text-[0.85rem] text-muted">
              Karta operatora: <GroupLink group={operatorKey} />
            </span>
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

        <div>
          <p className="cap px-2 pb-1">Rodziny markerów</p>
          {FAMILIES.map((family) => (
            <Check key={family} checked={families.has(family)} onChange={(on) => setFamilies(toggle(families, family, on))}>
              <FamilyDot family={family} />
              <span className="min-w-0 flex-1 truncate" title={FAMILY_LABELS[family]}>{FAMILY_LABELS[family]}</span>
              <Mono className="text-muted">{edges.filter((e) => (e.families[family] ?? 0) > 0).length}</Mono>
            </Check>
          ))}
          <p className="px-2 pt-1 text-[0.85rem] text-faint">Krawędź zostaje, gdy wkład ma choć jedna zaznaczona rodzina. Kolor krawędzi to rodzina o największym wkładzie.</p>
        </div>

        <div className="flex flex-col gap-1 px-2">
          <label htmlFor="min-p" className="cap flex justify-between">
            Próg pewności <Mono className="text-fg normal-case">{prob(minP)}</Mono>
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

        <p className="border-t border-line px-2 pt-2 text-[0.85rem] text-faint">
          Zakres dat, pivot po markerze i minimapa czekają na API osi czasu i wyszukiwania po markerach.
        </p>
      </div>
    </Panel>
  );

  const canvas = graph.loading ? (
    <Loading label="Pobieranie grafu" />
  ) : graph.error ? (
    <ErrorBox message={graph.error} onRetry={graph.reload} />
  ) : nodes.length === 0 ? (
    <Empty title="Graf jest pusty">W tym zakresie nie ma reklam ani powiązań. Zmień zakres albo wrzuć materiał w trybie Discovery.</Empty>
  ) : (
    <GraphCanvas
      nodes={nodes}
      edges={edges}
      colorBy={colorBy}
      layout="force"
      selectedEdge={edgeId}
      selectedNode={nodeId}
      onEdge={(id) => set({ edge: id })}
      onNode={(id) => set({ node: id, edge: null })}
      onClear={() => set({ edge: null, node: null })}
    />
  );

  const bottom = (
    <div className="flex min-h-0 w-full flex-col bg-panel">
      <Tabs
        value={table}
        onChange={setTable}
        items={[
          { id: "edges", label: `Krawędzie · pokazano ${visible.length} z ${totalEdges ?? edges.length}` },
          { id: "ads", label: `Reklamy ${nodes.length}` },
        ]}
      />
      <div className="min-h-0 flex-1 overflow-auto">
        {table === "edges" ? (
          <table className="dense min-w-max">
            <thead>
              <tr>
                <th>A</th>
                <th>B</th>
                <th>Relacja</th>
                <th>Pewność</th>
                <th className="text-right">Bity</th>
                <th className="w-40">Rodziny</th>
                <th>Decyzja</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((edge) => (
                <tr key={edge.id} data-selected={edge.id === edgeId} onClick={() => set({ edge: edge.id })} className="cursor-pointer">
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
                <th>ID</th>
                <th>Sprawa</th>
                <th>Tytuł</th>
                <th>Kampania</th>
                <th>Operator</th>
                <th>CERT</th>
              </tr>
            </thead>
            <tbody>
              {nodes.map((node) => (
                <tr key={node.id} data-selected={node.id === nodeId} onClick={event => {
                  if (!(event.target instanceof Element && event.target.closest("a"))) set({ node: node.id, edge: null });
                }} className="cursor-pointer">
                  <td><button type="button" className="table-action" aria-label={`Otwórz reklamę #${node.id}`}>#{node.id}</button></td>
                  <td className="font-mono text-[0.92rem]">{node.case ?? ""}</td>
                  <td className="max-w-0 w-full">{node.label}</td>
                  <td>
                    <GroupLink group={node.campaign} />
                  </td>
                  <td>
                    <GroupLink group={node.operator} />
                  </td>
                  <td>{node.listed && <Tag tone="rejected">Lista Ostrzeżeń</Tag>}</td>
                </tr>
              ))}
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

  const graphAndTable = (
    <Split id="inv-table" dir="col" fixed="second" initial={236} min={90} max={560}>
            <div className="flex min-h-0 min-w-0 flex-1">{canvas}</div>
            {bottom}
          </Split>
  );

  return (
    <>
      <TopBar crumbs={crumbs} />
      <div className="atlas-investigation"><Split id="inv-filters" dir="row" fixed="first" initial={208} min={180} max={360}>
        {filters}
        {edgeId === null && nodeId === null ? graphAndTable : <Split id="inv-inspector" dir="row" fixed="second" initial={380} min={280} max={820}>
          {graphAndTable}
          {inspector}
        </Split>}
      </Split></div>
    </>
  );
}
