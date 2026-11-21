"""Oś czasu grupy reklam (kampanii albo operatora) dla trybu Evolution.

Zbiera zdarzenia, które mają datę w bazie: pierwsze i ostatnie wystąpienie reklamy, migawki,
rejestrację domeny (RDAP), wystawienie certyfikatu (crt.sh) i wpis domeny na Listę Ostrzeżeń
CERT Polska. Niczego nie zgaduje: zdarzenie bez daty się nie pojawia.

Ostatnie wystąpienie i migawki to chwile, w których system widział reklamę w bibliotece reklam.
Dla przechwycenia z paczki albo zgłoszenia ręcznego to tylko data importu, więc ich nie pokazujemy.
Tak samo pierwsze wystąpienie przechwycenia, które w paczce nie miało daty i dostało datę importu.
"""

from collections import defaultdict
from datetime import UTC, datetime, timedelta

from django.utils.dateparse import parse_datetime

from ads.models import Ad, AdSnapshot, Source
from enrichment.models import DomainRecord, WarningDomain
from evidence.models import AdMarker

# Źródła, w których system sam obserwuje reklamę w czasie.
LIBRARY_SOURCES = {Source.META, Source.GOOGLE, Source.TIKTOK, Source.MICROSOFT, Source.NATIVE}

# Przechwycenie, którego pierwsze wystąpienie wypada tuż przy zapisie do bazy, nie miało własnej daty.
IMPORT_DATE_SLACK = timedelta(minutes=1)

# Kolejność zdarzeń z tą samą datą: najpierw zaplecze, potem reklama.
ORDER = ["domain_registered", "cert_issued", "ad_first_seen", "snapshot", "ad_last_seen", "cert_pl_added", "cert_pl_removed"]
LABELS = {
    "domain_registered": "Rejestracja domeny",
    "cert_issued": "Wystawienie certyfikatu",
    "ad_first_seen": "Pierwsze wystąpienie reklamy",
    "snapshot": "Migawka reklamy",
    "ad_last_seen": "Ostatnie wystąpienie reklamy",
    "cert_pl_added": "Wpis na Listę Ostrzeżeń CERT Polska",
    "cert_pl_removed": "Zdjęcie z Listy Ostrzeżeń CERT Polska",
}


def _event(kind: str, at: datetime, ads: list[int], value: str = "", detail: dict | None = None) -> dict:
    return {"type": kind, "label": LABELS[kind], "at": at.isoformat(), "ads": sorted(ads), "value": value, "detail": detail or {}}


def _cert_date(raw: str) -> datetime | None:
    if not raw:
        return None
    parsed = parse_datetime(raw)
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)  # crt.sh podaje czas UTC bez strefy
    return parsed


def events_for(ad_ids: list[int]) -> list[dict]:
    out: list[dict] = []
    ads = Ad.objects.filter(pk__in=ad_ids).only("id", "source", "first_seen", "last_seen", "created_at")
    observed: list[int] = []
    for ad in ads:
        import_date = ad.source == Source.CAPTURE and ad.first_seen and abs(ad.first_seen - ad.created_at) < IMPORT_DATE_SLACK
        if ad.first_seen and not import_date:
            out.append(_event("ad_first_seen", ad.first_seen, [ad.pk]))
        if ad.source not in LIBRARY_SOURCES:
            continue
        observed.append(ad.pk)
        if ad.last_seen and ad.last_seen != ad.first_seen:
            out.append(_event("ad_last_seen", ad.last_seen, [ad.pk]))
    for snap in AdSnapshot.objects.filter(ad_id__in=observed):
        out.append(_event("snapshot", snap.observed_at, [snap.ad_id], detail={"active": snap.active}))

    ads_by_domain: dict[str, set[int]] = defaultdict(set)
    for ad_id, value in AdMarker.objects.filter(ad_id__in=ad_ids, marker__kind="domain").values_list("ad_id", "marker__value"):
        ads_by_domain[value].add(ad_id)
    for record in DomainRecord.objects.filter(domain__in=ads_by_domain, registered_at__isnull=False):
        out.append(_event("domain_registered", record.registered_at, list(ads_by_domain[record.domain]), record.domain,
                          {"registrar": record.registrar} if record.registrar else {}))
    for listed in WarningDomain.objects.filter(domain__in=ads_by_domain):
        if listed.added_at:
            out.append(_event("cert_pl_added", listed.added_at, list(ads_by_domain[listed.domain]), listed.domain))
        if listed.removed_at:
            out.append(_event("cert_pl_removed", listed.removed_at, list(ads_by_domain[listed.domain]), listed.domain))

    # Certyfikat ma datę tylko z crt.sh. Ten sam numer u kilku reklam to jedno zdarzenie.
    certs: dict[str, dict] = {}
    rows = AdMarker.objects.filter(ad_id__in=ad_ids, marker__kind="tls_serial").values_list("ad_id", "marker__value", "detail")
    for ad_id, serial, detail in rows:
        at = _cert_date((detail or {}).get("not_before", ""))
        if at is None:
            continue
        entry = certs.setdefault(serial, {"at": at, "ads": set(), "detail": {}})
        entry["ads"].add(ad_id)
        for key in ("issuer", "domains"):
            if key in (detail or {}):
                entry["detail"][key] = detail[key]
    for serial, entry in certs.items():
        out.append(_event("cert_issued", entry["at"], list(entry["ads"]), serial, entry["detail"]))

    return sorted(out, key=lambda e: (e["at"], ORDER.index(e["type"]), e["ads"], e["value"]))
