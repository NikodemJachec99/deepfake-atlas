// Znak SCAM DNA: pasma genomu reklamy w kolorach rodzin śladów (ten sam rysunek co favicon w app/icon.svg).
export function LogoMark({ size = 28 }: { size?: number }) {
  return <svg viewBox="0 0 32 32" width={size} height={size} aria-hidden className="shrink-0">
    <rect width="32" height="32" rx="7" fill="#10203a" />
    <rect x="5" y="12" width="3" height="8" rx="1.5" fill="#3d9be0" />
    <rect x="10" y="7" width="3" height="18" rx="1.5" fill="#e0a12b" />
    <rect x="14.5" y="10" width="3" height="12" rx="1.5" fill="#25b48a" />
    <rect x="19" y="7" width="3" height="18" rx="1.5" fill="#ef7a3c" />
    <rect x="24" y="12" width="3" height="8" rx="1.5" fill="#d26fa9" />
  </svg>;
}

export function Logo({ compact = false, onDark = false }: { compact?: boolean; onDark?: boolean }) {
  return <span className="inline-flex items-center gap-2.5">
    <LogoMark size={compact ? 24 : 30} />
    <span className={`${compact ? "text-base" : "text-lg"} font-bold tracking-tight ${onDark ? "text-white" : ""}`}>SCAM <span className={`font-semibold ${onDark ? "text-[#c3cee0]" : "text-muted"}`}>DNA</span></span>
  </span>;
}
