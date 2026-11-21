"use client";

import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";

import { ApiError } from "./api";
import { errorText } from "./format";

interface ApiState<T> {
  key: string | null;
  data?: T;
  error?: string;
  status?: number;
}

// Pobranie z API ze stanami: ładowanie, błąd, dane. `key` identyfikuje zapytanie; null wyłącza pobieranie.
export function useApi<T>(key: string | null, fetcher: () => Promise<T>) {
  const [state, setState] = useState<ApiState<T>>({ key: null });
  const [nonce, setNonce] = useState(0);
  const latest = useRef(fetcher);
  useEffect(() => {
    latest.current = fetcher;
  });
  useEffect(() => {
    if (key === null) return;
    let live = true;
    latest.current().then(
      (data) => live && setState({ key, data }),
      (reason) => live && setState({ key, error: errorText(reason), status: reason instanceof ApiError ? reason.status : undefined }),
    );
    return () => {
      live = false;
    };
  }, [key, nonce]);
  const fresh = state.key === key;
  const reload = useCallback(() => setNonce((n) => n + 1), []);
  const set = useCallback((data: T) => setState((s) => ({ ...s, data })), []);
  return {
    data: fresh ? state.data : undefined,
    status: fresh ? state.status : undefined,
    error: fresh ? state.error : undefined,
    loading: key !== null && !fresh,
    reload,
    set,
  };
}

// Wartość w localStorage, bezpieczna dla prerenderu: serwer i pierwsze malowanie dostają wartość domyślną.
const listeners = new Set<() => void>();
function subscribe(callback: () => void) {
  listeners.add(callback);
  window.addEventListener("storage", callback);
  return () => {
    listeners.delete(callback);
    window.removeEventListener("storage", callback);
  };
}

export function useStored(name: string, fallback: string): [string, (value: string) => void] {
  const value = useSyncExternalStore(
    subscribe,
    () => {
      try {
        return window.localStorage.getItem(name) ?? fallback;
      } catch {
        return fallback;
      }
    },
    () => fallback,
  );
  const set = useCallback(
    (next: string) => {
      try {
        window.localStorage.setItem(name, next);
      } catch {
        // tryb prywatny: wartość żyje tylko do przeładowania
      }
      listeners.forEach((listener) => listener());
    },
    [name],
  );
  return [value, set];
}

export function useReducedMotion(): boolean {
  return useSyncExternalStore(
    (callback) => {
      const query = window.matchMedia("(prefers-reduced-motion: reduce)");
      query.addEventListener("change", callback);
      return () => query.removeEventListener("change", callback);
    },
    () => window.matchMedia("(prefers-reduced-motion: reduce)").matches,
    () => false,
  );
}

export function useHotkey(handler: (event: KeyboardEvent) => void) {
  const latest = useRef(handler);
  useEffect(() => {
    latest.current = handler;
  });
  useEffect(() => {
    const listener = (event: KeyboardEvent) => latest.current(event);
    window.addEventListener("keydown", listener);
    return () => window.removeEventListener("keydown", listener);
  }, []);
}

export const isTyping = (event: KeyboardEvent) => {
  const target = event.target as HTMLElement | null;
  return !!target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.tagName === "SELECT" || target.isContentEditable);
};
