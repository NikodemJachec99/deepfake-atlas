"""Pobieranie stron docelowych: łańcuch przekierowań krok po kroku, w dwóch profilach.

To jest wersja HTTP bez przeglądarki. Widzi przekierowania 3xx i meta refresh, nie wykona
JavaScriptu. Crawler Playwright w piaskownicy zastąpi ją pod tym samym interfejsem `fetch`.
"""

import ipaddress
import re
import socket
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlsplit

import httpx
from django.conf import settings

# Dwa profile, bo strony oszustów pokazują co innego automatom, a co innego ofiarom.
PROFILES = {
    "victim": {
        "User-Agent": "Mozilla/5.0 (Linux; Android 14; SM-A546B) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Mobile Safari/537.36 [FB_IAB/FB4A;FBAV/489.0.0.66.81;]",
        "Accept-Language": "pl-PL,pl;q=0.9",
        "Referer": "https://l.facebook.com/",
    },
    "bot": {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) HeadlessChrome/131.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    },
}

_META_REFRESH = re.compile(
    r"<meta[^>]+http-equiv=[\"']?refresh[\"']?[^>]+content=[\"']?\s*\d+\s*;\s*url=([^\"'>\s]+)", re.I
)


class BlockedUrl(ValueError):
    pass


def resolve_public(url: str) -> str:
    """Rozwiązuje nazwę raz i zwraca publiczny adres IP, z którym crawler się połączy.

    Crawler przyjmuje adresy od użytkowników, więc nie może dać się wysłać do sieci wewnętrznej.
    Odmawiamy, gdy którykolwiek adres z DNS jest niepubliczny, a łączymy się z tym sprawdzonym,
    żeby podmiana DNS między sprawdzeniem a połączeniem (rebinding) nic nie dała.
    """
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise BlockedUrl(f"Niedozwolony adres: {url}")
    try:
        infos = socket.getaddrinfo(parts.hostname, parts.port or (443 if parts.scheme == "https" else 80))
    except socket.gaierror as exc:
        raise BlockedUrl(f"Nie można rozwiązać nazwy: {parts.hostname}") from exc
    addresses = [ipaddress.ip_address(info[4][0]) for info in infos]
    for ip in addresses:
        if not ip.is_global:
            raise BlockedUrl(f"Adres prowadzi do sieci niepublicznej: {parts.hostname} -> {ip}")
    if not addresses:
        raise BlockedUrl(f"Nie można rozwiązać nazwy: {parts.hostname}")
    return str(addresses[0])


def assert_public(url: str) -> None:
    resolve_public(url)


def pinned_request(url: str, ip: str) -> tuple[str, dict, dict]:
    """Adres z wpisanym sprawdzonym IP, nagłówek Host i SNI oryginalnej nazwy. Certyfikatu i tak nie weryfikujemy."""
    parts = urlsplit(url)
    host = f"[{ip}]" if ":" in ip else ip
    netloc = f"{host}:{parts.port}" if parts.port else host
    target = parts._replace(netloc=netloc).geturl()
    original = parts.hostname + (f":{parts.port}" if parts.port else "")
    extensions = {"sni_hostname": parts.hostname} if parts.scheme == "https" else {}
    return target, {"Host": original}, extensions


@dataclass
class Hop:
    url: str
    status: int
    via: str = ""  # http | meta_refresh


@dataclass
class FetchResult:
    profile: str
    chain: list[Hop] = field(default_factory=list)
    final_url: str = ""
    status: int = 0
    content_type: str = ""
    body: bytes = b""
    error: str = ""

    @property
    def html(self) -> str:
        return self.body.decode("utf-8", errors="replace")


class HttpFetcher:
    def __init__(self) -> None:
        self.timeout = settings.CRAWLER_TIMEOUT
        self.max_hops = settings.CRAWLER_MAX_HOPS
        self.max_bytes = settings.CRAWLER_MAX_BYTES
        self.proxy = settings.CRAWLER_PROXY or None

    def _client(self, profile: str) -> httpx.Client:
        # verify=False: zbieramy dowody także ze stron z wadliwym certyfikatem.
        return httpx.Client(
            headers=PROFILES[profile], timeout=self.timeout, follow_redirects=False, verify=False, proxy=self.proxy
        )

    def fetch(self, url: str, profile: str = "victim") -> FetchResult:
        result = FetchResult(profile=profile)
        current, via = url, "http"
        try:
            with self._client(profile) as client:
                for _ in range(self.max_hops + 1):
                    ip = resolve_public(current)
                    if self.proxy:
                        # Przez proxy nazwę rozwiązuje proxy; sprawdzenie zostaje, przypięcia nie da się zrobić.
                        target, headers, extensions = current, {}, {}
                    else:
                        target, headers, extensions = pinned_request(current, ip)
                    with client.stream("GET", target, headers=headers, extensions=extensions) as response:
                        body = b""
                        for chunk in response.iter_bytes():
                            body += chunk
                            if len(body) >= self.max_bytes:
                                break
                    result.chain.append(Hop(current, response.status_code, via))
                    location = response.headers.get("location")
                    if response.is_redirect and location:
                        current, via = urljoin(current, location), "http"
                        continue
                    refresh = _META_REFRESH.search(body[:20000].decode("utf-8", errors="replace"))
                    if refresh:
                        current, via = urljoin(current, refresh.group(1)), "meta_refresh"
                        continue
                    result.final_url = current
                    result.status = response.status_code
                    result.content_type = response.headers.get("content-type", "")
                    result.body = body
                    return result
                result.error = f"Przekroczono limit {self.max_hops} przekierowań"
        except (httpx.HTTPError, BlockedUrl) as exc:
            result.error = f"{type(exc).__name__}: {exc}"
        result.final_url = current
        return result

    def fetch_bytes(self, url: str, profile: str = "victim") -> bytes:
        result = self.fetch(url, profile)
        return result.body if result.status == 200 else b""
