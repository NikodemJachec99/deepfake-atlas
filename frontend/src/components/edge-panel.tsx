"use client";

import { ContentSimilarity } from "./content-similarity";

// Panel dowodów krawędzi: z czego wynika połączenie dwóch reklam. Najważniejszy ekran aplikacji.
// Wszystko pochodzi z GET /api/edges/{id}; zrzuty reklam z GET /api/ads/{id}.

import { Check, ChevronDown, ChevronRight, Download, HelpCircle, X } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import Link from "next/link";
import { EdgeSuggestions } from "./edge-suggestions";
import { JevReview } from "./jev-review";
import { DecisionHistory } from "./decision-history";
import type { Regroup, ReviewItem, VerdictReason } from "@/lib/api";
import { PremiseChallenge } from "./premise-challenge";
import { EvidenceLab } from "./evidence-lab";
import { useState } from "react";

import { api, ApiError, artifactDownloadUrl, artifactImageUrl, type AdDetail, type AdSummary, type EdgeDetail, type Evidence, type Verdict } from "@/lib/api";
import { SOURCE_LABELS, utcEdgeVersion, markerValue, RELATION_HINT, adTitle, bits, dateTime, errorText, famVar, hostOf, num, plural } from "@/lib/format";
import { isTyping, useApi, useHotkey } from "@/lib/hooks";

import { Btn, Empty, ErrorBox, FamilyBar, FamilyDot, GroupLink, Kbd, Loading, Meter, Mono, RelationTag, Tag, VerdictTag } from "./ui";

const VISUAL_KINDS = new Set(["creative_phash", "creative_sha256", "image_set"]);
const zrodel = (n: number) => plural(n, "źródle", "źródłach", "źródłach");

function Creative({ sha, label }: { sha: string; label: string }) {
  const [broken, setBroken] = useState(false);
  if (broken) return <div className="flex h-28 items-center justify-center border border-line text-faint">zrzut niedostępny</div>;
  return (
    <a href={artifactImageUrl(sha)} target="_blank" rel="noreferrer" title="Otwórz zrzut reklamy w nowej karcie" className="block border border-line bg-bg">
      {/* eslint-disable-next-line @next/next/no-img-element -- obraz z API dowodów, bez optymalizacji po stronie Next */}
      <img src={artifactImageUrl(sha)} alt={label} loading="lazy" onError={() => setBroken(true)} className="h-28 w-full object-contain" />
    </a>
  );
}

function AdSide({ ad, detail, side, onOpenAd }: { ad: AdSummary; detail?: AdDetail; side: "A" | "B"; onOpenAd?: (id: number) => void }) {
  const creative = detail?.creatives[0];
  return (
    <div className="flex min-w-0 flex-1 flex-col gap-1.5 p-2">
      <div className="flex items-center gap-1.5">
        <Tag>Materiał {side}</Tag>
        <Mono className="text-muted">#{ad.id}</Mono>
        {ad.case && <span className="text-muted">sprawa {ad.case}</span>}
        {"cert_pl" in ad.labels && <Tag tone="rejected" title="Domena jest na Liście Ostrzeżeń CERT Polska">CERT</Tag>}
      </div>
      <p className="line-clamp-2 min-h-[2.8em] font-medium" title={ad.title}>
        {adTitle(ad)}
      </p>
      <Mono className="truncate" title={ad.landing_url}>
        {hostOf(ad.landing_url) || "brak adresu"}
      </Mono>
      <p className="text-xs text-muted">{SOURCE_LABELS[ad.source]} · {dateTime(ad.first_seen) || "Brak daty obserwacji"}</p>
      <div className="flex items-center gap-2">
        <GroupLink group={ad.campaign} />
        <GroupLink group={ad.operator} />
      </div>
      {creative ? <Creative sha={creative} label={`Zrzut reklamy ${side}`} /> : <div className="flex h-28 items-center justify-center border border-dashed border-line text-faint">{detail ? "brak zrzutu reklamy" : "…"}</div>}
      {onOpenAd ? (
        <Btn variant="ghost" className="self-start px-0!" onClick={() => onOpenAd(ad.id)}>
          Otwórz źródło
        </Btn>
      ) : (
        <Link href={`/ads/${ad.id}`} className="text-accent hover:underline">
          Otwórz źródło
        </Link>
      )}
    </div>
  );
}

