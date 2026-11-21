"use client";

import { Archive, Compass, FolderOpen, Network, UsersRound } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { api, RELATION_LABELS, type Stats } from "@/lib/api";

const sections: Record<string, string> = {
  "/": "Discovery", "/investigation": "Investigation", "/archive": "Archiwum",
  "/operators": "Operatorzy", "/campaigns": "Kampanie", "/ads": "Reklamy",
};

const navigation = [
  { href: "/", Icon: Compass }, { href: "/investigation", Icon: Network },
  { href: "/archive", Icon: Archive }, { href: "/operators", Icon: UsersRound },
  { href: "/campaigns", Icon: FolderOpen },
];

export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [, section, id] = pathname.split("/");
  const root = "/" + section;
  const [stats, setStats] = useState<Stats | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    async function refresh() {
      try {
        const next = await api.stats();
        if (active) { setStats(next); setFailed(false); }
      } catch {
        if (active) setFailed(true);
      } finally {
        if (active) timer = setTimeout(refresh, 20000);
      }
    }
    void refresh();
    return () => { active = false; clearTimeout(timer); };
  }, []);
  return <div className="flex h-dvh flex-col bg-bg text-fg">
    <div className="flex min-h-0 flex-1">
      <nav aria-label="Nawigacja główna" className="flex shrink-0 flex-col gap-1 overflow-auto border-r border-line atlas-sidebar bg-panel p-1.5 md:p-3">
        <strong className="hidden px-2 py-3 text-xl tracking-tight md:block">Deepfake Atlas</strong>
        {navigation.map(({ href, Icon }) =>
          <Link key={href} href={href} aria-current={root === href ? "page" : undefined}
            title={sections[href]} className="flex items-center gap-3 rounded-lg px-2 py-2.5 font-medium hover:bg-hover aria-[current=page]:bg-accent-soft aria-[current=page]:text-accent"><Icon size={16} aria-hidden /><span className="sr-only md:not-sr-only">{sections[href]}</span></Link>)}
      </nav>
      <div className="flex min-w-0 flex-1 flex-col">
        {root !== "/investigation" && <header className="border-b border-line bg-panel/95 px-4 py-2.5 font-semibold backdrop-blur">{sections[root] ?? "SCAM DNA"}{id && " › #" + id}</header>}
        <div className="flex min-h-0 flex-1 flex-col overflow-auto">{children}</div>
      </div>
    </div>
    <footer aria-label="Stan korpusu" className="flex shrink-0 gap-5 overflow-x-auto whitespace-nowrap text-xs text-muted border-t border-line bg-panel px-3 py-1 font-mono">
      {failed ? "Statystyki korpusu niedostępne" : !stats ? "Pobieranie statystyk…" : <>
        <span>Reklamy {stats.ads}</span><span>Kampanie {stats.campaigns}</span><span>Operatorzy {stats.operators}</span>
        {Object.entries(RELATION_LABELS).map(([key, label]) => <span key={key}>{label} {stats.edges[key as keyof Stats["edges"]] ?? 0}</span>)}
        <span>Lista CERT {stats.cert_pl_listed}</span><span>Ostatnia analiza {stats.last_analysis ? new Date(stats.last_analysis).toLocaleString("pl-PL") : "brak"}</span>
      </>}
    </footer>
  </div>;
}

export interface Crumb {
  label: React.ReactNode;
  href?: string;
}

export function TopBar({ crumbs }: { crumbs: Crumb[] }) {
  return <nav aria-label="Ścieżka śledztwa" className="flex shrink-0 gap-2 border-b border-line bg-panel/95 px-3 py-2.5 font-medium backdrop-blur">
    {crumbs.map((crumb, index) => <span key={index}>{index > 0 && " › "}
      {crumb.href ? <Link href={crumb.href}>{crumb.label}</Link> : crumb.label}
    </span>)}
  </nav>;
}
