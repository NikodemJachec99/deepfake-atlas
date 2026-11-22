"use client";

// Tryb ekspercki: domyślnie interfejs pokazuje wnioski prostym językiem, a szczegóły techniczne
// (bity, identyfikatory, wersje modelu, skróty) chowa. Wybór pamiętamy w przeglądarce.
import { useSyncExternalStore } from "react";

const KEY = "scamdna.expert";
const EVENT = "scamdna-expert";

function read(): boolean {
  try {
    return localStorage.getItem(KEY) === "1";
  } catch {
    return false; // przeglądarka bez localStorage: widok prosty
  }
}

function subscribe(callback: () => void) {
  window.addEventListener(EVENT, callback);
  window.addEventListener("storage", callback);
  return () => {
    window.removeEventListener(EVENT, callback);
    window.removeEventListener("storage", callback);
  };
}

export function useExpert() {
  const expert = useSyncExternalStore(subscribe, read, () => false);
  function setExpert(value: boolean) {
    try {
      localStorage.setItem(KEY, value ? "1" : "0");
    } catch {
      // bez zapisu wybór nie przetrwa odświeżenia
    }
    window.dispatchEvent(new Event(EVENT));
  }
  return { expert, setExpert };
}

/** Treść widoczna tylko w trybie eksperckim. `fallback` pokazuje się w trybie prostym. */
export function Expert({ children, fallback = null }: { children: React.ReactNode; fallback?: React.ReactNode }) {
  const { expert } = useExpert();
  return <>{expert ? children : fallback}</>;
}

/** Zgodność wsteczna: stan żyje w localStorage, provider niczego nie trzyma. */
export function ExpertProvider({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}

export function ExpertToggle() {
  const { expert, setExpert } = useExpert();
  return <label className="flex cursor-pointer items-center gap-2 text-sm font-normal text-muted">
    <input type="checkbox" checked={expert} onChange={event => setExpert(event.target.checked)} className="size-4 accent-[var(--color-accent)]" />
    Szczegóły techniczne
  </label>;
}
