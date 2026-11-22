"use client";

import { History, ClipboardCheck, ScanSearch, Scale, Bell, Archive, Compass, FolderOpen, Network, UsersRound } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { api, RELATION_LABELS, type Stats } from "@/lib/api";

import { dateTime } from "@/lib/format";

const sections: Record<string, string> = {
  "/review": "Do oceny", "/premises": "Historia zakwestionowań", "/hunt": "Łowca domen", "/": "Analiza", "/investigation": "Śledztwo", "/archive": "Archiwum",
  "/operators": "Operatorzy", "/campaigns": "Kampanie", "/ads": "Reklamy", "/alerts": "Alerty", "/weights": "Wagi markerów",
};

const compactSections: Record<string, string> = { "/hunt": "Domeny", "/weights": "Wagi", "/premises": "Historia" };

const navigation = [
  { label: "", links: [{ href: "/review", Icon: ClipboardCheck }] },
  { label: "Materiały", links: [{ href: "/", Icon: Compass }, { href: "/archive", Icon: Archive }] },
  { label: "Powiązania", links: [{ href: "/investigation", Icon: Network }, { href: "/campaigns", Icon: FolderOpen }, { href: "/operators", Icon: UsersRound }] },
  { label: "Monitoring", links: [{ href: "/alerts", Icon: Bell }, { href: "/hunt", Icon: ScanSearch }] },
  { label: "Model i jakość", links: [{ href: "/weights", Icon: Scale }, { href: "/premises", Icon: History }] },
];

export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [, section, id] = pathname.split("/");
  const root = "/" + section;
  useEffect(() => {
    const singular: Record<string, string> = { ads: "Reklama", operators: "Operator", campaigns: "Kampania" };
    const title = id && singular[section] ? `${singular[section]} #${id}` : sections[root];
    document.title = title ? `${title} · SCAM DNA` : "SCAM DNA";
  }, [section, root, id]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [failed, setFailed] = useState(false);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const refresh = () => setRevision(value => value + 1);
    window.addEventListener("atlas-alerts-updated", refresh);
    return () => window.removeEventListener("atlas-alerts-updated", refresh);
  }, []);
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
  }, [revision]);
  return <div className="flex h-dvh flex-col bg-bg text-fg">
    <div className="flex min-h-0 flex-1">
      <nav aria-label="Nawigacja główna" className="flex shrink-0 flex-col gap-1 overflow-auto border-r border-line atlas-sidebar bg-panel p-1.5 md:p-3">
        <strong className="hidden px-2 py-3 text-xl tracking-tight md:block">SCAM DNA</strong>
        {navigation.map(({ label, links }) => <div key={label} className="border-b border-line pb-1 last:border-0">
          {label && <p className="hidden px-2 pt-2 text-xs text-muted md:block">{label}</p>}
          {links.map(({ href, Icon }) =>
          <Link key={href} href={href} aria-current={root === href ? "page" : undefined}
            aria-label={sections[href]} title={sections[href]} className="flex flex-col items-center gap-1 text-xs md:flex-row md:gap-3 md:text-base rounded-lg px-2 py-2.5 font-medium hover:bg-hover aria-[current=page]:bg-accent-soft aria-[current=page]:text-accent"><Icon size={16} className="shrink-0" aria-hidden /><span aria-hidden className="md:hidden">{compactSections[href] ?? sections[href]}</span><span className="hidden md:inline">{href === "/premises" ? "Zakwestionowania" : sections[href]}</span>
            {href === "/review" && stats && !failed && <span className="rounded bg-accent-soft px-1 text-xs tabular-nums text-accent">{stats.review_pending}</span>}
          </Link>)}</div>)}
      </nav>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between gap-2 border-b border-line bg-panel/95 px-4 py-2 font-semibold backdrop-blur">
          <span>{sections[root] ?? "SCAM DNA"}{id && " › #" + id}</span>
          <Link href="/#input-kind" className="rounded border border-line-strong px-3 py-1.5 text-sm text-accent">Dodaj materiał</Link>
        </header>
        <div className="flex min-h-0 flex-1 flex-col overflow-auto">{children}</div>
      </div>
    </div>
    <footer aria-label="Stan korpusu" className="flex shrink-0 gap-x-5 overflow-x-auto whitespace-nowrap md:flex-wrap text-xs text-muted border-t border-line bg-panel px-3 py-1 font-mono">
      {failed ? "Statystyki korpusu niedostępne" : !stats ? "Pobieranie statystyk…" : <>
        <Link href="/alerts" className="text-accent">Nieprzejrzane alerty {stats.alerts_unseen ?? "—"}</Link><span>Reklamy {stats.ads}</span><span>Kampanie {stats.campaigns}</span><span>Operatorzy {stats.operators}</span>
        {Object.entries(RELATION_LABELS).map(([key, label]) => <span key={key}>Powiązania · {label.toLocaleLowerCase("pl")} {stats.edges[key as keyof Stats["edges"]] ?? 0}</span>)}
        <span>Lista CERT {stats.cert_pl_listed}</span><span>Ostatnia analiza {stats.last_analysis ? dateTime(stats.last_analysis) : "brak"}</span>
      </>}
    </footer>
  </div>;
}

export interface Crumb {
  label: React.ReactNode;
  href?: string;
}

export function TopBar({ crumbs }: { crumbs: Crumb[] }) {
  return <nav aria-label="Ścieżka śledztwa" className="flex shrink-0 flex-wrap gap-x-2 border-b border-line bg-panel/95 px-3 py-2.5 font-medium backdrop-blur">
    {crumbs.map((crumb, index) => <span key={index}>{index > 0 && " › "}
      {crumb.href ? <Link href={crumb.href}>{crumb.label}</Link> : crumb.label}
    </span>)}
  </nav>;
}