// Karta dowodu. Zwinięta: rodzina, marker, wartość, rzadkość, wkład. Rozwinięta: obie strony, wagi, artefakty.
function EvidenceCard({ item, max, refresh }: { item: Evidence; max: number; refresh: () => void }) {
  const [open, setOpen] = useState(false);
  const soft = item.df === 0;
  const same = item.value_a === item.value_b;
  const left = markerValue(item.value_a, item.display_value);
  const right = same ? left : markerValue(item.value_b);
  const discounted = item.raw_bits - item.weight_bits > 0.05;
  return (
    <li className="border-b border-line">
      <button type="button" onClick={() => setOpen(!open)} aria-expanded={open} className="grid min-h-9 w-full grid-cols-[12px_minmax(0,1fr)_auto] items-center gap-x-2 px-2 py-1 text-left hover:bg-hover">
        {open ? <ChevronDown size={12} className="text-muted" /> : <ChevronRight size={12} className="text-muted" />}
        <span className="flex min-w-0 flex-col">
          <span className="flex items-center gap-1.5">
            <FamilyDot family={item.family} />
            <span className="truncate">{item.label}</span>
            {item.decisive && <Tag tone="accent" title="Rzadki marker rozstrzygający: sam wystarcza do stwierdzenia wspólnego źródła">rozstrzyga</Tag>}
          </span>
          {soft ? (
            <span className="text-muted">
              podobieństwo <Mono className="text-fg">{num(item.similarity, 2)}</Mono>
            </span>
          ) : (
            <Mono className="truncate text-muted" title={same ? left : `${left} | ${right}`}>
              {same ? left : `${left} | ${right}`}
            </Mono>
          )}
        </span>
        <span className="flex flex-col items-end">
          <span className="flex items-center gap-2">
            <span className="h-1.5 w-14 bg-line">
              <span className="block h-full" style={{ width: `${Math.min(100, (item.weight_bits / max) * 100)}%`, background: famVar(item.family) }} />
            </span>
            <Mono className="w-[3.2em] text-right">{bits(item.weight_bits)}</Mono>
            <span className="text-faint">bita</span>
          </span>
          <span className="text-[0.85rem] text-muted">{soft ? "marker miękki" : `w ${item.df} z ${item.corpus_n} źródeł`}</span>
        </span>
      </button>
      <PremiseChallenge item={item} refresh={refresh}/>
      <ContentSimilarity kind={item.kind} similarity={item.similarity} />

      <AnimatePresence initial={false}>
        {open && (
          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.15 }} className="overflow-hidden bg-bg">
            <div className="flex flex-col gap-2 px-2 py-2 pl-7">
              {soft ? (
                <p className="text-muted">
                  Marker miękki porównywany przez podobieństwo, nie przez równość wartości. Podobieństwo <Mono className="text-fg">{num(item.similarity, 3)}</Mono>.
                </p>
              ) : (
                <div className="grid grid-cols-2 gap-2">
                  {(["a", "b"] as const).map((side) => (
                    <div key={side} className="min-w-0">
                      <p className="cap">Strona {side.toUpperCase()}</p>
                      <Mono className="break-all">{side === "a" ? left : right}</Mono>
                    </div>
                  ))}
                  <p className="col-span-2 text-muted">
                    {same ? "Wartości identyczne po obu stronach." : "Wartości różnią się zapisem, marker uznał je za zgodne."} Ta wartość występuje w <Mono className="text-fg">{item.df}</Mono> z{" "}
                    <Mono className="text-fg">{item.corpus_n}</Mono> niezależnych {zrodel(item.corpus_n)} korpusu (źródło to kampania albo reklama bez kampanii).
                  </p>
                </div>
              )}
              {VISUAL_KINDS.has(item.kind) && <div className="grid grid-cols-2 gap-2">
                {([["A", item.artifact_a], ["B", item.artifact_b]] as const).map(([side, sha]) => sha
                  ? <Creative key={side} sha={sha} label={`Artefakt dowodu · ${side}`} />
                  : <p key={side} className="text-muted">{side} · Brak artefaktu dowodu</p>)}
              </div>}
              <p className="text-muted">
                Wkład <Mono className="text-fg">{bits(item.weight_bits)}</Mono> bita
                {discounted && (
                  <>
                    {" "}
                    (waga surowa <Mono className="text-fg">{bits(item.raw_bits)}</Mono> bita, obniżona za korelację w rodzinie: kolejny marker tej samej rodziny liczy się połowę słabiej)
                  </>
                )}
                . Typ markera: <Mono>{item.kind}</Mono>.
              </p>
              <div className="flex flex-wrap gap-2">
                {([["A", item.artifact_a], ["B", item.artifact_b]] as const).map(([side, sha]) =>
                  sha ? (
                    <a key={side} href={artifactDownloadUrl(sha)} className="inline-flex items-center gap-1 text-accent hover:underline" title="Surowy dowód jako plik. Nigdy nie renderuje się w przeglądarce.">
                      <Download size={12} />
                      Artefakt {side} <Mono className="text-muted">{sha.slice(0, 12)}</Mono>
                    </a>
                  ) : (
                    <span key={side} className="text-faint">
                      Artefakt {side}: marker wyliczony z adresu lub treści, bez osobnego pliku
                    </span>
                  ),
                )}
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </li>
  );
}

