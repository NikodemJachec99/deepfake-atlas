"""Źródła kandydatów: świeże certyfikaty z crt.sh po tokenach nazw i Lista Ostrzeżeń CERT Polska.

Żadne z nich nie dotyka strony kandydata. crt.sh pytamy przez istniejącego dostawcę (`enrichment.providers`):
jedno zapytanie naraz, z odstępem i pauzą po braku odpowiedzi. Odpowiedź trzymamy w bazie kilka godzin,
żeby powtórzony przebieg nie pytał o to samo, i tylko te pola, których używamy.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from django.db.models import Q
from django.utils import timezone

from enrichment.models import CertLookup, WarningDomain
from extractors.url import registered_domain

CACHE_HOURS = 6
MAX_WINDOW_DAYS = 90  # starsze certyfikaty nie trafiają do pamięci, łowca szuka świeżych domen
KEPT_FIELDS = ("id", "issuer_name", "name_value", "common_name", "not_before", "serial_number")


@dataclass
class Hit:
    domain: str
    sources: set[str] = field(default_factory=set)
    issuer: str = ""
    serial: str = ""
    not_before: datetime | None = None
    crtsh_id: int | None = None


def parse_time(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).strip().replace("Z", ""))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def trim(raw: list[dict], now: datetime) -> list[dict]:
    """Zostawia pola, których używamy, i certyfikaty nie starsze niż MAX_WINDOW_DAYS."""
    floor = now - timedelta(days=MAX_WINDOW_DAYS)
    out = []
    for entry in raw:
        issued = parse_time(entry.get("not_before", ""))
        if issued and issued >= floor:
            out.append({k: entry.get(k) for k in KEPT_FIELDS})
    return out


def search_certs(token: str, enricher, now: datetime | None = None) -> list[dict] | None:
    """Świeże certyfikaty z `token` w nazwie. Najpierw pamięć w bazie. None, gdy crt.sh nie odpowiedział."""
    now = now or timezone.now()
    key = f"hunt:{token}"
    cached = CertLookup.objects.filter(domain=key, fetched_at__gte=now - timedelta(hours=CACHE_HOURS)).first()
    if cached is not None:
        return cached.raw
    raw = enricher.crtsh_search(token)
    if raw is None:
        return None
    rows = trim(raw, now)
    CertLookup.objects.update_or_create(domain=key, defaults={"raw": rows})
    return rows


def _names(entry: dict) -> set[str]:
    names = {n.strip().lower() for n in str(entry.get("name_value") or "").splitlines() if n.strip()}
    if entry.get("common_name"):
        names.add(str(entry["common_name"]).strip().lower())
    return names


def hits_from_certs(rows: list[dict], cutoff: datetime) -> dict[str, Hit]:
    """Domeny rejestrowe z nazw w certyfikatach wystawionych po `cutoff`. Dla domeny zostaje najnowszy certyfikat."""
    hits: dict[str, Hit] = {}
    for entry in rows:
        issued = parse_time(entry.get("not_before", ""))
        if issued is None or issued < cutoff:
            continue
        for name in _names(entry):
            name = name.removeprefix("*.")
            if "." not in name or " " in name or name.replace(".", "").isdigit():
                continue
            domain = registered_domain(name)
            if not domain or "." not in domain:
                continue
            hit = hits.setdefault(domain, Hit(domain, {"crtsh"}))
            if hit.not_before is None or issued > hit.not_before:
                hit.not_before = issued
                hit.issuer = str(entry.get("issuer_name") or "")[:300]
                hit.serial = str(entry.get("serial_number") or "").lower()[:80]
                hit.crtsh_id = int(entry["id"]) if entry.get("id") else None
    return hits


def cert_pl_hits(tokens: list[str], cutoff: datetime) -> dict[str, Hit]:
    """Domeny z Listy Ostrzeżeń CERT Polska dodane po `cutoff`, których nazwa zawiera któryś z tokenów."""
    if not tokens:
        return {}
    match = Q()
    for token in tokens:
        match |= Q(domain__icontains=token)
    rows = WarningDomain.objects.filter(match, removed_at__isnull=True, added_at__gte=cutoff).values_list("domain", "added_at")
    hits: dict[str, Hit] = {}
    for name, _added in rows:
        domain = registered_domain(name.lower())
        if domain:
            hits.setdefault(domain, Hit(domain, {"cert_pl"}))
    return hits
