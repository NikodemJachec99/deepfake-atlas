"""Obserwacja strony: co dokładnie przechwycono, kiedy, skąd wiemy kiedy i w jakim kontekście przeglądarki.

Zapis trafia do `Ad.raw["observation"]`. Brak pola oznacza "nieznane", nie "brak". Sekrety z adresu
są redagowane przed zapisem, a z nagłówków bierzemy tylko to, co opisuje kontekst (przeglądarka,
język, czy były ciasteczka i referer), nigdy wartości ciasteczek.
"""

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from extractors.url import redact_url, registered_domain

MAX_HOSTS = 60
_BRAND = re.compile(r'"([^"]+)";v="(\d+)')


def normalize_url(url: str) -> str:
    """Adres po jawnej, bezpiecznej normalizacji: małe litery w schemacie i hoście, bez portu domyślnego
    i fragmentu, parametry posortowane. Żadnej wartości nie usuwamy, bo parametry decydują o wersji strony."""
    if not url:
        return ""
    parts = urlsplit(redact_url(url))
    host = (parts.hostname or "").lower()
    port = parts.port
    if port and not ((parts.scheme == "http" and port == 80) or (parts.scheme == "https" and port == 443)):
        host = f"{host}:{port}"
    query = urlencode(sorted(parse_qsl(parts.query, keep_blank_values=True)))
    return urlunsplit((parts.scheme.lower(), host, parts.path or "/", query, ""))


def browser_family(headers: dict[str, str]) -> str:
    brands = [name for name, _v in _BRAND.findall(headers.get("sec-ch-ua", "")) if "Not" not in name and name != "Chromium"]
    if brands:
        return brands[0]
    ua = headers.get("user-agent", "")
    for marker, name in (("Edg/", "Microsoft Edge"), ("OPR/", "Opera"), ("Firefox/", "Firefox"), ("Chrome/", "Google Chrome"), ("Safari/", "Safari")):
        if marker in ua:
            return name
    return ""


def document_request(har: dict | None) -> dict | None:
    entries = (har or {}).get("log", {}).get("entries", [])
    for entry in entries:
        mime = entry.get("response", {}).get("content", {}).get("mimeType") or ""
        if entry.get("request", {}).get("method") == "GET" and "text/html" in mime:
            return entry
    return entries[0] if entries else None


def context_from_har(har: dict | None) -> dict:
    entry = document_request(har)
    if not entry:
        return {}
    headers = {h["name"].lower(): h.get("value", "") for h in entry.get("request", {}).get("headers", [])}
    if not headers:
        return {}
    mobile = headers.get("sec-ch-ua-mobile")
    return {
        "browser": browser_family(headers),
        "platform": headers.get("sec-ch-ua-platform", "").strip('"'),
        "mobile": {"?1": True, "?0": False}.get(mobile),
        "accept_language": headers.get("accept-language", ""),
        "cookies": bool(headers.get("cookie")),
        "referer": bool(headers.get("referer")),
    }


def hosts_from_har(har: dict | None) -> list[str]:
    hosts = set()
    for entry in (har or {}).get("log", {}).get("entries", []):
        host = urlsplit(entry.get("request", {}).get("url", "")).hostname
        if host:
            hosts.add(host.lower())
    return sorted(hosts)[:MAX_HOSTS]


def observation_info(url: str, captured_at: str, time_source: str, har: dict | None) -> dict:
    exact = redact_url(url) if url else ""
    return {
        "exact_url": exact,
        "normalized_url": normalize_url(url),
        "domain": registered_domain(urlsplit(url).hostname or "") if url else "",
        "captured_at": captured_at or "",
        "time_source": time_source if captured_at else "",
        "context": context_from_har(har),
        "hosts": hosts_from_har(har),
    }
