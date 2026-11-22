"use client";

import Link from "next/link";
import { useState } from "react";
import { ChevronDown, ChevronRight, Network } from "lucide-react";
import { api, RELATION_LABELS, type Group } from "@/lib/api";
import { bits } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import { Loading, ErrorBox } from "./ui";
import { CampaignMap } from "./campaign-map";

function CampaignBranch({ group }: { group: Group }) {
  const result = useApi(String(group.id), () => api.graph(`?campaign=${group.id}`));
  const [chosen, setChosen] = useState<number | null>(null);
  if (result.error) return <ErrorBox message={result.error} onRetry={result.reload} />;
  if (!result.data) return <Loading label="Pobieranie reklam" />;
  const { nodes, edges } = result.data;
  const members = nodes.filter(n => n.member ?? n.campaign === group.key);
  const neighbors = nodes.filter(n => !(n.member ?? n.campaign === group.key));
  const current = nodes.find(node => node.id === chosen) ?? members[0] ?? neighbors[0];
  if (!current) return <p className="p-4">Brak reklam w tym zakresie.</p>;
  const titles = new Map(nodes.map(node => [node.id, node.label]));
  const connected = edges.filter(edge => edge.source === current.id || edge.target === current.id)
    .sort((a,b) => b.probability - a.probability || a.id - b.id);
  return <div className="ml-4 grid min-w-0 gap-4 border-l-2 border-accent-soft py-3 pl-4 lg:grid-cols-[minmax(14rem,2fr)_minmax(18rem,3fr)]">
    <section className="min-w-0">
      {([["Reklamy kampanii", members], ["Sąsiedzi spoza kampanii", neighbors]] as const).map(([label, rows]) => {
        return <div key={label}><h3 className="mb-2 font-semibold">{label} ({rows.length})</h3>
      <div className="max-h-80 overflow-auto rounded-md border border-line">
        {rows.map(n => <button key={n.id} type="button" aria-pressed={n.id === current.id} onClick={() => setChosen(n.id)}
          className="flex w-full items-baseline gap-2 border-b border-line px-3 py-2 text-left last:border-0 hover:bg-panel aria-pressed:bg-accent-soft aria-pressed:text-accent">
          <span className="font-mono text-xs">#{n.id}</span><span className="break-words">{n.label || "Reklama"}</span>
        </button>)}
      </div></div>; })}
    </section>
    <section className="min-w-0">
      <div className="mb-2 flex flex-wrap justify-between gap-2"><h3 className="font-semibold">Powiązania reklamy #{current.id} ({connected.length})</h3>
        <Link href={`/ads/${current.id}`} className="text-accent underline">Karta reklamy</Link></div>
      {connected.length ? <ol className="max-h-80 overflow-auto border-t border-line">{connected.map(edge => {
        const other = current.id === edge.source ? edge.target : edge.source;
        return <li key={edge.id}><Link prefetch={false} href={`/investigation?campaign=${group.id}&edge=${edge.id}`}
          className="grid gap-0.5 border-b border-line px-2 py-2 hover:bg-panel">
          <span><span className="font-mono text-xs">↳ #{other}</span> {titles.get(other)}</span>
          <span className="text-sm text-muted">{RELATION_LABELS[edge.relation]} · {bits(edge.bits)} bita · <span className="text-accent">Dowody</span></span>
        </Link></li>;
      })}</ol> : <p className="text-muted">Brak powiązań tej reklamy w kampanii.</p>}
    </section>
  </div>;
}

export function CampaignTree({ groups }: { groups: Group[] }) {
  const [map, setMap] = useState(false);
  const [expanded, setExpanded] = useState<Set<number>>(new Set());
  const [query, setQuery] = useState("");
  function toggleCampaign(id: number) {
    setExpanded(current => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }
  const visible = groups.filter(g => (g.key + " " + g.label).toLocaleLowerCase("pl").includes(query.trim().toLocaleLowerCase("pl")));
  return <>
    <div className="flex flex-wrap items-center justify-between gap-3 border-y border-line py-3">
      <div className="flex rounded-lg bg-panel p-1">{["Drzewo kampanii", "Mapa węzłów"].map((name,i) =>
        <button key={name} aria-pressed={map === Boolean(i)} className="rounded-md px-3 py-2 font-medium aria-pressed:bg-raised aria-pressed:text-accent aria-pressed:shadow-sm"
          onClick={() => setMap(Boolean(i))}>{name}</button>)}</div>
      {!map && <input type="search" aria-label="Szukaj kampanii" placeholder="Szukaj kampanii…" value={query} onChange={e=>setQuery(e.target.value)} className="max-w-full rounded-md border border-line-strong px-3 py-2" />}
    </div>
    {map ? <CampaignMap groups={groups} expanded={expanded} onToggle={toggleCampaign} /> : <section aria-label="Drzewo kampanii">
      {!visible.length && <p>Brak kampanii odpowiadających wyszukiwaniu.</p>}
      {visible.map(group => {
        const open = expanded.has(group.id);
        const Icon = open ? ChevronDown : ChevronRight;
        return <div key={group.id} className="border-b border-line">
          <button aria-expanded={open} onClick={() => toggleCampaign(group.id)} className="flex w-full items-center gap-3 px-2 py-3 text-left hover:bg-panel">
            <Icon size={18}/><Network size={20} className="text-accent"/><strong className="text-lg">{group.key}</strong>
            <span className="min-w-0 flex-1 truncate">{group.label}</span><span className="text-muted">Reklamy · {group.size}</span>
          </button>
          {open && <CampaignBranch group={group}/>}
        </div>;
      })}
    </section>}
  </>;
}
