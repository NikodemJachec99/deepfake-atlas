"""Pobieranie strony przez usługę `crawler` (Chromium z Playwright w osobnym kontenerze).

Ten sam interfejs co `HttpFetcher`, plus HAR z przeglądarki, zrzut ekranu i przejścia skryptowe.
Gdy usługa nie odpowiada, wracamy do pobierania HTTP, żeby analiza nie stanęła.
"""

import base64
import logging
from urllib.parse import urlsplit

import httpx
from django.conf import settings

from .fetch import BlockedUrl, FetchResult, Hop, HttpFetcher, resolve_public

log = logging.getLogger(__name__)


def focus_on_document(har: dict, final_url: str) -> dict:
    """HAR zaczynający się od dokumentu strony końcowej.

    Ekstraktor HAR bierze pierwszy dokument HTML za stronę główną. Po przekierowaniu skryptowym
    pierwszym dokumentem jest strona pośrednia, więc ucinamy wszystko przed dokumentem końcowym.
    Przekierowania i tak są w łańcuchu z przeglądarki.
    """
    entries = har.get("log", {}).get("entries", [])
    target = final_url.split("#")[0]
    index = next(
        (
            i
            for i in range(len(entries) - 1, -1, -1)
            if entries[i]["request"]["url"].split("#")[0] == target
            and entries[i]["request"]["method"] == "GET"
            and "text/html" in (entries[i]["response"]["content"].get("mimeType") or "")
        ),
        0,
    )
    if index == 0:
        return har
    return {**har, "log": {**har["log"], "entries": entries[index:]}}


class BrowserFetcher:
    def __init__(self) -> None:
        self.url = settings.CRAWLER_BROWSER_URL.rstrip("/")
        self.timeout = settings.CRAWLER_BROWSER_TIMEOUT
        self.http = HttpFetcher()

    def fetch(self, url: str, profile: str = "victim") -> FetchResult:
        try:
            resolve_public(url)  # ta sama odmowa co w HttpFetcher, zanim cokolwiek wyślemy dalej
        except BlockedUrl as exc:
            return FetchResult(profile=profile, final_url=url, error=f"BlockedUrl: {exc}")
        try:
            response = httpx.post(f"{self.url}/render", json={"url": url, "profile": profile}, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("Usługa crawler nie odpowiada (%s), pobieram przez HTTP", exc)
            result = self.http.fetch(url, profile)
            result.engine = "http"
            result.notes.append(f"przeglądarka niedostępna: {type(exc).__name__}")
            return result
        return self.from_payload(data, profile)

    @staticmethod
    def from_payload(data: dict, profile: str) -> FetchResult:
        html = (data.get("html") or "").encode("utf-8")
        final_url = data.get("final_url") or ""
        har = data.get("har")
        if har and final_url:
            har = focus_on_document(har, final_url)
        try:
            screenshot = base64.b64decode(data.get("screenshot") or "")
        except ValueError:
            screenshot = b""
        notes = [f"zablokowane: {item}" for item in (data.get("blocked") or [])[:20]]
        return FetchResult(
            profile=profile,
            chain=[Hop(h["url"], int(h.get("status") or 0), h.get("via") or "http") for h in data.get("chain") or []],
            final_url=final_url,
            status=int(data.get("status") or 0),
            content_type=data.get("content_type") or "",
            body=html if urlsplit(final_url).scheme in ("http", "https") else b"",
            error=data.get("error") or "",
            engine="browser",
            har=har,
            screenshot=screenshot if screenshot.startswith(b"\x89PNG") else b"",
            console=[str(line) for line in (data.get("console") or [])[:50]],
            notes=notes,
        )

    def fetch_bytes(self, url: str, profile: str = "victim") -> bytes:
        return self.http.fetch_bytes(url, profile)
