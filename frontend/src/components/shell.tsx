"use client";

// Szkielet aplikacji: lewa szyna trybów, górny pasek z okruszkami, pasek stanu, paleta poleceń.

import {
  Archive,
  Bell,
  Boxes,
  ChevronRight,
  Database,
  FileText,
  FlaskConical,
  Gauge,
  History,
  Loader2,
  Moon,
  ScanSearch,
  Search,
  Settings,
  Sun,
  Tags,
  Users,
  Waypoints,
  type LucideIcon,
} from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useDeferredValue, useEffect, useMemo, useRef, useState } from "react";

import { API_URL, RELATION_LABELS, api } from "@/lib/api";
import { useAnalyses } from "@/lib/analysis-store";
import { RELATIONS, adTitle, dateTime, hostOf } from "@/lib/format";
import { isTyping, useApi, useHotkey, useStored } from "@/lib/hooks";

import { Kbd, Mono, cx } from "./ui";

interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  planned?: boolean;
}

const MODES: NavItem[] = [
  { href: "/", label: "Discovery", icon: ScanSearch },
  { href: "/investigation", label: "Investigation", icon: Waypoints },
  { href: "/evolution", label: "Evolution", icon: History, planned: true },
];

const BACK_OFFICE: NavItem[] = [
  { href: "/archive", label: "Archiwum", icon: Archive },
  { href: "/groups", label: "Operatorzy i kampanie", icon: Boxes },
  { href: "/people", label: "Osoby", icon: Users, planned: true },
  { href: "/sources", label: "Źródła i skany", icon: Database, planned: true },
  { href: "/labeling", label: "Etykietowanie", icon: Tags, planned: true },
  { href: "/alerts", label: "Alerty", icon: Bell, planned: true },
  { href: "/sandbox", label: "Piaskownica", icon: FlaskConical, planned: true },
  { href: "/reports", label: "Raporty", icon: FileText, planned: true },
  { href: "/quality", label: "Jakość modelu", icon: Gauge, planned: true },
  { href: "/admin", label: "Administracja", icon: Settings, planned: true },
];

const GROUP_PATHS = ["/groups", "/operator", "/campaign"];
const isActive = (pathname: string, href: string) =>
  href === "/" ? pathname === "/" : href === "/groups" ? GROUP_PATHS.some((p) => pathname.startsWith(p)) : href === "/archive" ? pathname.startsWith("/archive") || pathname.startsWith("/ad") : pathname.startsWith(href);

export function useTheme(): ["dark" | "light", () => void] {
  const [stored, setStored] = useStored("scamdna.theme", "dark");
  const theme = stored === "light" ? "light" : "dark";
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);
  return [theme, () => setStored(theme === "dark" ? "light" : "dark")];
}

function RailLink({ item, active }: { item: NavItem; active: boolean }) {
  const Icon = item.icon;
  return (
    <Link
      href={item.href}
      title={item.planned ? `${item.label} (ekran zaprojektowany, API jeszcze nie istnieje)` : item.label}
      aria-label={item.label}
      aria-current={active ? "page" : undefined}
      className={cx(
        "relative flex h-9 w-full items-center justify-center transition-colors duration-150 hover:bg-hover hover:text-fg",
        active ? "bg-raised text-fg shadow-[inset_2px_0_0_var(--accent)]" : item.planned ? "text-faint" : "text-muted",
      )}
    >
      <Icon size={16} strokeWidth={1.6} />
      {item.planned && <span className="absolute top-2 right-2.5 h-1 w-1 rounded-full bg-line-strong" />}
    </Link>
  );
}

export function Rail() {
  const pathname = usePathname();
  return (
    <nav aria-label="Tryby i zaplecze" className="no-print flex w-12 shrink-0 flex-col border-r border-line bg-panel">
      <Link href="/" className="flex h-9 items-center justify-center border-b border-line font-mono text-[0.85rem] font-semibold tracking-tight text-fg" title="SCAM DNA">
        S·D
      </Link>
      {MODES.map((item) => (
        <RailLink key={item.href} item={item} active={isActive(pathname, item.href)} />
      ))}
      <div className="my-1 border-t border-line" />
      {BACK_OFFICE.map((item) => (
        <RailLink key={item.href} item={item} active={isActive(pathname, item.href)} />
      ))}
    </nav>
  );
}

export interface Crumb {
  label: React.ReactNode;
  href?: string;
}

const openPalette = () => window.dispatchEvent(new Event("scamdna:palette"));

