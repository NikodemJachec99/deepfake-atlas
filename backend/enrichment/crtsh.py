"""Certyfikaty z dzienników Certificate Transparency (crt.sh).

Dla domeny strony bierzemy wszystkie wystawione certyfikaty, także dawne. Wspólny certyfikat
dwóch domen to ślad jednego konta: ktoś wystawił jeden certyfikat na kilka swoich stron.
Numer seryjny trafia do markera `tls_serial`, tego samego, który import paczek bierze z
`dns_ssl.json`, więc oba źródła łączą się ze sobą.

Odpowiedź trzymamy w bazie przez tydzień. Brak odpowiedzi crt.sh nie zatrzymuje analizy.
"""

from dataclasses import dataclass, field
from datetime import timedelta

from django.utils import timezone

from extractors import Observation
from extractors.url import registered_domain

from .models import CertLookup

CACHE_DAYS = 7
MAX_CERTS = 50  # najnowsze unikalne certyfikaty, starsze pomijamy
# Certyfikat na kilkanaście niezwiązanych domen to certyfikat współdzielony przez CDN,
# a nie ślad operatora. Taki pomijamy w całości.
MAX_SAN_DOMAINS = 10
SHARED_CERT_HOSTS = ("cloudflaressl.com",)


@dataclass
class Cert:
    serial: str
    crtsh_id: int
    issuer: str
    not_before: str
    names: list[str] = field(default_factory=list)

    @property
    def domains(self) -> list[str]:
        return sorted({registered_domain(n.removeprefix("*.")) for n in self.names if n})


def parse(raw: list[dict] | None) -> list[Cert]:
    """Odpowiedź crt.sh (output=json) na listę certyfikatów. Certyfikat i jego prekertyfikat to jeden wpis."""
    by_serial: dict[str, Cert] = {}
    for entry in raw or []:
        serial = str(entry.get("serial_number") or "").lower().strip()
        if not serial:
            continue
        names = {n.strip().lower() for n in str(entry.get("name_value") or "").splitlines() if n.strip()}
        if entry.get("common_name"):
            names.add(str(entry["common_name"]).strip().lower())
        crtsh_id = int(entry.get("id") or 0)
        cert = by_serial.get(serial)
        if cert is None:
            by_serial[serial] = Cert(
                serial=serial,
                crtsh_id=crtsh_id,
                issuer=str(entry.get("issuer_name") or ""),
                not_before=str(entry.get("not_before") or ""),
                names=sorted(names),
            )
        else:
            cert.names = sorted(set(cert.names) | names)
            cert.crtsh_id = min(filter(None, (cert.crtsh_id, crtsh_id)), default=0)
    certs = sorted(by_serial.values(), key=lambda c: c.not_before, reverse=True)
    return certs[:MAX_CERTS]


def shared_by_cdn(cert: Cert) -> bool:
    if any(n.endswith(host) for n in cert.names for host in SHARED_CERT_HOSTS):
        return True
    return len(cert.domains) > MAX_SAN_DOMAINS


def lookup(domain: str, source) -> list[Cert] | None:
    """Certyfikaty domeny. Najpierw pamięć w bazie, potem crt.sh. None, gdy crt.sh nie odpowiedział."""
    fresh = timezone.now() - timedelta(days=CACHE_DAYS)
    cached = CertLookup.objects.filter(domain=domain, fetched_at__gte=fresh).first()
    if cached is not None:
        return parse(cached.raw)
    raw = source.crtsh(domain)
    if raw is None:
        return None
    # Pustej listy nie zapisujemy: crt.sh pod obciążeniem potrafi ją zwrócić dla domeny,
    # która ma certyfikaty, a zapis ukryłby je na tydzień.
    if raw:
        CertLookup.objects.update_or_create(domain=domain, defaults={"raw": raw})
    return parse(raw)


def observations(domain: str, certs: list[Cert]) -> tuple[list[Observation], list[str]]:
    """Markery certyfikatów domeny i lista innych domen, które dzielą z nią certyfikat."""
    out: list[Observation] = []
    neighbours: set[str] = set()
    for cert in certs:
        if shared_by_cdn(cert):
            continue
        others = [d for d in cert.domains if d != domain]
        neighbours.update(others)
        detail = {"from": "crt.sh", "crtsh_id": cert.crtsh_id, "issuer": cert.issuer[:120], "not_before": cert.not_before}
        if others:
            detail["domains"] = others
        out.append(Observation("tls_serial", cert.serial, detail))
    return out, sorted(neighbours)