const DECISIONS: { verdict: Exclude<Verdict, "">; label: string; key: string; icon: typeof Check }[] = [
  { verdict: "confirmed", label: "Potwierdź", key: "P", icon: Check },
  { verdict: "unsure", label: "Do wyjaśnienia", key: "N", icon: HelpCircle },
  { verdict: "rejected", label: "Odrzuć", key: "O", icon: X },
];

function Decision({ edge, onSaved, refresh }: { edge: EdgeDetail; refresh: () => void; onSaved: (edge: EdgeDetail & { regroup?: Regroup }) => void }) {
  const reasons = useApi("verdict-reasons", api.kinds);
  const [reason, setReason] = useState<Exclude<VerdictReason, "unknown"> | "">(
    edge.verdict_reason && edge.verdict_reason !== "unknown" ? edge.verdict_reason : ""
  );
  const [selected, setSelected] = useState<Verdict>(edge.verdict);
  const [note, setNote] = useState(edge.verdict_note);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const [stale, setStale] = useState(false);
  async function decide(verdict: Exclude<Verdict, "">) {
    setBusy(true);
    setError("");
    try {
      onSaved(await api.setVerdict(edge.id, verdict, note, reason || undefined, utcEdgeVersion(edge.updated_at)));
    } catch (reason) {
      if (reason instanceof ApiError && reason.status === 409) setStale(true);
      else setError(errorText(reason));
    } finally {
      setBusy(false);
    }
  }

  useHotkey((event) => {
    if (isTyping(event) || event.ctrlKey || event.metaKey || event.altKey || busy || stale) return;
    const decision = DECISIONS.find((d) => d.key.toLowerCase() === event.key.toLowerCase());
    if (decision) setSelected(decision.verdict);
  });

  return (
    <footer className="shrink-0 border-t border-line bg-panel p-2">
      <div className="flex items-center justify-between gap-2 pb-1.5">
        <span className="cap">Twoja ocena powiązania</span>
        <span className="flex items-center gap-2 text-[0.85rem] text-muted">
          <VerdictTag verdict={edge.verdict} />
          {edge.verdict_at && <Mono>{dateTime(edge.verdict_at)}</Mono>}
        </span>
      </div>
      <label className="flex flex-wrap items-center gap-2 py-1">Powód decyzji
        <select className="max-w-full border border-line bg-panel p-1" value={reason}
          disabled={!reasons.data?.verdict_reasons?.length || busy}
          onChange={event => setReason(event.target.value as typeof reason)}>
          <option value="">{reasons.loading ? "Pobieranie powodów…" : reasons.data?.verdict_reasons?.length ? "Bez podanego powodu" : "Lista powodów niedostępna"}</option>
          {reasons.data?.verdict_reasons?.map(item => <option key={item.value} value={item.value}>{item.label}</option>)}
        </select>
      </label>
      <textarea
        aria-label="Dodaj uzasadnienie"
        value={note}
        onChange={(event) => setNote(event.target.value)}
        rows={2}
        placeholder="Uzasadnienie (opcjonalne). Trafia do dziennika audytu razem z decyzją."
        className="w-full resize-none rounded-sm border border-line bg-bg px-2 py-1 outline-none placeholder:text-faint focus:border-accent"
      />
      <div className="flex items-center gap-1.5 pt-1.5">
        {DECISIONS.map(({ verdict, label, key, icon: Icon }) => (
          <Btn key={verdict} disabled={busy || stale} active={selected === verdict} onClick={() => setSelected(verdict)} className="flex-1">
            <Icon size={13} />
            {label}
            <Kbd>{key}</Kbd>
          </Btn>
        ))}
      </div>
      <div className="mt-3 flex flex-wrap items-center justify-between gap-2"><span className="text-xs text-muted" title={edge.updated_at}>Wersja dowodów · {dateTime(edge.updated_at)}</span>
        <Btn disabled={!selected || busy || stale} onClick={() => selected && decide(selected)}>Zapisz ocenę</Btn></div>
      {stale && <p role="alert">Dane krawędzi zmieniły się. <button className="text-accent underline" onClick={refresh}>Odśwież dane</button></p>}
      {error && <p className="pt-1 text-rejected">Decyzja nie została zapisana: {error}</p>}
    </footer>
  );
}

