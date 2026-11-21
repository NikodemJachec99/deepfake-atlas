"use client";

import { useMemo } from "react";
import { useRouter } from "next/navigation";
import type { AnalysisEvent, Family, FuseEventPayload } from "@/lib/api";
import { GraphCanvas, type GEdge, type GNode } from "./graph-canvas";

export function LiveGraph({ events, onEdge }: { events: AnalysisEvent[]; onEdge: (id: number) => void }) {
  const router = useRouter();
  const {nodes, edges} = useMemo(() => {
    const id = events.find(event => event.stage === "ingest" && event.status === "done")?.payload.ad;
    if (typeof id !== "number") return { nodes: [], edges: [] };
    const nodes = new Map<number, GNode>();
    const edges = new Map<number, GEdge>();
    function addNode(ad: number) {
      nodes.set(ad, { id: ad, label: `Reklama #${ad}`, focus: ad === id, campaign: null, operator: null, case: null });
    }
    addNode(id);
    for (const event of events) {
      if (event.stage !== "fuse" || event.status !== "info") continue;
      const hit = event.payload as Partial<FuseEventPayload>;
      if (typeof hit.edge !== "number" || typeof hit.other_ad !== "number" || !hit.relation || typeof hit.probability !== "number") continue;
      const weights = Object.entries(hit.families ?? {}).sort((a, b) => b[1] - a[1]);
      addNode(hit.other_ad);
      edges.set(hit.edge, {id: hit.edge, source: id, target: hit.other_ad, relation: hit.relation,
        probability: hit.probability, family: weights.length ? weights[0][0] as Family : null});
    }
    return { nodes: [...nodes.values()], edges: [...edges.values()] };
  }, [events]);
  if (!nodes.length) return null;
  return <section aria-label="Graf analizy">
    <h2 className="font-semibold">Powiązania na żywo</h2>
    <div className="h-80"><GraphCanvas nodes={nodes} edges={edges} layout="radial" colorBy="campaign"
      onEdge={onEdge} onNode={id => router.push(`/ads/${id}`)} /></div>
  </section>;
}
