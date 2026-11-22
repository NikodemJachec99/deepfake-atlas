"use client";

// Komponenty systemu projektowego: panel, przycisk, znaczniki, miernik pewności, pasek rodzin, stany puste.

import { AlertTriangle, Loader2 } from "lucide-react";
import Link from "next/link";
import { useRef } from "react";

import { FAMILY_LABELS, RELATION_LABELS, type Family, type Relation, type Verdict } from "@/lib/api";
import { FAMILIES, RELATION_HINT, VERDICT_LABELS, bits, famVar, groupId, prob } from "@/lib/format";
import { useStored } from "@/lib/hooks";

export const cx = (...parts: (string | false | null | undefined)[]) => parts.filter(Boolean).join(" ");

export function Panel({
  title,
  actions,
  children,
  className,
  bodyClassName,
}: {
  title?: React.ReactNode;
  actions?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  bodyClassName?: string;
}) {
  return (
    <section className={cx("flex min-h-0 min-w-0 flex-col bg-raised", className)}>
      {title !== undefined && (
        <header className="flex h-9 shrink-0 items-center justify-between gap-2 border-b border-line bg-panel px-3">
          <h2 className="truncate font-semibold">{title}</h2>
          {actions && <div className="flex items-center gap-1">{actions}</div>}
        </header>
      )}
      <div className={cx("min-h-0 flex-1 overflow-auto", bodyClassName)}>{children}</div>
    </section>
  );
}

export function Btn({
  variant = "default",
  active,
  className,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "default" | "primary" | "ghost"; active?: boolean }) {
  return (
    <button
      type="button"
      {...props}
      className={cx(
        "inline-flex h-6 shrink-0 items-center justify-center gap-1.5 rounded-lg border px-3 text-[0.92rem] font-medium whitespace-nowrap transition-colors duration-150 disabled:opacity-40",
        variant === "primary" && "border-accent bg-accent font-medium text-on-accent hover:brightness-110",
        variant === "default" && "border-line-strong bg-raised hover:bg-hover",
        variant === "ghost" && "border-transparent text-muted hover:bg-hover hover:text-fg",
        active && "border-accent! bg-accent-soft! text-fg!",
        className,
      )}
    />
  );
}

export function Tabs<T extends string>({ value, onChange, items }: { value: T; onChange: (value: T) => void; items: { id: T; label: React.ReactNode }[] }) {
  return (
    <div role="tablist" className="flex h-9 shrink-0 items-stretch overflow-x-auto border-b border-line bg-panel">
      {items.map((item) => (
        <button
          key={item.id}
          role="tab"
          type="button"
          aria-selected={value === item.id}
          onClick={() => onChange(item.id)}
          className={cx(
            "cap shrink-0 whitespace-nowrap border-r border-line px-3",
            value === item.id ? "bg-raised text-fg! shadow-[inset_0_-2px_0_var(--accent)]" : "hover:bg-hover",
          )}
        >
          {item.label}
        </button>
      ))}
    </div>
  );
}

export function Mono({ children, className, title }: { children: React.ReactNode; className?: string; title?: string }) {
  return (
    <span title={title} className={cx("font-mono text-[0.92rem]", className)}>
      {children}
    </span>
  );
}

export function Tag({ children, tone = "neutral", title }: { children: React.ReactNode; tone?: "neutral" | "accent" | "confirmed" | "unsure" | "rejected" | "new"; title?: string }) {
  const tones = {
    neutral: "border-line-strong text-muted",
    accent: "border-accent text-accent",
    confirmed: "border-confirmed text-confirmed",
    unsure: "border-unsure text-unsure",
    rejected: "border-rejected text-rejected",
    new: "border-new text-new",
  };
  return (
    <span title={title} className={cx("inline-flex h-[18px] shrink-0 items-center rounded-sm border px-1 text-xs tracking-wide uppercase", tones[tone])}>
      {children}
    </span>
  );
}

export function FamilyDot({ family, size = 8 }: { family: Family | null | undefined; size?: number }) {
  return <span aria-hidden className="inline-block shrink-0 rounded-[1px]" style={{ width: size, height: size, background: famVar(family) }} />;
}

export function FamilyName({ family }: { family: Family }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <FamilyDot family={family} />
      {FAMILY_LABELS[family]}
    </span>
  );
}

