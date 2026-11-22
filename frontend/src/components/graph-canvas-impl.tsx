"use client";

// Płótno grafu: Sigma.js + Graphology. Węzeł to reklama, krawędź to relacja z dowodami.
// Styl krawędzi koduje relację, kolor dominującą rodzinę markerów, grubość wynik modelu (niekalibrowany).

import { layerBorder } from "@sigma/node-border";
import Graph from "graphology";
import forceAtlas2 from "graphology-layout-forceatlas2";
import { ArrowDown, ArrowLeft, ArrowRight, ArrowUp, Maximize2, Minus, Plus } from "lucide-react";
import { animate } from "motion";
import { useEffect, useMemo, useRef, useState } from "react";
import Sigma from "sigma";
import { layerDashed } from "sigma/rendering";

import { FAMILY_LABELS, RELATION_LABELS, type Family, type Relation, type Verdict } from "@/lib/api";
import { FAMILIES, RELATIONS, groupColor, prob } from "@/lib/format";
import { useReducedMotion } from "@/lib/hooks";


import { FamilyDot, Mono, RelationLine, cx } from "./ui";

export interface GNode {
  id: number;
  label: string;
  campaign: string | null;
  operator: string | null;
  case: string | null;
  listed?: boolean;
  focus?: boolean; // analizowany materiał w Discovery
}

export interface GEdge {
  id: number;
  source: number;
  target: number;
  relation: Relation;
  duplicate?: boolean;
  probability: number;
  family: Family | null;
  verdict?: Verdict;
  hidden?: boolean; // odfiltrowana: zostaje w układzie, znika z widoku
}

export interface GraphCanvasProps {
  nodes: GNode[];
  edges: GEdge[];
  colorBy: "operator" | "campaign";
  layout: "force" | "radial";
  selectedEdge?: number | null;
  selectedNode?: number | null;
  onEdge?: (id: number) => void;
  onNode?: (id: number) => void;
  onClear?: () => void;
  legend?: boolean;
}

const RANK: Record<Relation, number> = { same_campaign: 1, same_operator: 1.7, similar: 2.4 };
const WEIGHT: Record<Relation, number> = { same_campaign: 3, same_operator: 1, similar: 0.3 };

function cssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || "#888888";
}

