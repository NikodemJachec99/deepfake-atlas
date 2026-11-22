"use client";

import Link from "next/link";
import { useState } from "react";
import { api, type Evidence, type Regroup } from "@/lib/api";
import { bits, dateTime, errorText } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import { ErrorBox, Loading } from "./ui";

function GroupChanges({ changes }: { changes: Regroup }) {
  const rows = [...changes.campaign, ...changes.operator];
  return <div role="status"><strong>Przeliczono grupy</strong>
    {rows.length ? <ul>{rows.map(r => <li key={r.group}>{r.group} → {r.after.map(a => a.key + " (" + a.ads.length + ")").join(", ") || "brak grup"} · Reklamy poza grupą: {r.released.join(", ") || "brak"}</li>)}</ul> : <p>Skład grup pozostał ten sam.</p>}
  </div>;
}

export function PremiseChallenge({ item, refresh }: { item: Evidence; refresh: () => void }) {
  const values = [...new Set([item.value_a, item.value_b])].filter(Boolean);
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState(values[0] ?? "");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [changes, setChanges] = useState<Regroup | null>(null);
  const preview = useApi(open && value && !changes ? JSON.stringify([item.kind, value]) : null, () => api.previewPremise(item.kind, value));
  async function save() {
    if (!preview.data || !reason.trim() || busy) return;
    setBusy(true); setError("");
    try { setChanges((await api.challengePremise(item.kind, value, reason.trim())).regroup); }
    catch (e) { setError(errorText(e)); }
    finally { setBusy(false); }
  }
  return <section className="px-2 pb-2">
    <button className="text-accent underline" aria-expanded={open} disabled={busy} onClick={() => setOpen(!open)}>Zakwestionuj przesłankę</button>
    {open && <div className="grid gap-2 rounded border border-line p-3">
      {!changes && values.length > 1 && <label>Wartość śladu <select disabled={busy} value={value} onChange={e => setValue(e.target.value)}>{values.map(v => <option key={v}>{v}</option>)}</select></label>}
      {!value && <p>Brak wartości śladu do zakwestionowania.</p>}
      {changes ? <><GroupChanges changes={changes}/><button className="text-accent" onClick={refresh}>Odśwież krawędź</button></> : preview.loading ? <Loading/> : preview.error ? <ErrorBox message={preview.error} onRetry={preview.reload}/> : preview.data && <>
        <h3>Wpływ na cały korpus · {preview.data.display_value || value}</h3>
        <p>Krawędzie korzystające ze śladu: {preview.data.edge_count}. Podziały grup: {preview.data.split_count}.</p>
        <details><summary>Krawędzie przed i po zmianie</summary><ul>{preview.data.edges.map(e => <li key={e.id}>#{e.ad_a} ↔ #{e.ad_b} · {e.before.relation_label} ({bits(e.before.bits)} bita) → {e.removed ? "usunięcie powiązania" : e.after.relation_label + " (" + bits(e.after.bits) + " bita)"}</li>)}</ul></details>
        {Object.values(preview.data.groups).map((group, i) => <div key={i}>
          {group.split.map(g => <p key={g.key}>Podział {g.key} · {g.after.map(part => (part.key || "Nowa grupa") + ": " + part.ads.join(", ")).join(" · ")} · Uwolnione reklamy: {g.released.join(", ") || "brak"}</p>)}
          {group.stay.map(g => <p key={g.key}>{g.key} pozostaje razem · {g.supported_by.map(s => s.label + " (" + bits(s.bits) + " bita)").join(", ") || "brak dodatkowych śladów w odpowiedzi"}</p>)}
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
  return <main className="atlas-page"><h1 className="atlas-title">Historia zakwestionowań</h1>
    {changes && <GroupChanges changes={changes}/>}
    {error && <ErrorBox message={error}/>}
    {history.loading ? <Loading/> : history.error ? <ErrorBox message={history.error} onRetry={history.reload}/> : !history.data?.results.length ? <p>Brak zapisanych zakwestionowań.</p> :
      <ul>{history.data.results.map(p => <li className="border-b border-line py-3" key={p.id}><strong>{p.label} · {p.display_value || p.value}</strong><p>{p.status_label} · {dateTime(p.created_at)} · {p.reason}</p>
        {p.status === "challenged" && <button disabled={busy} className="text-accent underline" onClick={() => restore(p.id)}>Przywróć przesłankę</button>}</li>)}</ul>}
  </main>;
}
