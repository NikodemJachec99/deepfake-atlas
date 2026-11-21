"use client";

// Analizy uruchomione w tej przeglądarce i ich strumienie zdarzeń. Stan żyje ponad ekranami,
// więc analiza biegnie dalej po przejściu do Investigation, a pasek stanu widzi kolejkę.

import { createContext, useCallback, useContext, useEffect, useMemo, useReducer, useRef } from "react";

import { api, streamAnalysis, type Analysis, type AnalysisEvent } from "./api";

export interface Session {
  id: string;
  analysis: Analysis;
  events: AnalysisEvent[];
  stream: "waiting" | "open" | "closed";
}

interface State {
  sessions: Session[];
  activeId: string | null;
  tick: number; // rośnie po każdej zakończonej analizie: sygnał, że korpus się zmienił
}

type Action =
  | { type: "add"; analyses: Analysis[]; activate: boolean; stream: Session["stream"] }
  | { type: "event"; id: string; event: AnalysisEvent }
  | { type: "stream"; id: string; stream: Session["stream"]; reset?: boolean }
  | { type: "final"; id: string; analysis: Analysis }
  | { type: "select"; id: string | null };

function patch(state: State, id: string, change: (session: Session) => Session): State {
  return { ...state, sessions: state.sessions.map((s) => (s.id === id ? change(s) : s)) };
}

function reducer(state: State, action: Action): State {
  switch (action.type) {
    case "add": {
      const known = new Set(state.sessions.map((s) => s.id));
      const fresh = action.analyses.filter((a) => !known.has(a.id)).map((a) => ({ id: a.id, analysis: a, events: [], stream: action.stream }));
      return { ...state, sessions: [...fresh, ...state.sessions], activeId: action.activate && fresh[0] ? fresh[0].id : state.activeId };
    }
    case "event":
      return patch(state, action.id, (s) => (s.events.some((e) => e.seq === action.event.seq) ? s : { ...s, events: [...s.events, action.event] }));
    case "stream":
      return patch(state, action.id, (s) => ({ ...s, stream: action.stream, events: action.reset ? [] : s.events }));
    case "final":
      return { ...patch(state, action.id, (s) => ({ ...s, analysis: action.analysis })), tick: state.tick + 1 };
    case "select":
      return { ...state, activeId: action.id };
  }
}

interface Store extends State {
  active: Session | null;
  running: number;
  streaming: number;
  submit: (kind: "url" | "text", value: string) => Promise<void>;
  upload: (files: File[]) => Promise<void>;
  select: (id: string | null) => void;
}

const Context = createContext<Store | null>(null);
const RECENT_KEY = "scamdna.recent";
const MAX_STREAMS = 3; // przeglądarka ma limit połączeń na host, resztę zostawiamy dla zwykłych zapytań

function remember(ids: string[]) {
  try {
    const previous: string[] = JSON.parse(window.localStorage.getItem(RECENT_KEY) ?? "[]");
    window.localStorage.setItem(RECENT_KEY, JSON.stringify([...ids, ...previous.filter((id) => !ids.includes(id))].slice(0, 12)));
  } catch {
    // brak localStorage: lista ostatnich analiz żyje do przeładowania
  }
}

export function AnalysisProvider({ children }: { children: React.ReactNode }) {
  const [state, dispatch] = useReducer(reducer, { sessions: [], activeId: null, tick: 0 });
  const open = useRef(new Map<string, () => void>());
  const queue = useRef<Analysis[]>([]);
  const again = useRef<() => void>(() => undefined);

  const pump = useCallback(() => {
    while (open.current.size < MAX_STREAMS && queue.current.length > 0) {
      const analysis = queue.current.shift()!;
      dispatch({ type: "stream", id: analysis.id, stream: "open", reset: true });
      const stop = streamAnalysis(
        analysis,
        (event) => dispatch({ type: "event", id: analysis.id, event }),
        () => {
          open.current.delete(analysis.id);
          dispatch({ type: "stream", id: analysis.id, stream: "closed" });
          api.analysis(analysis.id).then(
            (finished) => dispatch({ type: "final", id: analysis.id, analysis: finished }),
            () => undefined,
          );
          again.current();
        },
      );
      open.current.set(analysis.id, stop);
    }
  }, []);
  useEffect(() => {
    again.current = pump;
  }, [pump]);

  const enqueue = useCallback(
    (analyses: Analysis[]) => {
      for (const analysis of analyses) if (!open.current.has(analysis.id) && !queue.current.some((a) => a.id === analysis.id)) queue.current.push(analysis);
      pump();
    },
    [pump],
  );

  useEffect(() => {
    const streams = open.current;
    let ids: string[] = [];
    try {
      ids = JSON.parse(window.localStorage.getItem(RECENT_KEY) ?? "[]");
    } catch {
      ids = [];
    }
    let live = true;
    Promise.allSettled(ids.map((id) => api.analysis(id))).then((results) => {
      if (!live) return;
      const found = results.flatMap((r) => (r.status === "fulfilled" ? [r.value] : []));
      dispatch({ type: "add", analyses: found, activate: false, stream: "closed" });
    });
    return () => {
      live = false;
      streams.forEach((stop) => stop());
      streams.clear();
    };
  }, []);

  const begin = useCallback(
    (analyses: Analysis[]) => {
      remember(analyses.map((a) => a.id));
      dispatch({ type: "add", analyses, activate: true, stream: "waiting" });
      enqueue(analyses);
    },
    [enqueue],
  );

  const submit = useCallback(async (kind: "url" | "text", value: string) => begin([await api.createAnalysis(kind, value)]), [begin]);
  const upload = useCallback(async (files: File[]) => begin(await api.uploadCase(files)), [begin]);

  const select = useCallback(
    (id: string | null) => {
      dispatch({ type: "select", id });
      const session = state.sessions.find((s) => s.id === id);
      // Analiza z poprzedniej sesji: strumień odtwarza zapisane zdarzenia od początku.
      if (session && session.stream === "closed" && session.events.length === 0) enqueue([session.analysis]);
    },
    [state.sessions, enqueue],
  );

  const store = useMemo<Store>(
    () => ({
      ...state,
      active: state.sessions.find((s) => s.id === state.activeId) ?? null,
      running: state.sessions.filter((s) => s.stream !== "closed" || s.analysis.status === "queued" || s.analysis.status === "running").length,
      streaming: state.sessions.filter((s) => s.stream === "open").length,
      submit,
      upload,
      select,
    }),
    [state, submit, upload, select],
  );

  return <Context.Provider value={store}>{children}</Context.Provider>;
}

export function useAnalyses(): Store {
  const store = useContext(Context);
  if (!store) throw new Error("useAnalyses poza AnalysisProvider");
  return store;
}
