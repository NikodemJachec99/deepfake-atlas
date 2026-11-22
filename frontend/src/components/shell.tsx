"use client";

import { History, ClipboardCheck, ScanSearch, Scale, Bell, Archive, Compass, FolderOpen, Network, UsersRound, Plus, Menu, X, ChevronRight, type LucideIcon } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { api, RELATION_LABELS, type Stats } from "@/lib/api";

import { dateTime } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import { Expert, ExpertProvider, ExpertToggle } from "@/lib/expert";

const sections: Record<string, string> = {
  "/review": "Do oceny", "/premises": "Zakwestionowania", "/hunt": "Łowca domen", "/": "Analiza", "/investigation": "Śledztwo", "/archive": "Archiwum",
  "/operators": "Operatorzy", "/campaigns": "Kampanie", "/ads": "Reklamy", "/alerts": "Alerty", "/weights": "Wagi markerów",
};

interface NavLink { href: string; Icon: LucideIcon; hint: string }
interface NavGroup { label: string; quiet?: boolean; links: NavLink[] }

// Grupy według zadań: najpierw codzienna praca, na końcu narzędzia modelu.
const navigation: NavGroup[] = [
  { label: "", links: [
    { href: "/review", Icon: ClipboardCheck, hint: "Pary reklam czekające na decyzję" },
    { href: "/", Icon: Compass, hint: "Dodaj materiał i zobacz, z czym się łączy" },
  ] },
  { label: "Powiązania", links: [
    { href: "/investigation", Icon: Network, hint: "Graf i lista powiązań" },
    { href: "/campaigns", Icon: FolderOpen, hint: "Grupy reklam jednej kampanii" },
    { href: "/operators", Icon: UsersRound, hint: "Grupy kampanii jednego zaplecza" },
    { href: "/archive", Icon: Archive, hint: "Wszystkie przeanalizowane reklamy" },
  ] },
  { label: "Monitoring", links: [
    { href: "/alerts", Icon: Bell, hint: "Nowe reklamy w znanych grupach" },
    { href: "/hunt", Icon: ScanSearch, hint: "Domeny podobne do znanych" },
  ] },
  { label: "Model i jakość", quiet: true, links: [
    { href: "/weights", Icon: Scale, hint: "Siła poszczególnych śladów" },
    { href: "/premises", Icon: History, hint: "Historia zakwestionowanych śladów" },
  ] },
];

// Na telefonie dolny pasek ma cztery najczęstsze miejsca, reszta jest w menu „Więcej”.
const mobileTabs = ["/review", "/", "/investigation", "/alerts"];
const mobileLabels: Record<string, string> = { "/investigation": "Śledztwo" };

function Badge({ value, tone = "accent" }: { value: number; tone?: "accent" | "alert" }) {
  return <span className={tone === "alert"
    ? "ml-auto min-w-5 rounded-full bg-rejected px-1.5 text-center text-xs font-semibold leading-5 tabular-nums text-on-accent"
    : "ml-auto min-w-5 rounded-full bg-accent-soft px-1.5 text-center text-xs font-semibold leading-5 tabular-nums text-accent"}>{value}</span>;
}

