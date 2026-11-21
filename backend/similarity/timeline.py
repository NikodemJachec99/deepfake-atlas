"""Oś obserwacji grupy reklam (kampanii albo operatora) dla trybu Evolution.

Każde zdarzenie mówi, jaki to rodzaj czasu i skąd go mamy:

- `observed`: chwila, w której materiał zobaczyło narzędzie przechwytujące, analityk albo nasz skan
  biblioteki. To moment obserwacji, a nie początek kampanii: kampania mogła działać wcześniej.
- `reported`: data podana przez zewnętrzne źródło: rejestracja domeny (RDAP), wystawienie certyfikatu
  (crt.sh), wpis na Listę Ostrzeżeń CERT Polska, start emisji podany przez bibliotekę reklam.

`precision` mówi, jak dokładna jest data (`exact` albo `day`). Niczego nie zgadujemy: rzecz bez daty
nie trafia na oś, tylko do liczników `undated`. Nie wnioskujemy też, że jedna domena zastąpiła drugą
albo że operator zmienił taktykę. Oś pokazuje kolejność obserwacji i nic ponad to.

Ostatnie wystąpienie i migawki to chwile skanu biblioteki reklam. Dla przechwycenia z paczki albo
zgłoszenia ręcznego byłaby to tylko data importu, więc ich nie pokazujemy. Tak samo pierwsze
wystąpienie przechwycenia, które w paczce nie miało daty i dostało datę importu.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from django.utils.dateparse import parse_datetime

from ads.models import Ad, AdSnapshot, Source
from enrichment.models import DomainRecord, WarningDomain
from evidence.kinds import KINDS
from evidence.models import AdMarker
from similarity.models import Edge

# Źródła, w których system sam obserwuje reklamę w czasie.
LIBRARY_SOURCES = {Source.META, Source.GOOGLE, Source.TIKTOK, Source.MICROSOFT, Source.NATIVE}
# Biblioteki, które podają datę startu emisji. Wtedy first_seen to data podana, a nie obserwacja.
REPORTED_START = {Source.META}

# Przechwycenie, którego pierwsze wystąpienie wypada tuż przy zapisie do bazy, nie miało własnej daty.
IMPORT_DATE_SLACK = timedelta(minutes=1)

# Ślady, których pojawienie się w grupie śledzimy: domeny, identyfikatory kont i lejka, kreacje, kontakty.
# Bez sygnatur, pasm, motywów (osoba, marka, tematyka) i wartości poufnych.
TRACE_KINDS = (
    "domain", "redirect_domain", "ip", "favicon_hash",
    "ga4", "ga_ua", "gtm", "meta_pixel", "yandex_metrica", "tiktok_pixel", "google_ads",
    "funnel_id", "funnel_param", "asset_host", "form_action",
    "creative_sha256", "creative_phash",
    "phone", "email", "telegram", "whatsapp", "crypto_btc", "crypto_eth", "iban",
    "advertiser_id", "payer",
)

# Kolejność zdarzeń z tą samą datą: najpierw zaplecze, potem reklama, potem to, co z niej wynika.
ORDER = [
    "domain_registered", "cert_issued", "ad_first_seen", "trace_first_observed", "link_observable",
    "snapshot", "ad_last_seen", "cert_pl_added", "cert_pl_removed",
]
LABELS = {
    "domain_registered": "Rejestracja domeny",
    "cert_issued": "Wystawienie certyfikatu",
    "ad_first_seen": "Pierwsze wystąpienie reklamy",
    "trace_first_observed": "Pierwsza obserwacja śladu w grupie",
    "link_observable": "Powiązania możliwe do zaobserwowania",
    "snapshot": "Migawka reklamy",
    "ad_last_seen": "Ostatnie wystąpienie reklamy",
    "cert_pl_added": "Wpis na Listę Ostrzeżeń CERT Polska",
    "cert_pl_removed": "Zdjęcie z Listy Ostrzeżeń CERT Polska",
}


@dataclass(frozen=True)
class Seen:
    """Data wraz z rodzajem czasu, źródłem i dokładnością."""

    at: datetime
    time_kind: str
    source: str
    precision: str = "exact"


def _event(kind: str, when: Seen, ads, value: str = "", detail: dict | None = None) -> dict:
    return {
        "type": kind,
        "label": LABELS[kind],
        "at": when.at,
        "time_kind": when.time_kind,
        "source": when.source,
        "precision": when.precision,
        "ads": sorted(ads),
        "value": value,
        "detail": detail or {},
    }


def _cert_date(raw: str) -> datetime | None:
    if not raw:
        return None
    parsed = parse_datetime(raw)
    if parsed is None:
        # dns_ssl.json z archiwum NASK ma format OpenSSL: "Oct  7 18:53:02 2026 GMT"
        try:
            return datetime.strptime(" ".join(raw.split()), "%b %d %H:%M:%S %Y GMT").replace(tzinfo=UTC)
        except ValueError:
            return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)  # crt.sh podaje czas UTC bez strefy


def ad_seen(ad: Ad) -> Seen | None:
    """Kiedy i skąd wiemy o reklamie. None, gdy jedyna data to chwila importu."""
    if not ad.first_seen:
        return None
    if ad.source == Source.CAPTURE and abs(ad.first_seen - ad.created_at) < IMPORT_DATE_SLACK:
        return None
    if ad.source in REPORTED_START:
        return Seen(ad.first_seen, "reported", str(ad.source), "day")
    return Seen(ad.first_seen, "observed", str(ad.source))


def _ad_events(ads: list[Ad], seen: dict[int, Seen]) -> list[dict]:
    out = []
    for ad in ads:
        if ad.pk in seen:
            out.append(_event("ad_first_seen", seen[ad.pk], [ad.pk]))
        if ad.source in LIBRARY_SOURCES and ad.last_seen and ad.last_seen != ad.first_seen:
            out.append(_event("ad_last_seen", Seen(ad.last_seen, "observed", str(ad.source)), [ad.pk]))
    source_of = {ad.pk: str(ad.source) for ad in ads if ad.source in LIBRARY_SOURCES}
    for snap in AdSnapshot.objects.filter(ad_id__in=source_of):
        out.append(_event("snapshot", Seen(snap.observed_at, "observed", source_of[snap.ad_id]), [snap.ad_id], detail={"active": snap.active}))
    return out


def _domain_events(ads_by_domain: dict[str, set[int]]) -> list[dict]:
    out = []
    for record in DomainRecord.objects.filter(domain__in=ads_by_domain, registered_at__isnull=False):
        detail = {"registrar": record.registrar} if record.registrar else {}
        out.append(_event("domain_registered", Seen(record.registered_at, "reported", "rdap"), ads_by_domain[record.domain], record.domain, detail))
    for listed in WarningDomain.objects.filter(domain__in=ads_by_domain):
        ads = ads_by_domain[listed.domain]
        if listed.added_at:
            out.append(_event("cert_pl_added", Seen(listed.added_at, "reported", "cert_pl"), ads, listed.domain))
        if listed.removed_at:
            out.append(_event("cert_pl_removed", Seen(listed.removed_at, "reported", "cert_pl"), ads, listed.domain))
    return out


def _cert_events(ad_ids: list[int], undated: dict) -> list[dict]:
    """Certyfikaty z crt.sh. Odnowienia (te same reklamy i te same pozostałe domeny) to jedna seria:
    data pierwszego wystawienia, liczba wystawień i data ostatniego."""
    by_serial: dict[str, dict] = {}
    rows = AdMarker.objects.filter(ad_id__in=ad_ids, marker__kind="tls_serial").values_list("ad_id", "marker__value", "detail")
    for ad_id, serial, detail in rows:
        detail = detail or {}
        entry = by_serial.setdefault(serial, {"at": None, "source": "", "ads": set(), "issuer": "", "domains": set()})
        entry["ads"].add(ad_id)
        at = _cert_date(detail.get("not_before", ""))
        # Ta sama data z crt.sh i z certyfikatu w przechwyceniu. Pierwszeństwo ma crt.sh, bo podaje wystawcę.
        if at and (entry["at"] is None or detail.get("from") == "crt.sh"):
            entry["at"], entry["source"] = at, "crt.sh" if detail.get("from") == "crt.sh" else "capture"
        entry["issuer"] = entry["issuer"] or detail.get("issuer", "")
        entry["domains"].update(detail.get("domains", []))
    series: dict[tuple, list[tuple[datetime, str, str, str]]] = defaultdict(list)
    for serial, entry in by_serial.items():
        if entry["at"] is None:
            undated["certificates"] += 1
            continue
        key = (tuple(sorted(entry["ads"])), tuple(sorted(entry["domains"])))
        series[key].append((entry["at"], serial, entry["issuer"], entry["source"]))
    out = []
    for (ads, domains), certs in series.items():
        certs.sort()
        first_at, first_serial, issuer, source = certs[0]
        detail: dict = {"issuer": issuer, "count": len(certs)}
        if domains:
            detail["domains"] = list(domains)
        if len(certs) > 1:
            detail["last_at"] = certs[-1][0].isoformat()
        out.append(_event("cert_issued", Seen(first_at, "reported", source), ads, first_serial, detail))
    return out


def _trace_events(ad_ids: list[int], seen: dict[int, Seen], undated: dict) -> list[dict]:
    """Pierwsza obserwacja każdego śladu w grupie. Kilka reklam z tą samą najwcześniejszą datą
    podajemy razem: nie rozstrzygamy, która była pierwsza."""
    holders: dict[tuple[str, str], set[int]] = defaultdict(set)
    rows = AdMarker.objects.filter(ad_id__in=ad_ids, marker__kind__in=TRACE_KINDS).values_list("marker__kind", "marker__value", "ad_id")
    for kind, value, ad_id in rows:
        holders[(kind, value)].add(ad_id)
    out = []
    for (kind, value), ads in holders.items():
        dated = [ad for ad in ads if ad in seen]
        if not dated:
            undated["traces"] += 1
            continue
        first = min(seen[ad].at for ad in dated)
        earliest = [ad for ad in dated if seen[ad].at == first]
        detail = {"kind": kind, "kind_label": KINDS[kind].label, "family": KINDS[kind].family, "in_group": len(ads)}
        if len(earliest) > 1:
            detail["tied"] = True
        if len(ads) > len(dated):
            detail["undated_ads"] = len(ads) - len(dated)
        out.append(_event("trace_first_observed", seen[min(earliest)], earliest, value[:200], detail))
    return out


LINK_LIST_LIMIT = 50


def _link_events(ad_ids: list[int], relations: list[str], seen: dict[int, Seen], undated: dict) -> list[dict]:
    """Powiązanie da się zaobserwować dopiero, gdy obie reklamy są w ręku. To nie jest data, w której
    operator je połączył. Jedno zdarzenie na reklamę, która dołącza do grupy: z iloma wcześniej widzianymi
    reklamami się wiąże. Przy tej samej chwili obu reklam nie wiemy, która była pierwsza: przypisujemy parę
    reklamie o wyższym numerze i oznaczamy remis."""
    joins: dict[int, dict] = {}
    edges = Edge.objects.filter(ad_a_id__in=ad_ids, ad_b_id__in=ad_ids, relation__in=relations).exclude(verdict=Edge.Verdict.REJECTED)
    for edge in edges.order_by("pk"):
        a, b = seen.get(edge.ad_a_id), seen.get(edge.ad_b_id)
        if a is None or b is None:
            undated["links"] += 1
            continue
        tied = a.at == b.at
        if tied:
            joining, partner = max(edge.ad_a_id, edge.ad_b_id), min(edge.ad_a_id, edge.ad_b_id)
        else:
            joining, partner = (edge.ad_b_id, edge.ad_a_id) if b.at > a.at else (edge.ad_a_id, edge.ad_b_id)
        entry = joins.setdefault(joining, {"partners": [], "edges": [], "relations": {}, "max_probability": 0.0, "tied": False})
        entry["partners"].append(partner)
        entry["edges"].append(edge.pk)
        entry["relations"][edge.relation] = entry["relations"].get(edge.relation, 0) + 1
        entry["max_probability"] = max(entry["max_probability"], round(edge.probability, 4))
        entry["tied"] = entry["tied"] or tied
    out = []
    for joining, entry in joins.items():
        count = len(entry["edges"])
        detail = {
            "count": count,
            "relations": dict(sorted(entry["relations"].items())),
            "partners": sorted(entry["partners"])[:LINK_LIST_LIMIT],
            "edges": sorted(entry["edges"])[:LINK_LIST_LIMIT],
            "max_probability": entry["max_probability"],
        }
        if count > LINK_LIST_LIMIT:
            detail["truncated"] = True
        if entry["tied"]:
            detail["tied"] = True
        out.append(_event("link_observable", seen[joining], [joining], str(count), detail))
    return out


def build(ad_ids: list[int], relations: list[str]) -> dict:
    """Zdarzenia grupy posortowane po dacie i liczniki tego, czego nie da się umieścić w czasie."""
    undated = {"ads": [], "traces": 0, "links": 0, "certificates": 0}
    ads = list(Ad.objects.filter(pk__in=ad_ids).only("id", "source", "first_seen", "last_seen", "created_at"))
    seen = {ad.pk: s for ad in ads if (s := ad_seen(ad))}
    undated["ads"] = sorted(ad.pk for ad in ads if ad.pk not in seen)

    ads_by_domain: dict[str, set[int]] = defaultdict(set)
    for ad_id, value in AdMarker.objects.filter(ad_id__in=ad_ids, marker__kind="domain").values_list("ad_id", "marker__value"):
        ads_by_domain[value].add(ad_id)

    events = [
        *_ad_events(ads, seen),
        *_domain_events(ads_by_domain),
        *_cert_events(ad_ids, undated),
        *_trace_events(ad_ids, seen, undated),
        *_link_events(ad_ids, relations, seen, undated),
    ]
    events.sort(key=lambda e: (e["at"], ORDER.index(e["type"]), e["ads"], e["value"]))
    for event in events:
        event["at"] = event["at"].isoformat()
    return {"events": events, "undated": undated}