export function TopBar({ crumbs, children }: { crumbs: Crumb[]; children?: React.ReactNode }) {
  const [theme, toggleTheme] = useTheme();
  const { running } = useAnalyses();
  return (
    <header className="no-print flex h-9 shrink-0 items-center gap-3 border-b border-line bg-panel px-3">
      <nav aria-label="Okruszki" className="flex min-w-0 items-center gap-1">
        {crumbs.map((crumb, index) => (
          <span key={index} className="flex min-w-0 items-center gap-1">
            {index > 0 && <ChevronRight size={12} className="shrink-0 text-faint" />}
            {crumb.href ? (
              <Link href={crumb.href} className="truncate text-muted hover:text-fg">
                {crumb.label}
              </Link>
            ) : (
              <span className={cx("truncate", index === crumbs.length - 1 ? "text-fg" : "text-muted")}>{crumb.label}</span>
            )}
          </span>
        ))}
      </nav>
      <div className="flex flex-1 items-center justify-end gap-2">
        {children}
        <button
          type="button"
          onClick={openPalette}
          className="flex h-6 w-64 items-center gap-2 rounded-sm border border-line bg-bg px-2 text-muted transition-colors duration-150 hover:border-line-strong"
        >
          <Search size={13} />
          <span className="flex-1 truncate text-left">Szukaj reklamy, kampanii, operatora</span>
          <Kbd>Ctrl K</Kbd>
        </button>
        <Link href="/" className={cx("flex h-6 items-center gap-1.5 rounded-sm px-2", running > 0 ? "text-fg" : "text-faint")} title="Analizy w toku">
          {running > 0 ? <Loader2 size={13} className="animate-spin" /> : <span className="h-1.5 w-1.5 rounded-full bg-line-strong" />}
          <span>Analizy w toku</span>
          <Mono>{running}</Mono>
        </Link>
        <button type="button" onClick={toggleTheme} className="flex h-6 w-6 items-center justify-center rounded-sm text-muted hover:bg-hover hover:text-fg" title={theme === "dark" ? "Motyw jasny" : "Motyw ciemny"} aria-label="Przełącz motyw">
          {theme === "dark" ? <Sun size={14} /> : <Moon size={14} />}
        </button>
        <span className="border-l border-line pl-2 text-faint" title="API działa bez logowania. Role i klucze: API jeszcze nie istnieje.">
          bez logowania
        </span>
      </div>
    </header>
  );
}

function Stat({ label, value, title }: { label: string; value: React.ReactNode; title?: string }) {
  return (
    <span className="flex items-center gap-1.5 border-r border-line px-2" title={title}>
      <span className="text-muted">{label}</span>
      <Mono className="text-fg">{value}</Mono>
    </span>
  );
}

export function StatusBar() {
  const { tick, running, streaming } = useAnalyses();
  const stats = useApi(`stats:${tick}`, api.stats);
  const reload = stats.reload;
  useEffect(() => {
    const timer = window.setInterval(reload, 20000);
    return () => window.clearInterval(timer);
  }, [reload]);
  const s = stats.data;
  return (
    <footer className="no-print flex h-6 shrink-0 items-center border-t border-line bg-panel text-[0.85rem]">
      {s ? (
        <>
          <Stat label="reklamy" value={s.ads} />
          <Stat label="kampanie" value={s.campaigns} />
          <Stat label="operatorzy" value={s.operators} />
          {RELATIONS.map((relation) => (
            <Stat key={relation} label={RELATION_LABELS[relation].toLowerCase()} value={s.edges[relation] ?? 0} title={`Krawędzie: ${RELATION_LABELS[relation]}`} />
          ))}
          <Stat label="na liście CERT" value={s.cert_pl_listed} title="Reklamy, których domena jest na Liście Ostrzeżeń CERT Polska" />
          <Stat label="ostatnia analiza" value={s.last_analysis ? dateTime(s.last_analysis) : "brak"} />
        </>
      ) : (
        <span className="px-2 text-muted">{stats.error ? "Statystyki korpusu niedostępne" : "Pobieranie statystyk"}</span>
      )}
      <span className="flex-1" />
      <Stat label="kolejka" value={running} title="Analizy uruchomione w tej przeglądarce, które jeszcze trwają" />
      <span className="flex items-center gap-1.5 border-r border-line px-2" title="Strumień zdarzeń analizy (SSE)">
        <span className={cx("h-1.5 w-1.5 rounded-full", streaming > 0 ? "pulse bg-new" : "bg-line-strong")} />
        <span className="text-muted">{streaming > 0 ? `strumień otwarty (${streaming})` : "strumień bezczynny"}</span>
      </span>
      <span className="flex items-center gap-1.5 px-2" title={API_URL}>
        <span className={cx("h-1.5 w-1.5 rounded-full", stats.error ? "bg-rejected" : s ? "bg-confirmed" : "bg-line-strong")} />
        <Mono className="text-muted">{hostOf(API_URL) || API_URL}</Mono>
        <span className={stats.error ? "text-rejected" : "text-muted"}>{stats.error ? "API niedostępne" : s ? "API połączone" : "łączenie"}</span>
      </span>
    </footer>
  );
}

interface Command {
  id: string;
  section: string;
  label: string;
  hint?: string;
  href: string;
}

