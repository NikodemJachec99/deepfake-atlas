"""Wzbogacanie domeny landingu: DNS, system autonomiczny, certyfikat, dane rejestrowe.

Każda metoda zwraca pustą wartość zamiast rzucać wyjątek poza moduł: brak jednego źródła
nie może zatrzymać analizy reklamy.
"""

import hashlib
import socket
import ssl
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime

import dns.resolver
import httpx

RDAP_PL = "https://rdap.dns.pl/domain/{domain}"
RDAP_BOOTSTRAP = "https://rdap.org/domain/{domain}"
CRTSH = "https://crt.sh/"
CRTSH_TIMEOUT = 25.0  # crt.sh bywa wolny, ale dłużej analiza nie czeka
CRTSH_SEARCH_TIMEOUT = 90.0  # wyszukiwanie po fragmencie nazwy (łowca domen) liczy się długo
CRTSH_INTERVAL = 3.0  # odstęp między zapytaniami z jednego procesu, crt.sh prosi o umiar
CRTSH_PAUSE = 600.0  # po braku odpowiedzi nie pytamy przez 10 minut
_crtsh_lock = threading.Lock()
_crtsh_last = 0.0
_crtsh_down_until = 0.0


@dataclass
class RdapInfo:
    registrar: str = ""
    registered_at: datetime | None = None
    nameservers: list[str] = field(default_factory=list)
    raw: dict = field(default_factory=dict)


def parse_rdap(data: dict) -> RdapInfo:
    info = RdapInfo(raw=data)
    for event in data.get("events", []):
        if event.get("eventAction") == "registration" and event.get("eventDate"):
            info.registered_at = datetime.fromisoformat(event["eventDate"].replace("Z", "+00:00"))
    for entity in data.get("entities", []):
        if "registrar" in entity.get("roles", []):
            for item in (entity.get("vcardArray") or [None, []])[1]:
                if item[0] == "fn":
                    info.registrar = item[3]
    info.nameservers = sorted(ns.get("ldhName", "").lower().rstrip(".") for ns in data.get("nameservers", []) if ns.get("ldhName"))
    return info


class LiveEnricher:
    def __init__(self, timeout: float = 8.0) -> None:
        self.timeout = timeout
        self.resolver = dns.resolver.Resolver()
        self.resolver.lifetime = timeout

    def resolve(self, host: str) -> list[str]:
        try:
            return sorted({r.address for r in self.resolver.resolve(host, "A")})
        except Exception:
            return []

    def nameservers(self, domain: str) -> list[str]:
        try:
            return sorted({str(r.target).lower().rstrip(".") for r in self.resolver.resolve(domain, "NS")})
        except Exception:
            return []

    def asn(self, ip: str) -> str:
        """Numer AS z usługi Team Cymru (zapytanie DNS TXT)."""
        try:
            reversed_ip = ".".join(reversed(ip.split(".")))
            answer = self.resolver.resolve(f"{reversed_ip}.origin.asn.cymru.com", "TXT")
            number = str(answer[0]).strip('"').split("|")[0].strip().split(" ")[0]
            return f"AS{number}" if number.isdigit() else ""
        except Exception:
            return ""

    def tls_fingerprint(self, host: str, port: int = 443) -> str:
        """Odcisk certyfikatu. Łączymy się tylko z publicznym adresem sprawdzonym tak jak w crawlerze,
        z nazwą w SNI, żeby podmiana DNS nie skierowała połączenia do sieci wewnętrznej."""
        from crawler.fetch import BlockedUrl, resolve_public

        try:
            ip = resolve_public(f"https://{host}:{port}/")
        except BlockedUrl:
            return ""
        try:
            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            with socket.create_connection((ip, port), timeout=self.timeout) as sock:
                with context.wrap_socket(sock, server_hostname=host) as tls:
                    der = tls.getpeercert(binary_form=True)
            return hashlib.sha256(der).hexdigest() if der else ""
        except Exception:
            return ""

    def rdap(self, domain: str) -> RdapInfo | None:
        url = (RDAP_PL if domain.endswith(".pl") else RDAP_BOOTSTRAP).format(domain=domain)
        try:
            response = httpx.get(url, timeout=self.timeout, follow_redirects=True)
            if response.status_code != 200:
                return None
            return parse_rdap(response.json())
        except Exception:
            return None


    def crtsh(self, domain: str) -> list[dict] | None:
        """Surowa odpowiedź crt.sh albo None, gdy nie odpowiedział. Zapytania idą po kolei, z odstępem.

        Po nieudanym zapytaniu crt.sh jest pomijany przez CRTSH_PAUSE, żeby import kilkudziesięciu
        stron nie czekał na każdy limit czasu osobno.
        """
        return self._crtsh_get({"q": domain, "output": "json"}, CRTSH_TIMEOUT)

    def crtsh_search(self, token: str) -> list[dict] | None:
        """Certyfikaty z nazwą zawierającą `token` (zapytanie `%token%`), tylko niewygasłe. Łowca domen.

        Zapytania z wieloznacznikiem są dla crt.sh drogie, więc mają dłuższy limit czasu, ale idą tym samym
        torem co zwykłe: jedno naraz, z odstępem i z pauzą po braku odpowiedzi.
        """
        return self._crtsh_get({"q": f"%{token}%", "output": "json", "exclude": "expired"}, CRTSH_SEARCH_TIMEOUT)

    def _crtsh_get(self, params: dict, timeout: float) -> list[dict] | None:
        global _crtsh_last, _crtsh_down_until
        with _crtsh_lock:
            if time.monotonic() < _crtsh_down_until:
                return None
            wait = _crtsh_last + CRTSH_INTERVAL - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            data = None
            try:
                response = httpx.get(CRTSH, params=params, timeout=timeout)
                if response.status_code == 200:
                    parsed = response.json()
                    data = parsed if isinstance(parsed, list) else None
            except Exception:
                data = None
            _crtsh_last = time.monotonic()
            if data is None:
                _crtsh_down_until = _crtsh_last + CRTSH_PAUSE
            return data


class NullEnricher:
    """Bez sieci. Do testów i pracy offline."""

    def resolve(self, host: str) -> list[str]:
        return []

    def nameservers(self, domain: str) -> list[str]:
        return []

    def asn(self, ip: str) -> str:
        return ""

    def tls_fingerprint(self, host: str, port: int = 443) -> str:
        return ""

    def rdap(self, domain: str) -> RdapInfo | None:
        return None

    def crtsh(self, domain: str) -> list[dict] | None:
        return []

    def crtsh_search(self, token: str) -> list[dict] | None:
        return []
