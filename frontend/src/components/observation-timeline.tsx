"use client";

import Link from "next/link";
import { useState } from "react";
import { api, type TimelineEvent } from "@/lib/api";
import { markerValue } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import { ErrorBox, Loading } from "./ui";

function eventDate(event: TimelineEvent) {
  if (event.precision === "day") return event.at.slice(0, 10);
  const date = new Date(event.at);
  return Number.isFinite(date.getTime()) ? date.toLocaleString("pl-PL", { timeZoneName: "short" }) : "Data niedostępna";
}

export function ObservationTimeline({ id, operator }: { id: number; operator: boolean }) {
  const timeline = useApi(`${operator}:${id}`, () => operator ? api.operatorTimeline(id) : api.campaignTimeline(id));
  const [type, setType] = useState("");
  const [position, setPosition] = useState(0);
  if (timeline.loading) return <Loading label="Pobieranie osi obserwacji" />;
  if (timeline.error) return <ErrorBox message={timeline.error} onRetry={timeline.reload} />;
  const data = timeline.data;
  if (!Array.isArray(data?.events) || !Array.isArray(data.undated?.ads)) return <p>Oś obserwacji niedostępna.</p>;
  const events = data.events.filter(item => !type || item.type === type);
  const event = events[position];
  return <section className="grid gap-2 border-y border-line py-3">
    <h2 className="font-semibold">Oś obserwacji</h2>
    <label>Typ zdarzenia <select value={type} onChange={e => { setType(e.target.value); setPosition(0); }}>
      <option value="">Wszystkie</option>
      {[...new Map(data.events.map(item => [item.type, item.label]))].map(([key,label]) => <option key={key} value={key}>{label}</option>)}
    </select></label>
    {event ? <>
      <label>Zdarzenie <select className="max-w-full border border-line bg-panel p-1" value={position}
        onChange={e => setPosition(Number(e.target.value))}>
        {events.map((item, index) => <option key={index} value={index}>{index + 1}. {eventDate(item)} · {item.label}</option>)}
      </select></label>
      <div className="flex gap-4">
        <button disabled={position === 0} className="text-accent disabled:opacity-50" onClick={() => setPosition(position - 1)}>Poprzednie zdarzenie</button>
        <button disabled={position + 1 >= events.length} className="text-accent disabled:opacity-50" onClick={() => setPosition(position + 1)}>Następne zdarzenie</button>
      </div>
      <article aria-live="polite" className="break-words">
        <h3>{event.label}</h3><p>{eventDate(event)} · {event.time_kind === "observed" ? "Data obserwacji" : "Data podana przez źródło"} · {event.source}</p>
        <p className="font-mono">{markerValue(event.value)}</p>
        {event.ads.map(ad => <Link key={ad} className="mr-2 text-accent underline" href={`/ads/${ad}`}>Reklama #{ad}</Link>)}
      </article>
    </> : <p>Brak datowanych zdarzeń.</p>}
    {(data.undated.ads.length + data.undated.links + data.undated.traces + data.undated.certificates > 0) && <div><h3>Materiały bez daty</h3>
      <p>Reklamy {data.undated.ads.length} · Ślady {data.undated.traces} · Powiązania {data.undated.links} · Certyfikaty {data.undated.certificates}</p>
      {data.undated.ads.map(ad => <Link key={ad} className="mr-2 text-accent underline" href={`/ads/${ad}`}>Reklama #{ad}</Link>)}
    </div>}
  </section>;
}