// Udział rodzin markerów w wyniku krawędzi. Szerokość segmentu to bity z API, bez przeliczeń poza proporcją.
export function FamilyBar({ families, legend = false, height = 8 }: { families: Partial<Record<Family, number>>; legend?: boolean; height?: number }) {
  const present = FAMILIES.filter((f) => (families[f] ?? 0) > 0);
  const total = present.reduce((sum, f) => sum + (families[f] ?? 0), 0);
  return (
    <div className="flex min-w-0 flex-col gap-1.5">
      <div className="flex w-full overflow-hidden rounded-[1px] bg-line" style={{ height }} role="img" aria-label="Udział rodzin markerów">
        {present.map((f) => (
          <span key={f} title={`${FAMILY_LABELS[f]}: ${bits(families[f] ?? 0)} bita`} style={{ width: `${((families[f] ?? 0) / total) * 100}%`, background: famVar(f) }} />
        ))}
      </div>
      {legend && (
        <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-muted">
          {present.map((f) => (
            <span key={f} className="inline-flex items-center gap-1">
              <FamilyDot family={f} size={7} />
              {FAMILY_LABELS[f]} <Mono className="text-fg">{bits(families[f] ?? 0)}</Mono>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

// Miernik pewności: liczba z dwoma miejscami po przecinku i pasek z progami 0,50 oraz 0,90 (próg wspólnego źródła).
export function Meter({ value, width = 72 }: { value: number; width?: number }) {
  const tone = value >= 0.9 ? "var(--fg)" : value >= 0.5 ? "var(--st-unsure)" : "var(--faint)";
  return (
    <span className="inline-flex items-center gap-2" title={`Wynik modelu (niekalibrowany) ${prob(value)}. Progi: 0,50 i 0,90`}>
      <Mono className="w-[2.6em] text-right">{prob(value)}</Mono>
      <span className="relative h-1.5 rounded-[1px] bg-line" style={{ width }}>
        <span className="absolute inset-y-0 left-0 rounded-[1px]" style={{ width: `${Math.max(0, Math.min(1, value)) * 100}%`, background: tone }} />
        <span className="absolute -inset-y-0.5 left-1/2 w-px bg-line-strong" />
        <span className="absolute -inset-y-0.5 left-[90%] w-px bg-line-strong" />
      </span>
    </span>
  );
}

// Trzy relacje są zawsze rozróżnialne: gruba ciągła, cienka ciągła, przerywana.
export function RelationLine({ relation, color = "currentColor", width = 26 }: { relation: Relation; color?: string; width?: number }) {
  return (
    <svg width={width} height={8} aria-hidden className="shrink-0">
      <line
        x1={0}
        x2={width}
        y1={4}
        y2={4}
        stroke={color}
        strokeWidth={relation === "same_campaign" ? 3.5 : 1.5}
        strokeDasharray={relation === "similar" ? "4 3" : undefined}
      />
    </svg>
  );
}

export function RelationTag({ relation, duplicate }: { relation: Relation; duplicate?: boolean }) {
  return (
    <span className="inline-flex items-center gap-1.5" title={RELATION_HINT[relation]}>
      <RelationLine relation={relation} />
      <span>{RELATION_LABELS[relation]}</span>
      {duplicate && <Tag tone="new" title="Ta sama strona przechwycona ponownie">Duplikat</Tag>}
    </span>
  );
}

export function VerdictTag({ verdict }: { verdict: Verdict }) {
  if (!verdict) return <span className="text-faint">bez decyzji</span>;
  return <Tag tone={verdict}>{VERDICT_LABELS[verdict]}</Tag>;
}

export function GroupLink({ group }: { group: string | null | undefined }) {
  const id = groupId(group);
  if (!group || id === null) return <span className="text-faint">brak</span>;
  const operator = group.startsWith("O");
  return (
    <Link href={`/${operator ? "operators" : "campaigns"}/${id}`} className="font-mono text-[0.92rem] text-accent hover:underline" title={operator ? "Operator" : "Kampania"}>
      {group}
    </Link>
  );
}

export function Empty({ title, children }: { title: string; children?: React.ReactNode }) {
  return (
    <div className="flex h-full min-h-28 flex-col justify-center gap-1.5 p-6">
      <p className="text-base font-medium text-fg">{title}</p>
      {children && <div className="max-w-[60ch] text-muted">{children}</div>}
    </div>
  );
}

export function Loading({ label = "Pobieranie danych" }: { label?: string }) {
  return (
    <div className="flex h-full min-h-20 items-center justify-center gap-2 p-6 text-muted" role="status">
      <Loader2 size={16} className="animate-spin text-accent" aria-hidden />
      {label}
    </div>
  );
}

export function ErrorBox({ message, onRetry, missing }: {
  message: string;
  onRetry?: () => void;
  missing?: { description: string; href: string; link: string };
}) {
  return (
    <div className="m-3 flex items-start gap-3 rounded-lg border border-rejected/60 bg-rejected/5 p-3" role="alert">
      <AlertTriangle size={14} className="mt-0.5 shrink-0 text-rejected" />
      <div className="min-w-0 flex-1">
        <p>{missing?.description ?? (/^API 5\d\d:|Brak połączenia z API/.test(message) ? "Backend chwilowo niedostępny." : "Nie udało się pobrać danych.")}</p>
        {missing && <Link href={missing.href} className="text-accent underline">{missing.link}</Link>}
        <details><summary>Szczegóły techniczne</summary>
        <p className="font-mono text-xs break-words text-muted">{message}{message.startsWith("Brak połączenia z API") && " Sprawdź dostępność backendu i konfigurację NEXT_PUBLIC_API_URL."}</p></details>
      </div>
      {onRetry && !missing && <Btn onClick={onRetry}>Ponów</Btn>}
    </div>
  );
}

export function Kbd({ children }: { children: React.ReactNode }) {
  return <kbd className="inline-flex h-4 min-w-4 items-center justify-center rounded-sm border border-line-strong px-1 font-mono text-xs text-muted">{children}</kbd>;
}

export function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex min-w-0 flex-wrap gap-x-2 py-0.5">
      <dt className="w-28 min-w-min shrink-0 text-muted">{label}</dt>
      <dd className="min-w-[min(100%,8rem)] flex-1 break-words">{children}</dd>
    </div>
  );
}

// Dwa panele z uchwytem do zmiany rozmiaru. Rozmiar panelu `fixed` jest w pikselach i zapamiętywany.
export function Split({
  id,
  dir,
  fixed,
  initial,
  min = 160,
  max = 900,
  children,
}: {
  id: string;
  dir: "row" | "col";
  fixed: "first" | "second";
  initial: number;
  min?: number;
  max?: number;
  children: [React.ReactNode, React.ReactNode];
}) {
  const [stored, setStored] = useStored(`scamdna.split.${id}`, String(initial));
  const size = Math.max(min, Math.min(max, Number(stored) || initial));
  const drag = useRef<{ start: number; size: number } | null>(null);
  const row = dir === "row";

  function onPointerDown(event: React.PointerEvent<HTMLDivElement>) {
    drag.current = { start: row ? event.clientX : event.clientY, size };
    event.currentTarget.setPointerCapture(event.pointerId);
  }
  function onPointerMove(event: React.PointerEvent<HTMLDivElement>) {
    if (!drag.current) return;
    const delta = (row ? event.clientX : event.clientY) - drag.current.start;
    const next = drag.current.size + (fixed === "first" ? delta : -delta);
    setStored(String(Math.round(Math.max(min, Math.min(max, next)))));
  }
  function onKeyDown(event: React.KeyboardEvent) {
    const step = (row ? { ArrowLeft: -16, ArrowRight: 16 } : { ArrowUp: -16, ArrowDown: 16 })[event.key as "ArrowLeft"] as number | undefined;
    if (step) setStored(String(Math.max(min, Math.min(max, size + (fixed === "first" ? step : -step)))));
  }

  const fixedStyle = row ? { width: size } : { height: size };
  return (
    <div data-split={id} className={cx("flex min-h-0 min-w-0 flex-1", row ? "flex-row" : "flex-col")}>
      <div className={cx("flex min-h-0 min-w-0", fixed === "first" ? "shrink-0" : "flex-1")} style={fixed === "first" ? fixedStyle : undefined}>
        {children[0]}
      </div>
      <div
        role="separator"
        tabIndex={0}
        aria-orientation={row ? "vertical" : "horizontal"}
        aria-label="Zmień rozmiar panelu"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={() => (drag.current = null)}
        onKeyDown={onKeyDown}
        className={cx("no-print shrink-0 bg-line transition-colors duration-150 hover:bg-accent focus-visible:bg-accent", row ? "w-px cursor-col-resize px-px" : "h-px cursor-row-resize py-px")}
      />
      <div className={cx("flex min-h-0 min-w-0", fixed === "second" ? "shrink-0" : "flex-1")} style={fixed === "second" ? fixedStyle : undefined}>
        {children[1]}
      </div>
    </div>
  );
}