export function EdgePanel({ edgeId, onOpenAd, onVerdict, review }: { edgeId: number; review?: ReviewItem; onOpenAd?: (id: number) => void; onVerdict?: (edge: EdgeDetail & { regroup?: Regroup }) => void }) {
  const [tab, setTab] = useState("Dowody");
  const [showAll, setShowAll] = useState(false);
  const [result, setResult] = useState("");
  const [section, setSection] = useState<string | null>(null);
  const toggle = (name: string) => setSection(current => current === name ? null : name);
  const edge = useApi(`edge:${edgeId}`, () => api.edge(edgeId));
  const data = edge.data;
  const adA = useApi(data ? `ad:${data.ad_a}` : null, () => api.ad(data!.ad_a));
  const adB = useApi(data ? `ad:${data.ad_b}` : null, () => api.ad(data!.ad_b));

  if (edge.loading) return <Loading label="Pobieranie dowodów krawędzi" />;
  if (edge.error) return <ErrorBox message={edge.error} onRetry={edge.reload} />;
  if (!data) return null;

  const evidence = [...data.evidence].sort((a, b) => b.weight_bits - a.weight_bits);
  const max = Math.max(1, ...evidence.map((e) => e.weight_bits));
  const [a, b] = [data.ads.find((ad) => ad.id === data.ad_a) ?? data.ads[0], data.ads.find((ad) => ad.id === data.ad_b) ?? data.ads[1]];
  const crossDomain = a && b && hostOf(a.landing_url) && hostOf(b.landing_url) && hostOf(a.landing_url) !== hostOf(b.landing_url);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="min-h-0 flex-1 overflow-auto">
        <div className="flex flex-col gap-2 border-b border-line p-2">
          <h2 className="text-lg font-semibold">Hipoteza modelu</h2>
          {review && <span className="text-xs text-muted">Do oceny · {review.reason_label}</span>}
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="text-[1.08rem] font-medium">
              <RelationTag relation={data.relation} duplicate={data.duplicate} />
            </span>
            <Mono className="text-muted">krawędź #{data.id}</Mono>
          </div>
          <p className="text-muted">
            {RELATION_HINT[data.relation]}
            {data.duplicate && ". Duplikat: ta sama strona przechwycona ponownie"}
            {crossDomain && !data.duplicate && data.relation !== "similar" && ". Różne domeny, to samo zaplecze"}.
          </p>
          <div className="flex flex-wrap items-center gap-x-5 gap-y-1">
            <span className="flex items-center gap-2">
              <span className="text-muted">wynik modelu (niekalibrowany)</span>
              <Meter value={data.probability} width={96} />
            </span>
            <span>
              <span className="text-muted">suma dowodów</span> <Mono>{bits(data.bits)}</Mono> <span className="text-faint">bita</span>
            </span>
            <span>
              <span className="text-muted">dowody</span> <Mono>{evidence.length}</Mono>
            </span>
            {data.decisive && <Tag tone="accent">marker rozstrzygający</Tag>}
          </div>
          <FamilyBar families={data.families} legend />
        </div>

        <div className="flex divide-x divide-line border-b border-line">
          {a && <AdSide ad={a} detail={adA.data} side="A" onOpenAd={onOpenAd} />}
          {b && <AdSide ad={b} detail={adB.data} side="B" onOpenAd={onOpenAd} />}
        </div>

        <div className="flex gap-2 border-b border-line px-2" aria-label="Widok pary">{["Dowody", "Źródła", "Kontekst"].map(t =>
          <button key={t} aria-pressed={tab === t} className="min-h-10 px-2 aria-pressed:border-b-2 aria-pressed:border-accent" onClick={() => setTab(t)}>{t}</button>)}</div>
        {tab === "Kontekst" && <>        <JevReview open={section === "jev"} onToggle={() => toggle("jev")} key={`jev-${data.id}`} edge={data} />
        <DecisionHistory open={section === "history"} onToggle={() => toggle("history")} edge={data} />
        <EdgeSuggestions open={section === "suggestions"} onToggle={() => toggle("suggestions")} key={`suggestions-${data.id}`} edgeId={data.id} />
        <EvidenceLab open={section === "lab"} onToggle={() => toggle("lab")} key={data.id + ":" + data.updated_at} edge={data} refresh={edge.reload} />
</>}
        {tab === "Źródła" && <ul className="grid gap-2 p-3">{evidence.map(item => <li key={item.id}><strong>{item.label}</strong> · {([["A", item.artifact_a], ["B", item.artifact_b]] as const).map(([side,sha]) => sha ? <a className="mr-2 text-accent underline" key={side} href={artifactDownloadUrl(sha)} download>Sprawdź źródło {side}</a> : <span className="mr-2 text-muted" key={side}>{side} · brak pliku</span>)}</li>)}</ul>}
        {tab === "Dowody" && <>        <div className="flex h-7 items-center justify-between border-b border-line px-2">
          <span className="cap">Co uzasadnia tę hipotezę</span>
          <span className="text-[0.85rem] text-faint">wersja modelu oceny powiązań · {data.model_version}</span>
        </div>
        {evidence.length === 0 ? (
          <Empty title="Krawędź nie ma zapisanych dowodów">To nie powinno się zdarzyć: silnik nie tworzy krawędzi bez dowodów. Zgłoś identyfikator krawędzi.</Empty>
        ) : (
          <ul>
            {(showAll ? evidence : evidence.slice(0, 3)).map((item, index) => (
              <EvidenceCard key={`${item.kind}:${item.value_a}:${index}`} item={item} max={max} refresh={edge.reload} />
            ))}
          </ul>
        )}
        {evidence.length > 3 && <button className="min-h-9 px-2 text-accent" onClick={() => setShowAll(!showAll)}>{showAll ? "Zwiń listę" : `Wszystkie przesłanki (${evidence.length})`}</button>}
        {!!review?.limitations.length && <aside className="m-2 rounded border border-amber-400 p-3"><h3>Ograniczenia hipotezy</h3>{review.limitations.map(text => <p key={text}>{text}</p>)}</aside>}
      <Decision
        key={`${data.id}:${data.updated_at}:${data.verdict_at}`}
        refresh={edge.reload}
        edge={data}
        onSaved={(saved) => {
          setResult(regroupMessage(saved.regroup));
          edge.set(saved);
          onVerdict?.(saved);
        }}
      />
      {result && <p role="status" className="p-2">{result}</p>}</>}
      </div>
    </div>
  );
}

export function EdgePanelEmpty() {
  return (
    <Empty title="Wybierz krawędź albo węzeł">
      Kliknij krawędź w grafie albo wiersz w tabeli, żeby zobaczyć dowody: typ markera, wartości po obu stronach, rzadkość w korpusie i wkład w bitach. Kliknięcie węzła otwiera kartę reklamy.
    </Empty>
  );
}


export function regroupMessage(regroup?: Regroup) {
  const changes = [...(regroup?.campaign ?? []), ...(regroup?.operator ?? [])];
  if (!changes.length) return "Zapisano ocenę. Skład grup pozostał ten sam.";
  return "Zapisano ocenę. " + changes.map(c => c.group + " → " + (c.after.map(g => g.key).join(", ") || "grupa rozwiązana") + (c.released.length ? " · uwolnione reklamy: " + c.released.join(", ") : "")).join(" · ");
}