function alpha(hex: string, a: number): string {
  const h = hex.replace("#", "");
  const full = h.length === 3 ? h.split("").map((c) => c + c).join("") : h.slice(0, 6);
  const n = Number.parseInt(full, 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${a})`;
}

// Układ siłowy liczony od stałych pozycji startowych: ten sam graf daje zawsze ten sam rysunek.
function forcePositions(nodes: GNode[], edges: GEdge[]): Map<number, { x: number; y: number }> {
  const graph = new Graph({ type: "undirected", multi: false });
  const sorted = [...nodes].sort((a, b) => a.id - b.id);
  sorted.forEach((node, index) => {
    const angle = (index / Math.max(1, sorted.length)) * Math.PI * 2;
    graph.addNode(node.id, { x: Math.cos(angle) * 10, y: Math.sin(angle) * 10 });
  });
  for (const edge of edges) {
    if (edge.source !== edge.target && graph.hasNode(edge.source) && graph.hasNode(edge.target) && !graph.hasEdge(edge.source, edge.target)) {
      graph.addEdge(edge.source, edge.target, { weight: WEIGHT[edge.relation] });
    }
  }
  if (graph.order > 1) {
    forceAtlas2.assign(graph, {
      iterations: 350,
      getEdgeWeight: "weight",
      settings: { ...forceAtlas2.inferSettings(graph), gravity: 1.2, scalingRatio: 6, edgeWeightInfluence: 1, barnesHutOptimize: graph.order > 400 },
    });
  }
  const positions = new Map<number, { x: number; y: number }>();
  graph.forEachNode((key, attributes) => positions.set(Number(key), { x: attributes.x, y: attributes.y }));
  return positions;
}

// Układ promienisty dla Discovery: analizowany materiał w środku, powiązane reklamy w kolejności napływu zdarzeń.
function radialPositions(nodes: GNode[], edges: GEdge[]): Map<number, { x: number; y: number }> {
  const focus = nodes.find((n) => n.focus);
  const positions = new Map<number, { x: number; y: number }>();
  let index = 0;
  for (const node of nodes) {
    if (node === focus) {
      positions.set(node.id, { x: 0, y: 0 });
      continue;
    }
    const link = edges.filter((e) => focus && ((e.source === focus.id && e.target === node.id) || (e.target === focus.id && e.source === node.id)));
    const radius = link.length ? Math.min(...link.map((e) => RANK[e.relation])) : 2.4;
    const angle = index * 2.399963 - Math.PI / 2;
    positions.set(node.id, { x: Math.cos(angle) * radius, y: Math.sin(angle) * radius });
    index += 1;
  }
  return positions;
}

function createSigma(graph: Graph, container: HTMLElement) {
  return new Sigma(graph, container, {
    primitives: {
      nodes: {
        variables: {
          ringColor: { type: "color", default: "#888888" },
          ringSize: { type: "number", default: 2 },
        },
        // Obwódka cieńsza niż ok. 1,5 px gasi cały węzeł (Sigma 4.0), więc węzeł bez obwódki dostaje 2 px we własnym kolorze.
        layers: [
          layerBorder({
            borders: [
              { size: { attribute: "ringSize" }, color: { attribute: "ringColor" }, mode: "pixels" },
              { size: 0, color: { attribute: "color" }, fill: true },
            ],
          }),
        ],
      },
      edges: {
        variables: {
          gapColor: { type: "color", default: "#00000000" },
        },
        // Jedna warstwa dla wszystkich relacji: linia ciągła to kreski z przerwą w kolorze linii.
        layers: [layerDashed({ dashSize: { value: 6, mode: "pixels" }, gapSize: { value: 5, mode: "pixels" }, gapColor: { attribute: "gapColor", default: "#00000000" } })],
      },
    },
    styles: {
      nodes: {
        x: { attribute: "x" },
        y: { attribute: "y" },
        size: (attributes, state) => (attributes.size ?? 6) + (state.isHovered ? 1.5 : 0),
        color: { attribute: "color", defaultValue: "#888888" },
        label: { attribute: "label" },
        labelColor: { attribute: "labelColor", defaultValue: "#888888" },
        labelSize: 11,
        labelFont: { attribute: "labelFont", defaultValue: "sans-serif" },
        labelVisibility: { whenState: "isHovered", then: "visible", else: "auto" },
        backdropVisibility: { whenState: "isHovered", then: "visible", else: "hidden" },
        backdropColor: { attribute: "backdropColor", defaultValue: "#000000" },
        backdropShadowColor: "rgba(0, 0, 0, 0)",
        backdropShadowBlur: 0,
        backdropPadding: 4,
        depth: { whenState: "isHovered", then: "topNodes", else: "nodes" },
        ringColor: { attribute: "ringColor", defaultValue: "#888888" },
        ringSize: { attribute: "ringSize", defaultValue: 2 },
        cursor: "pointer",
      },
      edges: {
        size: (attributes, state) => (attributes.size ?? 1) + (state.isHovered ? 1.5 : 0),
        color: { attribute: "color", defaultValue: "#888888" },
        label: { attribute: "label" },
        labelColor: { attribute: "labelColor", defaultValue: "#888888" },
        labelSize: 10,
        visibility: { attribute: "visibility", defaultValue: "visible" },
        zIndex: { attribute: "zIndex", defaultValue: 0 },
        depth: { whenState: "isHovered", then: "topEdges", else: "edges" },
        gapColor: { attribute: "gapColor", defaultValue: "#00000000" },
        cursor: "pointer",
      },
    },
    settings: {
      itemSizesReference: "screen",
      enableEdgeEvents: true,
      renderEdgeLabels: true,
      edgePickingPadding: 4,
      labelDensity: 0.28,
      labelRenderedSizeThreshold: 5,
      stagePadding: 48,
      minCameraRatio: 0.05,
      maxCameraRatio: 8,
      allowInvalidContainer: true,
    },
  });
}

export default function GraphCanvasImpl({ nodes, edges, colorBy, layout, selectedEdge, selectedNode, onEdge, onNode, onClear, legend = true }: GraphCanvasProps) {
  const container = useRef<HTMLDivElement>(null);
  const sigma = useRef<Sigma | null>(null);
  const graph = useRef<Graph | null>(null);
  const layoutKey = useRef("");
  const targets = useRef(new Map<number, { x: number; y: number }>());
  const reduced = useReducedMotion();
  const [showAll, setShowAll] = useState(false);
  const available = useMemo(() => edges.filter(edge => !edge.hidden), [edges]);
  const dense = layout === "force" && available.length > Math.max(35, nodes.length * 2);
  const drawn = useMemo(() => {
    if (!dense || showAll) return new Set(available.map(edge => edge.id));
    const strongest = new Map<number, GEdge>();
    const ids = new Set<number>();
    for (const edge of available) {
      for (const node of [edge.source, edge.target]) {
        const prior = strongest.get(node);
        if (!prior || edge.probability > prior.probability || (edge.probability === prior.probability && edge.id < prior.id)) strongest.set(node, edge);
      }
      if (edge.id === selectedEdge || edge.source === selectedNode || edge.target === selectedNode) ids.add(edge.id);
    }
    for (const edge of strongest.values()) ids.add(edge.id);
    return ids;
  }, [available, dense, showAll, selectedEdge, selectedNode]);
  const [hover, setHover] = useState<{ kind: "node" | "edge"; id: number } | null>(null);
  const [failed, setFailed] = useState("");
  const handlers = useRef({ onEdge, onNode, onClear });
  useEffect(() => {
    handlers.current = { onEdge, onNode, onClear };
  });

  useEffect(() => {
    if (!container.current) return;
    const g = new Graph({ type: "undirected", multi: false });
    let instance: Sigma;
    try {
      instance = createSigma(g, container.current);
    } catch (reason) {
      queueMicrotask(() => setFailed(reason instanceof Error ? reason.message : String(reason)));
      return;
    }
    graph.current = g;
    sigma.current = instance;
    instance.on("clickNode", ({ node }) => handlers.current.onNode?.(Number(node)));
    instance.on("clickEdge", ({ edge }) => handlers.current.onEdge?.(Number(edge)));
    instance.on("clickStage", () => handlers.current.onClear?.());
    instance.on("enterNode", ({ node }) => setHover({ kind: "node", id: Number(node) }));
    instance.on("leaveNode", () => setHover(null));
    instance.on("enterEdge", ({ edge }) => setHover({ kind: "edge", id: Number(edge) }));
    instance.on("leaveEdge", () => setHover(null));
    const observer = new ResizeObserver(() => {
      instance.resize();
      instance.scheduleRefresh();
    });
    const surface = container.current;
    function rotate(event: WheelEvent) {
      if (event.ctrlKey || event.metaKey || !event.deltaY) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      const unit = event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? surface.clientHeight : 1;
      const delta = Math.max(-240, Math.min(240, event.deltaY * unit));
      const camera = instance.getCamera();
      camera.setState({ angle: camera.getState().angle + delta * Math.PI / 1500 });
    }
    surface.addEventListener("wheel", rotate, { capture: true, passive: false });
    observer.observe(surface);
    return () => {
      surface.removeEventListener("wheel", rotate, true);
      observer.disconnect();
      instance.kill();
      sigma.current = null;
      graph.current = null;
      layoutKey.current = "";
      targets.current = new Map();
    };
  }, []);

  useEffect(() => {
    const g = graph.current;
    const s = sigma.current;
    if (!g || !s) return;

    const fg = cssVar("--fg");
    const muted = cssVar("--muted");
    const faint = cssVar("--faint");
    const accent = cssVar("--accent");
    const raised = cssVar("--raised");
    const listed = cssVar("--st-rejected");
    const family = Object.fromEntries(FAMILIES.map((f) => [f, cssVar(`--fam-${f}`)])) as Record<Family, string>;
    const font = getComputedStyle(document.body).fontFamily.split(",")[0].replace(/["']/g, "").trim() || "sans-serif";

    // Układ zależy tylko od zbioru węzłów i krawędzi, nie od filtrów ani zaznaczenia.
    const key = `${layout}|${nodes.map((n) => n.id).join(",")}|${edges.map((e) => e.id).join(",")}`;
    if (key !== layoutKey.current) {
      layoutKey.current = key;
      targets.current = layout === "radial" ? radialPositions(nodes, edges) : forcePositions(nodes, edges);
      s.setCustomBBox(layout === "radial" ? { x: [-2.7, 2.7], y: [-2.7, 2.7] } : null);
    }

    const visible = edges.filter((e) => !e.hidden);
    const linked = new Set<number>();
    for (const edge of visible) {
      linked.add(edge.source);
      linked.add(edge.target);
    }
    const picked = selectedEdge != null ? edges.find((e) => e.id === selectedEdge) : undefined;
    const anySelection = picked !== undefined || selectedNode != null;

    const wanted = new Set(nodes.map((n) => String(n.id)));
    g.forEachNode((nodeKey) => {
      if (!wanted.has(nodeKey)) g.dropNode(nodeKey);
    });
    for (const node of nodes) {
      const target = targets.current.get(node.id) ?? { x: 0, y: 0 };
      const isSelected = node.id === selectedNode || (picked !== undefined && (picked.source === node.id || picked.target === node.id));
      const dim = (!linked.has(node.id) && !node.focus && edges.length > 0) || (anySelection && !isSelected);
      const base = groupColor(colorBy === "operator" ? node.operator : node.campaign, "light");
      const title = node.label.length > 38 ? `${node.label.slice(0, 37)}…` : node.label;
      const fill = dim ? alpha(base, 0.35) : base;
      const ring = isSelected ? accent : node.listed ? listed : node.focus ? fg : null;
      const attributes = {
        size: node.focus ? 10 : dense ? 4 : 7,
        color: fill,
        label: dense ? `#${node.id}` : node.case ? `${node.case} · ${title}` : title,
        labelColor: dim ? faint : fg,
        labelFont: font,
        backdropColor: raised,
        ringColor: ring ?? fill,
        ringSize: ring ? 3 : 2,
      };
      if (g.hasNode(node.id)) {
        g.mergeNodeAttributes(node.id, { ...attributes, ...(layout === "force" ? target : {}) });
      } else if (layout === "radial" && !node.focus && !reduced) {
        // Nowy węzeł wyjeżdża ze środka na swoje miejsce. To jedyna dłuższa sekwencja ruchu poza Evolution.
        g.addNode(node.id, { ...attributes, x: 0, y: 0, size: 0.5 });
        const id = node.id;
        animate(0, 1, {
          duration: 0.45,
          ease: "easeOut",
          onUpdate: (t) => {
            if (graph.current === g && g.hasNode(id)) g.mergeNodeAttributes(id, { x: target.x * t, y: target.y * t, size: 0.5 + (attributes.size - 0.5) * t });
          },
        });
      } else {
        g.addNode(node.id, { ...attributes, ...target });
      }
    }

    const wantedEdges = new Set(edges.map((e) => String(e.id)));
    g.forEachEdge((edgeKey) => {
      if (!wantedEdges.has(edgeKey)) g.dropEdge(edgeKey);
    });
    for (const edge of edges) {
      if (edge.source === edge.target || !g.hasNode(edge.source) || !g.hasNode(edge.target)) continue;
      const isSelected = edge.id === selectedEdge;
      const touchesNode = selectedNode != null && (edge.source === selectedNode || edge.target === selectedNode);
      const base = edge.verdict === "rejected" ? faint : edge.family ? family[edge.family] : muted;
      // Wynik modelu (niekalibrowany) koduje grubość i nasycenie. Relacja koduje styl linii.
      const strength = 0.45 + 0.55 * edge.probability;
      const opacity = edge.verdict === "rejected" ? 0.35 : anySelection && !isSelected && !touchesNode ? 0.18 : strength;
      const width = edge.relation === "same_campaign" ? 1.5 + 2.5 * edge.probability : edge.relation === "same_operator" ? 0.6 + 0.9 * edge.probability : 1.2;
      const color = isSelected ? fg : alpha(base, opacity);
      const attributes = {
        size: isSelected ? width + 2 : width,
        color,
        gapColor: edge.relation === "similar" ? "#00000000" : color,
        label: edge.duplicate ? "duplikat" : edge.verdict === "confirmed" ? "potwierdzone" : edge.verdict === "rejected" ? "odrzucone" : "",
        labelColor: muted,
        visibility: !drawn.has(edge.id) ? "hidden" : "visible",
        zIndex: isSelected ? 3 : edge.relation === "same_campaign" ? 2 : edge.relation === "same_operator" ? 1 : 0,
      };
      if (g.hasEdge(edge.id)) g.mergeEdgeAttributes(edge.id, attributes);
      else if (!g.hasEdge(edge.source, edge.target)) g.addEdgeWithKey(edge.id, edge.source, edge.target, attributes);
    }
    s.scheduleRefresh();
  }, [nodes, edges, colorBy, layout, selectedEdge, selectedNode, reduced, dense, drawn]);

  const directions = [
    { key: "ArrowLeft", label: "w lewo", dx: -1, dy: 0, Icon: ArrowLeft },
    { key: "ArrowUp", label: "w górę", dx: 0, dy: -1, Icon: ArrowUp },
    { key: "ArrowDown", label: "w dół", dx: 0, dy: 1, Icon: ArrowDown },
    { key: "ArrowRight", label: "w prawo", dx: 1, dy: 0, Icon: ArrowRight },
  ];
  function pan(dx: number, dy: number) {
    const renderer = sigma.current;
    if (!renderer) return;
    const camera = renderer.getCamera();
    const state = camera.getState();
    const origin = renderer.viewportToFramedGraph({ x: 0, y: 0 });
    const target = renderer.viewportToFramedGraph({ x: dx * 70, y: dy * 70 });
    camera.setState({ x: state.x + target.x - origin.x, y: state.y + target.y - origin.y });
  }

  const zoom = (factor: number) => {
    const camera = sigma.current?.getCamera();
    if (!camera) return;
    if (factor === 0) void camera.reset({ duration: 150 });
    else void camera.animate({ ratio: camera.getState().ratio * factor }, { duration: 150 });
  };

  const hoveredEdge = hover?.kind === "edge" ? edges.find((e) => e.id === hover.id) : undefined;
  const hoveredNode = hover?.kind === "node" ? nodes.find((n) => n.id === hover.id) : undefined;
  const usedFamilies = FAMILIES.filter((f) => edges.some((e) => !e.hidden && e.family === f));

  return (
    <div className="relative h-full min-h-0 w-full min-w-0 overflow-hidden bg-bg">
      <div ref={container} tabIndex={0} role="region" aria-label="Graf powiązań. Przeciągnij tło lub użyj strzałek. Kółko obraca graf." className="absolute inset-0 cursor-grab active:cursor-grabbing" onKeyDown={event => {
        const direction = directions.find(item => item.key === event.key);
        if (direction) { event.preventDefault(); pan(direction.dx, direction.dy); }
      }} />
      <div className="absolute top-2 left-2 flex rounded-md border border-line bg-panel">
        {directions.map(({ key, label, dx, dy, Icon }) => <button key={key} type="button" aria-label={`Przesuń widok ${label}`} title={`Przesuń widok ${label}`} onClick={() => pan(dx, dy)} className="grid size-8 place-items-center hover:bg-hover"><Icon size={15} /></button>)}
      </div>
      {failed && <p className="absolute inset-x-0 top-10 px-4 text-rejected">Płótno grafu nie wystartowało (WebGL): {failed}</p>}

      <div className="no-print absolute top-2 right-2 flex flex-col overflow-hidden rounded-sm border border-line bg-panel">
        {[
          { icon: Plus, label: "Przybliż", factor: 1 / 1.5 },
          { icon: Minus, label: "Oddal", factor: 1.5 },
          { icon: Maximize2, label: "Dopasuj do okna", factor: 0 },
        ].map(({ icon: Icon, label, factor }) => (
          <button key={label} type="button" title={label} aria-label={label} onClick={() => zoom(factor)} className="flex h-6 w-6 items-center justify-center text-muted hover:bg-hover hover:text-fg">
            <Icon size={13} />
          </button>
        ))}
      </div>

      {dense && <label className="absolute top-12 left-2 flex items-center gap-2 rounded-md border border-line bg-raised px-2 py-1 text-sm">
        <input type="checkbox" checked={showAll} onChange={event => setShowAll(event.target.checked)} />
        Wszystkie połączenia
      </label>}
      {legend && (
        <details className="absolute bottom-8 left-2 rounded-md border border-line bg-panel p-2 text-[0.85rem] text-muted"><summary>Legenda</summary>
          {RELATIONS.map((relation) => (
            <span key={relation} className="flex items-center gap-2">
              <RelationLine relation={relation} />
              {RELATION_LABELS[relation]}
            </span>
          ))}
          <span className="flex items-center gap-2">
            <span className="inline-block h-2.5 w-2.5 rounded-full border-2 border-rejected bg-faint" />
            domena na Liście Ostrzeżeń
          </span>
          <span className="flex items-center gap-2">
            <span className="inline-block h-2.5 w-2.5 rounded-full bg-faint" />
            kolor węzła: {colorBy === "operator" ? "operator" : "kampania"}
          </span>
          {usedFamilies.length > 0 && (
            <span className="mt-1 flex max-w-64 flex-wrap gap-x-2 gap-y-0.5 border-t border-line pt-1">
              {usedFamilies.map((f) => (
                <span key={f} className="flex items-center gap-1">
                  <FamilyDot family={f} size={7} />
                  {FAMILY_LABELS[f]}
                </span>
              ))}
            </span>
          )}
        </details>
      )}

      <div className={cx("absolute inset-x-0 bottom-0 flex h-6 items-center gap-3 border-t border-line bg-panel/95 px-2 text-[0.85rem]", !hover && "text-faint")}>
        {hoveredEdge ? (
          <>
            <Mono>
              #{hoveredEdge.source} ↔ #{hoveredEdge.target}
            </Mono>
            <span>{RELATION_LABELS[hoveredEdge.relation]}</span>
            {hoveredEdge.duplicate && <span className="text-new">duplikat</span>}
            <span>
              wynik modelu (niekalibrowany) <Mono>{prob(hoveredEdge.probability)}</Mono>
            </span>
            {hoveredEdge.family && (
              <span className="flex items-center gap-1">
                <FamilyDot family={hoveredEdge.family} size={7} />
                {FAMILY_LABELS[hoveredEdge.family]}
              </span>
            )}
            <span className="text-muted">kliknij, aby zobaczyć dowody</span>
          </>
        ) : hoveredNode ? (
          <>
            <Mono>#{hoveredNode.id}</Mono>
            <span className="truncate">{hoveredNode.label}</span>
            {hoveredNode.case && <span className="text-muted">sprawa {hoveredNode.case}</span>}
            {hoveredNode.campaign && <Mono>{hoveredNode.campaign}</Mono>}
            {hoveredNode.operator && <Mono>{hoveredNode.operator}</Mono>}
            {hoveredNode.listed && <span className="text-rejected">Lista Ostrzeżeń</span>}
          </>
        ) : (
          <span>
            {nodes.length} węzłów · {drawn.size} z {edges.length} krawędzi{dense && !showAll && " · najsilniejsze dla każdego węzła"} · kółko obraca graf · krawędź otwiera dowody, węzeł kartę reklamy
          </span>
        )}
      </div>
    </div>
  );
}
