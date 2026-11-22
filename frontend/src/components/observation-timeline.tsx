"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { api, type TimelineEvent } from "@/lib/api";
import { dateTime, markerValue } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import { ErrorBox, Loading } from "./ui";

function eventDate(event: TimelineEvent) {
  if (event.precision === "day") return event.at.slice(0, 10);
  return dateTime(event.at) || "Data niedostępna";
}

export function ObservationTimeline({ id, operator, bare = false }: { id: number; operator: boolean; bare?: boolean }) {
  const timeline = useApi(`${operator}:${id}`, () => operator ? api.operatorTimeline(id) : api.campaignTimeline(id));
  const params = useSearchParams();
  if (timeline.loading) return <Loading label="Pobieranie osi obserwacji" />;
  if (timeline.error) return <ErrorBox message={timeline.error} onRetry={timeline.reload} />;
  const data = timeline.data;
  if (!Array.isArray(data?.events) || !Array.isArray(data.undated?.ads)) return <p>Oś obserwacji niedostępna.</p>;
  const requestedType = params.get("eventType");
  const type = data.events.some(item => item.type === requestedType) ? requestedType ?? "" : "";
  const events = data.events.filter(item => !type || item.type === type);
  const ordinal = Number(params.get("event"));
  const position = Number.isSafeInteger(ordinal) && ordinal >= 1 && ordinal <= events.length ? ordinal - 1 : 0;
  const event = events[position];

  function selectEvent(nextType: string, nextPosition: number) {
    const url = new URL(window.location.href);
    if (nextType) url.searchParams.set("eventType", nextType);
    else url.searchParams.delete("eventType");
    if (nextPosition > 0) url.searchParams.set("event", String(nextPosition + 1));
    else url.searchParams.delete("event");
    window.history.replaceState(null, "", url);
  }

  const Wrapper = bare ? "div" : "section";
  return <Wrapper className={bare ? "grid grid-cols-1 gap-2" : "grid grid-cols-1 gap-2 border-y border-line py-3"}>
    {!bare && <h2 className="font-semibold">Oś obserwacji</h2>}
    <label className="grid gap-1 sm:block">Typ zdarzenia <select className="min-w-0 max-w-full" value={type} onChange={e => selectEvent(e.target.value, 0)}>
      <option value="">Wszystkie</option>
      {[...new Map(data.events.map(item => [item.type, item.label]))].map(([key,label]) => <option key={key} value={key}>{label}</option>)}
    </select></label>
    {event ? <>
      <label className="grid gap-1 sm:block">Zdarzenie <select className="min-w-0 max-w-full border border-line bg-panel p-1" value={position}
        onChange={e => selectEvent(type, Number(e.target.value))}>
        {events.map((item, index) => <option key={index} value={index}>{index + 1}. {eventDate(item)} · {item.label}</option>)}
      </select></label>
      <div className="flex gap-4">
        <button disabled={position === 0} className="text-accent disabled:opacity-50" onClick={() => selectEvent(type, position - 1)}>Poprzednie zdarzenie</button>
        <button disabled={position + 1 >= events.length} className="text-accent disabled:opacity-50" onClick={() => selectEvent(type, position + 1)}>Następne zdarzenie</button>
      </div>
      <article aria-live="polite" className="wrap-anywhere">
        <h3>{event.label}</h3><p>{eventDate(event)} · {event.time_kind === "observed" ? "Data obserwacji" : "Data podana przez źródło"} · {event.source}</p>
        <p className="font-mono">{markerValue(event.value)}</p>
        {event.ads.map(ad => <Link key={ad} className="mr-2 text-accent underline" href={`/ads/${ad}`}>Reklama #{ad}</Link>)}
      </article>
    </> : <p>Brak datowanych zdarzeń.</p>}
    {(data.undated.ads.length + data.undated.links + data.undated.traces + data.undated.certificates > 0) && <div><h3>Materiały bez daty</h3>
      <p>Reklamy {data.undated.ads.length} · Ślady {data.undated.traces} · Powiązania {data.undated.links} · Certyfikaty {data.undated.certificates}</p>
      {data.undated.ads.map(ad => <Link key={ad} className="mr-2 text-accent underline" href={`/ads/${ad}`}>Reklama #{ad}</Link>)}
    </div>}
  </Wrapper>;
}