export function CommandPalette() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [cursor, setCursor] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const deferred = useDeferredValue(query.trim());

  const close = () => {
    setOpen(false);
    setQuery("");
    setCursor(0);
  };

  useEffect(() => {
    const show = () => setOpen(true);
    window.addEventListener("scamdna:palette", show);
    return () => window.removeEventListener("scamdna:palette", show);
  }, []);

  useHotkey((event) => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
      event.preventDefault();
      setOpen((value) => !value);
    } else if (event.key === "/" && !isTyping(event) && !open) {
      event.preventDefault();
      setOpen(true);
    }
  });

  const operators = useApi(open ? "palette:operators" : null, api.operators);
  const campaigns = useApi(open ? "palette:campaigns" : null, api.campaigns);
  const ads = useApi(open && deferred.length >= 2 ? `palette:ads:${deferred}` : null, () => api.ads(`?q=${encodeURIComponent(deferred)}`));

  const commands = useMemo<Command[]>(() => {
    const needle = deferred.toLowerCase();
    const match = (text: string) => !needle || text.toLowerCase().includes(needle);
    const navigation: Command[] = [...MODES, ...BACK_OFFICE]
      .filter((item) => match(item.label))
      .map((item) => ({ id: `nav:${item.href}`, section: "Przejdź do", label: item.label, hint: item.planned ? "niedostępne" : undefined, href: item.href }));
    const groups: Command[] = [
      ...(operators.data?.results ?? []).map((g) => ({ id: `op:${g.id}`, section: "Operatorzy", label: g.key, hint: `${g.size} reklam${g.label ? ` · ${g.label}` : ""}`, href: `/operator?id=${g.id}` })),
      ...(campaigns.data?.results ?? []).map((g) => ({ id: `ca:${g.id}`, section: "Kampanie", label: g.key, hint: `${g.size} reklam${g.label ? ` · ${g.label}` : ""}`, href: `/campaign?id=${g.id}` })),
    ].filter((c) => match(`${c.label} ${c.hint}`));
    const found: Command[] = (ads.data?.results ?? []).slice(0, 12).map((ad) => ({
      id: `ad:${ad.id}`,
      section: "Reklamy",
      label: adTitle(ad),
      hint: [hostOf(ad.landing_url), ad.case && `sprawa ${ad.case}`, ad.campaign, ad.operator].filter(Boolean).join(" · "),
      href: `/ad?id=${ad.id}`,
    }));
    return [...found, ...groups, ...navigation];
  }, [deferred, operators.data, campaigns.data, ads.data]);

  const selected = Math.min(cursor, Math.max(0, commands.length - 1));
  const run = (command: Command | undefined) => {
    if (!command) return;
    close();
    router.push(command.href);
  };

  function onKeyDown(event: React.KeyboardEvent) {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setCursor(Math.min(commands.length - 1, selected + 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setCursor(Math.max(0, selected - 1));
    } else if (event.key === "Enter") {
      run(commands[selected]);
    } else if (event.key === "Escape") {
      close();
    }
  }

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-50 flex justify-center bg-black/40 pt-[12vh]"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.12 }}
          onMouseDown={(event) => event.target === event.currentTarget && close()}
        >
          <motion.div
            role="dialog"
            aria-label="Paleta poleceń"
            className="flex h-fit max-h-[60vh] w-[560px] flex-col overflow-hidden rounded-md border border-line-strong bg-raised"
            initial={{ y: -6 }}
            animate={{ y: 0 }}
            transition={{ duration: 0.12 }}
          >
            <div className="flex h-9 items-center gap-2 border-b border-line px-3">
              <Search size={14} className="text-muted" />
              <input
                ref={input}
                autoFocus
                value={query}
                onChange={(event) => {
                  setQuery(event.target.value);
                  setCursor(0);
                }}
                onKeyDown={onKeyDown}
                placeholder="Tytuł, domena, tekst reklamy, K-0001, O-0001, nazwa ekranu"
                className="h-full flex-1 bg-transparent outline-none placeholder:text-faint"
              />
              <Kbd>Esc</Kbd>
            </div>
            <ul className="min-h-0 flex-1 overflow-auto py-1">
              {commands.length === 0 && <li className="px-3 py-2 text-muted">{ads.loading ? "Szukam w archiwum" : "Brak wyników. Zmień zapytanie."}</li>}
              {commands.map((command, index) => (
                <li key={command.id}>
                  {(index === 0 || commands[index - 1].section !== command.section) && <p className="cap px-3 pt-2 pb-1">{command.section}</p>}
                  <button
                    type="button"
                    onMouseEnter={() => setCursor(index)}
                    onClick={() => run(command)}
                    className={cx("flex h-7 w-full items-center gap-3 px-3 text-left", index === selected && "bg-accent-soft shadow-[inset_2px_0_0_var(--accent)]")}
                  >
                    <span className="truncate">{command.label}</span>
                    {command.hint && <span className="ml-auto shrink-0 truncate font-mono text-[0.85rem] text-muted">{command.hint}</span>}
                  </button>
                </li>
              ))}
            </ul>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
