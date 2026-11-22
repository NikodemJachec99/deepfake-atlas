"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { api, type Evidence, type Regroup } from "@/lib/api";
import { bits, dateTime, errorText, plural } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import { useExpert } from "@/lib/expert";
import { ErrorBox, GroupLink, Loading } from "./ui";

const groupKind = (key: string) => (key.startsWith("O") ? "Operator" : "Kampania");
const adList = (ids: number[]) => ids.map(id => "#" + id).join(", ") || "brak";
const adCount = (n: number) => `${n} ${plural(n, "reklama", "reklamy", "reklam")}`;

function GroupChanges({ changes }: { changes: Regroup }) {
  const rows = [...changes.campaign, ...changes.operator];
  const merges = [...(changes.merged?.campaign ?? []), ...(changes.merged?.operator ?? [])];
  return <div role="status"><strong>Przeliczono grupy</strong>
    {rows.length > 0 && <ul>{rows.map(r => <li key={r.group}>{groupKind(r.group)} {r.group} → {r.after.map(a => a.key + " (" + adCount(a.ads.length) + ")").join(", ") || "grupa rozwiązana"} · Reklamy poza grupą: {adList(r.released)}</li>)}</ul>}
    {merges.length > 0 && <ul>{merges.map(m => <li key={m.group}>
      {groupKind(m.group)}: {m.from.join(", ")} → <GroupLink group={m.group}/> · Reklamy po scaleniu: {m.ads.length}
      {m.joined.length > 0 && <span> · Dołączone reklamy: {m.joined.map(id => <Link key={id} href={`/ads/${id}`} className="mr-1 text-accent underline">#{id}</Link>)}</span>}
    </li>)}</ul>}
    {!rows.length && !merges.length && <p>Skład grup pozostał ten sam.</p>}
  </div>;
}

function RestoreDetails({ id }: { id: number }) {
  const [open, setOpen] = useState(false);
  const result = useApi(open ? String(id) : null, () => api.premise(id));
  return <details onToggle={e => setOpen(e.currentTarget.open)}><summary>Wynik przywrócenia</summary>
    {open && (result.loading ? <Loading/> : result.error ? <ErrorBox message={result.error} onRetry={result.reload}/> :
      result.data?.restored_state?.regroup ? <GroupChanges changes={result.data.restored_state.regroup}/> : <p>Brak zapisanego wyniku przeliczenia grup.</p>)}
  </details>;
}

export function PremiseChallenge({ item, refresh, inline }: { item: Evidence; refresh: () => void; inline?: boolean }) {
  const values = [...new Set([item.value_a, item.value_b])].filter(Boolean);
  const { expert } = useExpert();
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState(values[0] ?? "");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [changes, setChanges] = useState<Regroup | null>(null);
  const preview = useApi(open && value && !changes ? JSON.stringify([item.kind, value]) : null, () => api.previewPremise(item.kind, value));
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    if (!preview.data || !heading.current) return;
    heading.current.focus({ preventScroll: true });
    heading.current.scrollIntoView({ block: "nearest" });
  }, [preview.data]);

  const memberships = new Map<number, string[]>();
  for (const groups of Object.values(preview.data?.groups ?? {})) {
    for (const group of [...groups.split, ...groups.stay]) {
      for (const id of group.before) memberships.set(id, [...(memberships.get(id) ?? []), group.key]);
    }
  }
  function adLabel(id: number) {
    return [`#${id}`, ...(memberships.get(id) ?? [])].join(" · ");
  }
  async function save() {
    if (!preview.data || !reason.trim() || busy) return;
    setBusy(true); setError("");
    try { setChanges((await api.challengePremise(item.kind, value, reason.trim())).regroup); }
    catch (e) { setError(errorText(e)); }
    finally { setBusy(false); }
  }
  return <section className={inline ? "contents" : "px-2 pb-2"}>
    <button className="text-accent underline" aria-expanded={open} disabled={busy} onClick={() => setOpen(!open)}>Zakwestionuj przesłankę</button>
    {open && <div className="grid basis-full gap-2 rounded border border-line p-3 text-sm">
      {!changes && values.length > 1 && <label>Wartość śladu <select disabled={busy} value={value} onChange={e => setValue(e.target.value)}>{values.map(v => <option key={v}>{v}</option>)}</select></label>}
      {!value && <p>Brak wartości śladu do zakwestionowania.</p>}
      {changes ? <><GroupChanges changes={changes}/><button className="text-accent" onClick={refresh}>Odśwież krawędź</button></> : preview.loading ? <Loading/> : preview.error ? <ErrorBox message={preview.error} onRetry={preview.reload}/> : preview.data && <>
        <h3 ref={heading} tabIndex={-1}>Wpływ na cały korpus · {preview.data.display_value || value}</h3>
        <p>{expert ? <>Krawędzie korzystające ze śladu: {preview.data.edge_count}. Podziały grup: {preview.data.split_count}.</> : <>Ten ślad łączy {preview.data.edge_count} {plural(preview.data.edge_count, "parę", "pary", "par")} reklam. {preview.data.split_count ? `Po zakwestionowaniu rozpadnie się ${preview.data.split_count} ${plural(preview.data.split_count, "grupa", "grupy", "grup")}.` : "Żadna grupa się nie rozpadnie."}</>}</p>
        <details><summary>Krawędzie przed i po zmianie</summary><ul>{preview.data.edges.map(e => <li key={e.id}>{adLabel(e.ad_a)} ↔ {adLabel(e.ad_b)} · {e.before.relation_label} ({bits(e.before.bits)} bita) → {e.removed ? "usunięcie powiązania" : e.after.relation_label + " (" + bits(e.after.bits) + " bita)"}</li>)}</ul></details>
        {Object.values(preview.data.groups).map((group, i) => <div key={i}>
          {group.split.map(g => <p key={g.key}>Podział: {groupKind(g.key)} {g.key} na {g.after.map(part => (part.key || "nową grupę") + " (" + adList(part.ads) + ")").join(" i ")} · Reklamy poza grupą: {adList(g.released)}</p>)}
          {group.stay.map(g => <p key={g.key}>{g.key} pozostaje razem · {g.supported_by.map(s => expert ? s.label + " (" + bits(s.bits) + " bita)" : s.label).join(", ") || "brak dodatkowych śladów w odpowiedzi"}</p>)}
        </div>)}
        {preview.data.warnings.map(w => <p key={w}>{w}</p>)}
        <label>Powód zakwestionowania<textarea className="block w-full border border-line" value={reason} disabled={busy} onChange={e => setReason(e.target.value)}/></label>
        <button disabled={busy || !reason.trim()} className="rounded border border-line p-2 disabled:opacity-50" onClick={save}>Zapisz zakwestionowanie</button>
      </>}
      {error && <ErrorBox message={error}/>}
      <Link href="/premises" className="text-accent underline">Historia zakwestionowań</Link>
    </div>}
  </section>;
}

export function PremiseHistory() {
  const history = useApi("premises", () => api.premises());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [changes, setChanges] = useState<Regroup | null>(null);
  async function restore(id: number) {
    setBusy(true); setError("");
    try { setChanges((await api.restorePremise(id)).regroup); history.reload(); }
    catch(e) { setError(errorText(e)); }
    finally { setBusy(false); }
  }
  return <main className="atlas-page"><header className="grid gap-2"><h1 className="atlas-title">Historia zakwestionowań</h1>
      <p className="max-w-3xl text-pretty text-muted">Zakwestionowanie to wyłączenie śladu, który nie dowodzi wspólnego źródła, na przykład popularnej usługi pośrednika. System przelicza wtedy powiązania bez niego. Każde zakwestionowanie można tu cofnąć.</p></header>
    {changes && <GroupChanges changes={changes}/>}
    {error && <ErrorBox message={error}/>}
    {history.loading ? <Loading/> : history.error ? <ErrorBox message={history.error} onRetry={history.reload}/> : !history.data?.results.length ? <div className="grid justify-items-start gap-2 rounded-xl border border-dashed border-line-strong p-6">
        <p className="text-lg font-medium">Nikt jeszcze nie zakwestionował żadnego śladu.</p>
        <p className="text-muted">Ślad zakwestionujesz przy ocenie pary reklam, przyciskiem „Zakwestionuj przesłankę”. Przed zapisem zobaczysz, które grupy by się zmieniły.</p>
        <Link href="/review" className="rounded-md border border-line-strong px-3 py-2 text-accent hover:bg-panel">Przejdź do oceny par</Link>
      </div> :
      <ul>{history.data.results.map(p => <li className="border-b border-line py-3" key={p.id}><div className="flex flex-wrap items-baseline gap-x-3">
          <strong className="wrap-anywhere">{p.label} · {p.display_value || p.value}</strong>
          <span className="text-sm text-muted">{p.status_label}</span>
        </div>
        <p>Powód zakwestionowania: {p.reason}</p>
        <dl className="my-2 flex flex-wrap gap-x-6 gap-y-1 text-sm">
          <div><dt className="text-muted">Zakwestionowano</dt><dd><time dateTime={p.created_at}>{dateTime(p.created_at)}</time></dd></div>
          {p.status === "restored" && <div><dt className="text-muted">Przywrócono</dt><dd>{p.restored_at
            ? <time dateTime={p.restored_at}>{dateTime(p.restored_at)}</time>
            : "Data niedostępna"}</dd></div>}
        </dl>
        {p.status === "restored" && <RestoreDetails id={p.id}/>}
        {p.status === "challenged" && <button disabled={busy} className="text-accent underline" onClick={() => restore(p.id)}>Przywróć przesłankę</button>}</li>)}</ul>}
  </main>;
}
