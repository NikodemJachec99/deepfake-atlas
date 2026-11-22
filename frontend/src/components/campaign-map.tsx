"use client";

import Link from "next/link";
import { RotateCcw, RotateCw } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { api, type Group, type Graph } from "@/lib/api";
import { groupColor } from "@/lib/format";
import { allGroups as loadGroups } from "@/lib/group-pages";
import { useApi } from "@/lib/hooks";

function CampaignNode({ group, x, y, angle, color, expanded, toggle }: {
  group: Group; x: number; y: number; angle: number; color: string; expanded: boolean; toggle: () => void;
}) {
  const result = useApi(expanded ? String(group.id) : null, () => api.graph(`?campaign=${group.id}`));
  const [all, setAll] = useState(false);
  const layout = useMemo(() => {
    const nodes = (result.data?.nodes ?? []).filter(n => n.member ?? n.campaign === group.key);
    const positions = new Map(nodes.map((n, i) => {
      const angle = i * 2.399963;
      const radius = 28 + 49 * Math.sqrt((i + 1) / nodes.length);
      return [n.id, { x: radius * Math.cos(angle), y: radius * Math.sin(angle) }];
    }));
    const edges = (result.data?.edges ?? []).filter(e => positions.has(e.source) && positions.has(e.target));
    const strongest = new Map<number, Graph["edges"][number]>();
    for (const e of edges) for (const id of [e.source, e.target]) {
      const old = strongest.get(id);
      if (!old || old.probability < e.probability) strongest.set(id, e);
    }
    return { nodes, positions, edges: all ? edges : [...new Set(strongest.values())], total: edges.length };
  }, [result.data, all, group.key]);
  return <g transform={`translate(${x} ${y})`}>
    {expanded && <>
      <circle r="84" fill="var(--accent-soft)" stroke="var(--line)" />
      {layout.edges.map(e => {
        const a = layout.positions.get(e.source), b = layout.positions.get(e.target);
        if (!a || !b) return null;
        const endpoints = { x1: a.x, y1: a.y, x2: b.x, y2: b.y };
        const label = `Dowody powiązania #${e.id} · reklamy #${e.source} i #${e.target}`;
        return <Link key={e.id} className="group" aria-label={label} href={`/investigation?campaign=${group.id}&edge=${e.id}`} prefetch={false}>
          <title>{label}</title>
          <line {...endpoints} stroke="transparent" strokeWidth="12" vectorEffect="non-scaling-stroke" pointerEvents="stroke" />
          <line {...endpoints} stroke="var(--accent)" strokeWidth=".9" pointerEvents="none"
            className="opacity-35 group-hover:opacity-100 group-focus-visible:opacity-100 group-hover:stroke-2 group-focus-visible:stroke-2" />
        </Link>;
      })}
      {layout.nodes.map(n => <Link key={n.id} href={`/ads/${n.id}`} prefetch={false} aria-label={`Reklama #${n.id}`}>
        <title>#{n.id} · {n.label}</title><circle {...{cx:layout.positions.get(n.id)?.x, cy:layout.positions.get(n.id)?.y}} r="4" fill="var(--accent)" stroke="white" />
      </Link>)}
    </>}
    <g transform={`rotate(${-angle})`} role="button" tabIndex={0} aria-label={`Kampania ${group.key}, liczba reklam ${group.size}`} aria-expanded={expanded}
      className="cursor-pointer" onClick={toggle} onKeyDown={e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(); } }}>
      <title>{group.label || group.key} · {group.size} reklam</title>
      <circle r="20" fill={expanded ? color : "var(--raised)"} stroke={color} strokeWidth="2" />
      <text textAnchor="middle" dy="5" fill={expanded ? "white" : "var(--accent)"} fontSize="14" fontWeight="600">{group.size}</text>
      <text textAnchor="middle" y={expanded ? -88 : 38} fill="var(--fg)" fontSize="13">{group.key}</text>
    </g>
    {expanded && <foreignObject transform={`rotate(${-angle})`} x="-92" y="84" width="184" height="65">
      <div className="text-center text-xs">{result.loading ? "Pobieranie reklam…" : result.error ? <button onClick={result.reload}>Ponów pobranie</button> :
        <button aria-pressed={all} onClick={() => setAll(!all)} className="text-accent underline">{all ? "Najsilniejsze połączenia" : `Połączenia wewnętrzne (${layout.total})`}</button>}
        {result.data?.truncated && <p>Pobrano {result.data.edges.length} z {result.data.total} powiązań zakresu.</p>}
      </div>
    </foreignObject>}
  </g>;
}

async function loadMapOperators() {
  const list = await loadGroups("operators");
  return Promise.all(list.results.map(async ({ id, key }) => {
    const { campaigns } = await api.operator(id);
    return { id, key, campaigns };
  }));
}

export function createMapOperatorLoader() {
  let pending: ReturnType<typeof loadMapOperators> | undefined;
  return () => {
    pending ??= loadMapOperators().catch(error => {
      pending = undefined;
      throw error;
    });
    return pending;
  };
}

