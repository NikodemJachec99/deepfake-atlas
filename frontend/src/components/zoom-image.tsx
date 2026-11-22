"use client";

import { useEffect, useRef, useState } from "react";
import { artifactImageUrl } from "@/lib/api";

// Zrzut reklamy, który po kliknięciu otwiera się powiększony w oknie dialogowym.
// Natywny <dialog>: Esc zamyka, fokus zostaje w oknie, tło jest nieaktywne, działa z klawiatury.
// Obraz zawsze z API artefaktów, nigdy strona oszusta.
export function ZoomImage({ sha, alt, className = "", buttonClassName = "", title = "Powiększ zrzut", onError }: {
  sha: string; alt: string; onError?: () => void; className?: string; buttonClassName?: string; title?: string;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDialogElement>(null);
  const src = artifactImageUrl(sha);

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  return (
    <>
      <button type="button" onClick={() => setOpen(true)} title={title} aria-haspopup="dialog"
        className={`block cursor-zoom-in ${buttonClassName}`}>
        {/* eslint-disable-next-line @next/next/no-img-element -- obraz dowodowy z API artefaktów */}
        <img src={src} alt={alt} loading="lazy" onError={onError} className={className} />
        <span className="sr-only"> (powiększ)</span>
      </button>
      <dialog ref={ref} aria-label={alt} onClose={() => setOpen(false)}
        onClick={(event) => { if (event.target === event.currentTarget) setOpen(false); }}
        className="m-auto h-dvh max-h-dvh w-screen max-w-none border-0 bg-transparent p-0 backdrop:bg-black/80">
        {open && <div className="flex h-full w-full flex-col items-center justify-center gap-2 p-3 sm:p-6" onClick={(event) => { if (event.target === event.currentTarget) setOpen(false); }}>
          <div className="flex w-full max-w-[96rem] items-center justify-end gap-3">
            <a href={src} target="_blank" rel="noreferrer" className="rounded bg-white px-3 py-2 text-sm text-neutral-900 underline">Otwórz w nowej karcie</a>
            <button type="button" autoFocus onClick={() => setOpen(false)} aria-label="Zamknij podgląd"
              className="rounded bg-white px-4 py-2 text-sm font-semibold text-neutral-900">Zamknij</button>
          </div>
          {/* eslint-disable-next-line @next/next/no-img-element -- obraz dowodowy z API artefaktów */}
          <img src={src} alt={alt} className="min-h-0 max-w-full flex-1 rounded bg-white object-contain" />
        </div>}
      </dialog>
    </>
  );
}
