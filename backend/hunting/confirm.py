"""Potwierdzenie kandydata: strona pobrana przez crawlera w piaskownicy i porównana ze śladami operatora.

`observe` robi z kandydata te same obserwacje co etap extract potoku (`extract_page`, `parse_har`,
`url_observations`). `evaluate` zestawia je z markerami reklam operatora i liczy wynik tym samym modelem co
łączenie par (`fusion.score_pair`), więc waga każdego śladu w bitach pochodzi z `evidence/kinds.py` i z rzadkości
wartości w korpusie. Kandydat jest jednym ze źródeł wartości (liczymy go tak jak drugą reklamę w parze).

Strony nie renderujemy. Do bazy trafia jej HTML (do pobrania) i zrzut ekranu z przeglądarki.
"""

from dataclasses import dataclass, field

from crawler.fetch import FetchResult
from evidence import store
from evidence.kinds import KINDS
from evidence.models import AdMarker, Marker
from extractors import Observation
from extractors.har import parse_har
from extractors.html import extract_page
from extractors.url import host_of, redact_url, registered_domain, url_observations
from similarity import fusion
from similarity.models import Edge
from similarity.service import corpus_size, source_counts

from .profile import MAX_PROVENANCE

# Nazwa strony wynika z nazwy domeny, którą oceniamy osobno: liczenie jej drugi raz zawyżałoby wynik.
SKIP_KINDS = {"page_name"}
MAX_EVIDENCE = 12


@dataclass
class Observed:
    domain: str
    reachable: bool = False
    final_url: str = ""
    http_status: int | None = None
    error: str = ""
    html_sha: str = ""
    screenshot_sha: str = ""
    observations: list[Observation] = field(default_factory=list)


@dataclass
class Verdict:
    status: str
    bits: float
    probability: float
    evidence: list[dict]
    note: str


def _usable(result: FetchResult) -> bool:
    return not result.error and bool(result.body) and 0 < result.status < 400


def observe(domain: str, fetcher, enricher=None, *, try_http: bool = False) -> Observed:
    """Pobiera stronę główną domeny w profilu ofiary i wyciąga z niej markery. Błąd sieci daje `reachable=False`."""
    result = fetcher.fetch(f"https://{domain}/", "victim")
    if not _usable(result) and try_http:
        result = fetcher.fetch(f"http://{domain}/", "victim")
    out = Observed(domain, final_url=redact_url(result.final_url or ""), http_status=result.status or None)
    if not _usable(result):
        out.error = (result.error or (f"HTTP {result.status}" if result.status else "brak odpowiedzi"))[:300]
        return out

    out.reachable = True
    final_url = result.final_url
    observations: list[Observation] = list(url_observations(final_url))
    final_domain = registered_domain(host_of(final_url))
    hop_domains = {registered_domain(host_of(h.url)) for h in result.chain} - {final_domain, ""}
    observations += [Observation("redirect_domain", d) for d in sorted(hop_domains)]
    page = extract_page(result.html, final_url)
    observations += page.observations
    if page.dom_hash:
        observations.append(Observation("dom_hash", page.dom_hash))
    if result.har:
        observations += parse_har(result.har).observations

    out.html_sha = store.put(result.body, kind="html_victim", content_type=result.content_type, source_url=out.final_url).sha256
    if result.screenshot:
        out.screenshot_sha = store.put(result.screenshot, kind="page_screenshot", content_type="image/png", source_url=out.final_url).sha256

    if enricher is not None:
        observations += registry_observations(domain, enricher)
    out.observations = [o for o in dict.fromkeys(observations) if o.kind in KINDS and o.value and o.kind not in SKIP_KINDS]
    return out


def registry_observations(domain: str, enricher) -> list[Observation]:
    """Rejestrator, dzień rejestracji i serwery nazw: zapytania do rejestru (RDAP) i DNS, nie do strony kandydata."""
    found: list[Observation] = []
    try:
        rdap = enricher.rdap(domain)
        if rdap:
            if rdap.registrar:
                found.append(Observation("registrar", rdap.registrar))
            if rdap.registered_at:
                found.append(Observation("reg_day", rdap.registered_at.date().isoformat()))
            found += [Observation("nameserver", ns) for ns in rdap.nameservers]
        found += [Observation("nameserver", ns) for ns in enricher.nameservers(domain)]
    except Exception:  # noqa: BLE001  brak jednego źródła nie zatrzymuje potwierdzenia
        pass
    return found


def evaluate(ad_ids: list[int], observations: list[Observation]) -> Verdict:
    """Ślady strony wspólne z markerami reklam operatora, policzone modelem par. Nic nie zapisuje."""
    wanted = {(o.kind, Marker.hash_value(o.value)): o for o in observations}
    markers = {
        (m.kind, m.value_hash): m
        for m in Marker.objects.filter(value_hash__in=[h for _, h in wanted]).only("id", "kind", "value", "value_hash")
        if (m.kind, m.value_hash) in wanted
    }
    holders: dict[int, list[int]] = {}
    for marker_id, ad_id in AdMarker.objects.filter(marker_id__in=[m.pk for m in markers.values()], ad_id__in=ad_ids).values_list("marker_id", "ad_id"):
        holders.setdefault(marker_id, []).append(ad_id)

    known = [m for m in markers.values() if m.pk in holders]
    sources = source_counts([m.pk for m in known])
    shared = [fusion.Shared(m.kind, m.value, sources.get(m.pk, 1) + 1) for m in known]
    result = fusion.score_pair(shared, [], corpus_size() + 1)

    by_value = {(m.kind, m.value): m for m in known}
    evidence = []
    for item in result.evidence[:MAX_EVIDENCE]:
        marker = by_value[(item.kind, item.value_a)]
        evidence.append(
            {
                "kind": item.kind,
                "label": KINDS[item.kind].label,
                "family": item.family,
                "bits": round(item.weight_bits, 2),
                "raw_bits": round(item.raw_bits, 2),
                "decisive": item.decisive,
                "value": item.value_a[:120],
                "df": item.df,
                "ad_ids": sorted(holders[marker.pk])[:MAX_PROVENANCE],
            }
        )

    bits, probability = round(result.bits, 2), round(result.probability, 4)
    if result.relation in (Edge.Relation.SAME_CAMPAIGN, Edge.Relation.SAME_OPERATOR):
        top = ", ".join(e["label"] for e in evidence[:3])
        return Verdict("confirmed", bits, probability, evidence, f"Wspólne ślady z operatorem ({bits} bita): {top}"[:300])
    if bits >= fusion.FAMILY_MIN_BITS:
        return Verdict("candidate", bits, probability, evidence, f"Słabe dowody ({bits} bita), za mało na potwierdzenie bez drugiej niezależnej rodziny"[:300])
    return Verdict("rejected", bits, probability, evidence, "Strona działa, ale nie ma wspólnych śladów z operatorem")