export function CampaignMap({ groups, expanded, onToggle, loadOperators }: {
  loadOperators: typeof loadMapOperators;
  groups: Group[];
  expanded: ReadonlySet<number>;
  onToggle: (id: number) => void;
}) {
  const [scale, setScale] = useState(1);
  const [angle, setAngle] = useState(0);
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const surface = useRef<SVGSVGElement>(null);
  const drag = useRef<{x:number; y:number} | null>(null);
  const operators = useApi("map-operators", loadOperators);
  const locations = groups.map((group, index) => ({
    group, x: 125 + (index % Math.ceil(Math.sqrt(groups.length))) * 215,
    y: 155 + Math.floor(index / Math.ceil(Math.sqrt(groups.length))) * 270,
    owners: operators.data?.filter(operator => operator.campaigns.includes(group.key)) ?? [],
  }));
  const width = Math.max(...locations.map(item => item.x)) + 125;
  const height = Math.max(...locations.map(item => item.y)) + 125;
  const selected = locations.find(item => item.group.id === Array.from(expanded).at(-1));
  useEffect(() => {
    const svg = surface.current;
    if (!svg) return;
    function wheel(e: WheelEvent) {
      e.preventDefault();
      const delta = e.deltaY || e.deltaX;
      if (e.shiftKey) setAngle(value => value + Math.sign(delta) * 4);
      else setScale(value => Math.max(.4, Math.min(8, value * Math.exp(-Math.sign(delta) * .12))));
    }
    svg.addEventListener("wheel", wheel, { passive: false });
    return () => svg.removeEventListener("wheel", wheel);
  }, []);
  return <section className="flex min-h-[55vh] flex-1 flex-col rounded-lg border border-line">
    <div className="flex flex-wrap items-center gap-3 border-b border-line p-2">
      <span id="campaign-map-help" className="basis-full">Kliknij węzeł kampanii, aby rozwinąć lub zwinąć jej reklamy. Kółko zmienia skalę, Shift z kółkiem obraca mapę. Po ustawieniu fokusu na mapie strzałki ją przesuwają.</span>
      <button aria-label="Oddal" onClick={() => setScale(v => Math.max(.4,v/1.4))}>−</button>
      <button aria-label="Przybliż" onClick={() => setScale(v => Math.min(8,v*1.4))}>＋</button>
      <button aria-label="Obróć mapę w lewo" title="Obróć mapę w lewo" className="grid size-10 place-items-center" onClick={() => setAngle(v => v - 15)}><RotateCcw size={18}/></button>
      <button aria-label="Obróć mapę w prawo" title="Obróć mapę w prawo" className="grid size-10 place-items-center" onClick={() => setAngle(v => v + 15)}><RotateCw size={18}/></button>
      <button onClick={() => {setScale(1);setAngle(0);setOffset({x:0,y:0});}}>Dopasuj widok</button>
      {selected && <button onClick={() => {
        setAngle(0); setScale(1); setOffset({ x: width/2 - selected.x, y: height/2 - selected.y });
      }}>Wróć do zaznaczenia · {selected.group.key}</button>}
    </div>
    {operators.error && <button className="text-accent" onClick={operators.reload}>Ponów pobranie operatorów mapy</button>}
    <svg ref={surface} className="min-h-[48vh] w-full flex-1 touch-none cursor-grab" viewBox={`0 0 ${width} ${height}`} aria-label="Graf kampanii" aria-describedby="campaign-map-help" tabIndex={0}
      onKeyDown={e => {
        if (e.target !== e.currentTarget || e.altKey || e.ctrlKey || e.metaKey) return;
        const directions: Record<string, [number, number]> = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] };
        const direction = directions[e.key];
        const matrix = e.currentTarget.getScreenCTM();
        if (!direction || !matrix) return;
        e.preventDefault();
        setOffset(v => ({ x: v.x + direction[0] * 48 / matrix.a, y: v.y + direction[1] * 48 / matrix.d }));
      }}
      onPointerDown={e => { if ((e.target as Element).closest('a,button,[role="button"]')) return; drag.current={x:e.clientX,y:e.clientY};e.currentTarget.setPointerCapture(e.pointerId); }}
      onPointerMove={e => { const prev=drag.current, matrix=e.currentTarget.getScreenCTM(); if (!prev || !matrix) return;
        const dx=(e.clientX-prev.x)/matrix.a, dy=(e.clientY-prev.y)/matrix.d; drag.current={x:e.clientX,y:e.clientY}; setOffset(v=>({x:v.x+dx,y:v.y+dy})); }}
      onLostPointerCapture={()=>{drag.current=null;}}>
      <g transform={`translate(${width/2+offset.x} ${height/2+offset.y}) rotate(${angle}) scale(${scale}) translate(${-width/2} ${-height/2})`}>
        {operators.data?.map(operator => {
          const cells = locations.filter(item => item.owners.some(owner => owner.id === operator.id));
          if (!cells.length) return null;
          const x = cells[0].x, y = cells[0].y - 110;
          const color = groupColor(operator.key, "light");
          return <g key={operator.id}>
            {cells.map(cell => <line key={cell.group.id} x1={x} y1={y} x2={cell.x} y2={cell.y} stroke={color} />)}
            <g transform={`rotate(${-angle} ${x} ${y})`}><Link href={`/operators/${operator.id}`} aria-label={`Operator ${operator.key}`}>
              <rect x={x-40} y={y-12} width="80" height="24" rx="5" fill={color}/>
              <text x={x} y={y+4} textAnchor="middle" fontSize="13" fill="white">{operator.key}</text>
            </Link></g>
          </g>;
        })}
        {locations.map(({group,x,y,owners}) => <CampaignNode key={group.id} group={group} x={x} y={y} angle={angle}
          color={groupColor(owners[0]?.key, "light")} expanded={expanded.has(group.id)} toggle={() => onToggle(group.id)} />)}
      </g>
    </svg>
  </section>;
}
