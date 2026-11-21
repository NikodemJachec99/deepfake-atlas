"use client";

import dynamic from "next/dynamic";

import { Loading } from "./ui";

export type { GEdge, GNode, GraphCanvasProps } from "./graph-canvas-impl";

// Sigma potrzebuje WebGL, więc płótno powstaje dopiero w przeglądarce.
export const GraphCanvas = dynamic(() => import("./graph-canvas-impl"), { ssr: false, loading: () => <Loading label="Przygotowanie płótna grafu" /> });