export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [, section, id] = pathname.split("/");
  const root = "/" + section;
  const active = root === "/ads" ? "/archive" : root;
  // Nagłówek nie powtarza tytułu strony: okruszki tylko na kartach szczegółów (lista › element).
  const parents: Record<string, { href: string; label: string }> = { ads: { href: "/archive", label: "Archiwum" }, campaigns: { href: "/campaigns", label: "Kampanie" }, operators: { href: "/operators", label: "Operatorzy" } };
  const parent = id ? parents[section] : undefined;
  const groupKey = parent && section !== "ads" && /^\d+$/.test(id) ? `shell-${section}-${id}` : null;
  const group = useApi(groupKey, () => section === "operators" ? api.operator(Number(id)) : api.campaign(Number(id)));
  const current = section === "ads" ? `Reklama #${id}` : group.data?.key ?? `#${id}`;
  useEffect(() => {
    const singular: Record<string, string> = { ads: "Reklama", operators: "Operator", campaigns: "Kampania" };
    const title = id && singular[section] ? `${singular[section]} #${id}` : sections[root];
    document.title = title ? `${title} · SCAM DNA` : "SCAM DNA";
  }, [section, root, id]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [failed, setFailed] = useState(false);
  const [revision, setRevision] = useState(0);
  const [menu, setMenu] = useState(false);
  const [menuPath, setMenuPath] = useState(pathname);
  if (menuPath !== pathname) {
    setMenuPath(pathname);
    setMenu(false);
  }
  useEffect(() => {
    if (!menu) return;
    const close = (event: KeyboardEvent) => { if (event.key === "Escape") setMenu(false); };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [menu]);
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

  function badge(href: string) {
    if (!stats || failed) return null;
    if (href === "/review" && stats.review_pending > 0) return <Badge value={stats.review_pending} />;
    if (href === "/alerts" && stats.alerts_unseen > 0) return <Badge value={stats.alerts_unseen} tone="alert" />;
    return null;
  }

  const linkClass = "flex items-center gap-3 rounded-lg px-3 font-medium text-fg transition-colors duration-150 hover:bg-hover aria-[current=page]:bg-accent-soft aria-[current=page]:text-accent";

  return <ExpertProvider><div className="flex h-dvh flex-col bg-bg text-fg">
    <div className="flex min-h-0 flex-1">
      <nav aria-label="Nawigacja główna" className="atlas-sidebar hidden shrink-0 flex-col gap-4 overflow-auto border-r border-line px-3 pt-4 pb-3 md:flex">
        <Link href="/" className="px-3 pb-1 text-lg font-semibold tracking-tight">SCAM DNA</Link>
        {navigation.map(({ label, quiet, links }) => <div key={label || "main"} className={quiet ? "mt-auto flex flex-col gap-0.5 border-t border-line pt-3" : "flex flex-col gap-0.5"}>
          {label && <p className="px-3 pb-1 text-xs font-medium text-muted">{label}</p>}
          {links.map(({ href, Icon, hint }) =>
            <Link key={href} href={href} aria-current={active === href ? "page" : undefined} title={hint}
              className={`${linkClass} ${quiet ? "h-9 text-sm text-muted" : "h-10"}`}>
              <Icon size={quiet ? 15 : 17} className="shrink-0" aria-hidden />
              <span className="min-w-0 truncate">{sections[href]}</span>
              {badge(href)}
            </Link>)}
        </div>)}
      </nav>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-13 shrink-0 items-center justify-between gap-3 border-b border-line bg-bg px-4 md:px-6">
          <nav aria-label="Ścieżka" className="flex min-w-0 items-center gap-2 font-medium">
            {!parent && <Link href="/" className="shrink-0 font-semibold tracking-tight md:hidden">SCAM DNA</Link>}
            {parent && <>
              <Link href={parent.href} className="shrink-0 rounded text-muted hover:text-accent hover:underline">{parent.label}</Link>
              <ChevronRight size={15} aria-hidden className="shrink-0 text-faint" />
              <span aria-current="page" className="min-w-0 truncate font-semibold">{current}</span>
            </>}
          </nav>
          <div className="flex shrink-0 items-center gap-4">
            <span className="hidden md:block"><ExpertToggle /></span>
            {root !== "/" && <Link href="/#input-kind" className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-line-strong px-3 text-sm font-medium text-accent hover:bg-hover">
              <Plus size={15} aria-hidden /><span className="hidden sm:inline">Dodaj materiał</span><span className="sm:hidden">Dodaj</span>
            </Link>}
          </div>
        </header>
        <div className="flex min-h-0 flex-1 flex-col overflow-auto">{children}</div>
      </div>
    </div>
    <Expert>
      <footer aria-label="Stan korpusu" className="hidden shrink-0 gap-x-5 overflow-x-auto whitespace-nowrap border-t border-line bg-panel px-3 py-1 font-mono text-xs text-muted md:flex md:flex-wrap">
        {failed ? "Statystyki korpusu niedostępne" : !stats ? "Pobieranie statystyk…" : <>
          <Link href="/alerts" className="text-accent">Nieprzejrzane alerty {stats.alerts_unseen ?? "—"}</Link><span>Reklamy {stats.ads}</span><span>Kampanie {stats.campaigns}</span><span>Operatorzy {stats.operators}</span>
          {Object.entries(RELATION_LABELS).map(([key, label]) => <span key={key}>Powiązania · {label.toLocaleLowerCase("pl")} {stats.edges[key as keyof Stats["edges"]] ?? 0}</span>)}
          <span>Lista CERT {stats.cert_pl_listed}</span><span>Ostatnia analiza {stats.last_analysis ? dateTime(stats.last_analysis) : "brak"}</span>
        </>}
      </footer>
    </Expert>
    {menu && <div className="fixed inset-0 z-40 bg-fg/20 md:hidden" onClick={() => setMenu(false)} aria-hidden />}
    {menu && <div id="mobile-menu" role="dialog" aria-label="Wszystkie widoki" className="fixed inset-x-0 bottom-16 z-50 max-h-[75dvh] overflow-auto rounded-t-2xl border-t border-line bg-bg px-4 pt-4 pb-3 shadow-[0_-8px_24px_rgb(0_0_0/0.12)] md:hidden">
      <div className="mb-3 flex items-center justify-between gap-3 border-b border-line pb-3">
        <ExpertToggle />
        <button type="button" onClick={() => setMenu(false)} aria-label="Zamknij menu" className="inline-flex size-10 items-center justify-center rounded-lg hover:bg-hover"><X size={18} aria-hidden /></button>
      </div>
      {navigation.map(({ label, links }) => <div key={label || "main"} className="mb-2">
        {label && <p className="px-3 pt-2 pb-1 text-xs font-medium text-muted">{label}</p>}
        {links.map(({ href, Icon, hint }) => <Link key={href} href={href} aria-current={active === href ? "page" : undefined} className={`${linkClass} min-h-12 py-1.5`}>
          <Icon size={18} className="shrink-0" aria-hidden />
          <span className="flex min-w-0 flex-col"><span>{sections[href]}</span><span className="text-xs font-normal text-muted">{hint}</span></span>
          {badge(href)}
        </Link>)}
      </div>)}
    </div>}
    <nav aria-label="Nawigacja na telefonie" className="grid h-16 shrink-0 grid-cols-5 border-t border-line bg-bg md:hidden">
      {mobileTabs.map(href => {
        const { Icon } = navigation.flatMap(group => group.links).find(link => link.href === href)!;
        const count = !stats || failed ? 0 : href === "/review" ? stats.review_pending : href === "/alerts" ? stats.alerts_unseen : 0;
        return <Link key={href} href={href} aria-current={active === href ? "page" : undefined}
          className="relative flex flex-col items-center justify-center gap-1 text-xs font-medium text-muted focus-visible:-outline-offset-2 before:absolute before:inset-x-4 before:top-0 before:h-0.5 before:rounded-full aria-[current=page]:font-semibold aria-[current=page]:text-accent aria-[current=page]:before:bg-accent">
          <Icon size={20} aria-hidden />
          <span>{mobileLabels[href] ?? sections[href]}</span>
          {count > 0 && <span className={`absolute top-1.5 left-1/2 ml-2 min-w-4 rounded-full px-1 text-center text-[11px] font-semibold leading-4 tabular-nums text-on-accent ${href === "/alerts" ? "bg-rejected" : "bg-accent"}`}>{count}</span>}
        </Link>;
      })}
      <button type="button" onClick={() => setMenu(value => !value)} aria-expanded={menu} aria-controls="mobile-menu"
        className="flex flex-col items-center justify-center gap-1 text-xs font-medium text-muted focus-visible:-outline-offset-2 aria-expanded:font-semibold aria-expanded:text-accent">
        <Menu size={20} aria-hidden /><span>Więcej</span>
      </button>
    </nav>
  </div></ExpertProvider>;
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
