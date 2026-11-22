"use client";

import { ChevronRight } from "lucide-react";

/** Rozwijana sekcja zakładki Kontekst w panelu pary. Nazwa przycisku to sam tytuł (używają jej skrypty zrzutów). */
export function ContextSection({ title, hint, open, onToggle, children }: { title: string; hint: string; open: boolean; onToggle: () => void; children: React.ReactNode }) {
  return <section className="min-w-0 border-b border-line">
    <button type="button" aria-expanded={open} onClick={onToggle} className="flex w-full items-center gap-2 px-3 pt-3 pb-1 text-left font-medium hover:text-accent">
      <ChevronRight size={14} aria-hidden className={`shrink-0 text-muted transition-transform ${open ? "rotate-90" : ""}`} />
      {title}
    </button>
    <p className="px-3 pb-3 pl-8 text-xs text-muted">{hint}</p>
    {open && <div className="grid min-w-0 gap-2 px-3 pb-3 pl-8 break-words" aria-live="polite">{children}</div>}
  </section>;
}
