"""Zamienniki sieci w testach. Strony i dane DNS podaje się w słownikach."""

from datetime import UTC, datetime

from crawler.fetch import FetchResult, Hop
from enrichment.providers import NullEnricher, RdapInfo

PAGES: dict[str, dict] = {}
DNS: dict[str, dict] = {}


def reset() -> None:
    PAGES.clear()
    DNS.clear()


def page(url: str, html: str, *, bot_html: str | None = None, chain: list[str] | None = None, favicon: bytes = b"") -> None:
    PAGES[url] = {"html": html, "bot_html": bot_html, "chain": chain or [], "favicon": favicon}


class FakeFetcher:
    def fetch(self, url: str, profile: str = "victim") -> FetchResult:
        entry = PAGES.get(url)
        if entry is None:
            return FetchResult(profile=profile, final_url=url, error="ConnectError: brak strony w teście")
        html = entry["bot_html"] if profile == "bot" and entry["bot_html"] is not None else entry["html"]
        hops = [Hop(u, 302) for u in entry["chain"]]
        return FetchResult(
            profile=profile,
            chain=[*hops, Hop(url, 200)],
            final_url=url,
            status=200,
            content_type="text/html",
            body=html.encode("utf-8"),
        )

    def fetch_bytes(self, url: str, profile: str = "victim") -> bytes:
        host = url.split("/")[2]
        for entry_url, entry in PAGES.items():
            if entry_url.split("/")[2] == host:
                return entry["favicon"]
        return b""


class FakeEnricher(NullEnricher):
    def resolve(self, host: str) -> list[str]:
        return DNS.get(host, {}).get("ips", [])

    def asn(self, ip: str) -> str:
        return "AS13335"

    def nameservers(self, domain: str) -> list[str]:
        return DNS.get(domain, {}).get("ns", [])

    def rdap(self, domain: str) -> RdapInfo | None:
        entry = DNS.get(domain, {})
        if "registrar" not in entry:
            return None
        return RdapInfo(
            registrar=entry["registrar"], registered_at=datetime(2026, 3, 1, tzinfo=UTC), nameservers=entry.get("ns", [])
        )
