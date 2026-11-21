"""Ślady z pliku HAR: dokument główny, łańcuch przekierowań i odcisk zaplecza strony.

HAR pokazuje to, czego nie widać w zapisanym HTML: ścieżki, pod które strona woła swój serwer,
hosty zasobów, treść żądań POST i adres IP z chwili przechwycenia.
"""

import base64
import ipaddress
import re
from dataclasses import dataclass, field
from urllib.parse import parse_qsl, urlsplit

from . import Observation
from .html import TRACKERS
from .url import path_template, registered_domain

# Publiczne CDN-y i końcówki platform. Ma je prawie każda strona, więc niczego nie łączą.
COMMON_DOMAINS = {
    "cloudflare.com", "jsdelivr.net", "unpkg.com", "googleapis.com", "gstatic.com", "jquery.com", "facebook.net", "facebook.com",
    "google.com", "google.pl", "googletagmanager.com", "google-analytics.com", "doubleclick.net", "googlesyndication.com",
    "unsplash.com", "bootstrapcdn.com", "fontawesome.com", "gravatar.com", "youtube.com", "ytimg.com", "instagram.com",
    "fbcdn.net", "tiktok.com", "yandex.ru", "cloudflareinsights.com", "er-api.com", "w3.org",
}
# Platformy wielu najemców: o właścicielu mówi dopiero pełna nazwa hosta.
TENANT_SUFFIXES = (
    "b-cdn.net", "netlify.app", "pages.dev", "vercel.app", "herokuapp.com", "web.app", "firebaseapp.com", "github.io",
    "cloudfront.net", "amazonaws.com", "on.aws", "windows.net", "workers.dev", "onrender.com", "azurewebsites.net", "r2.dev",
    "supabase.co", "appspot.com", "run.app", "digitaloceanspaces.com", "fly.dev", "glitch.me", "replit.app", "shopifycdn.com",
)
CLOUDFLARE_NETS = [
    ipaddress.ip_network(net)
    for net in (
        "173.245.48.0/20", "103.21.244.0/22", "103.22.200.0/22", "103.31.4.0/22", "141.101.64.0/18", "108.162.192.0/18",
        "190.93.240.0/20", "188.114.96.0/20", "197.234.240.0/22", "198.41.128.0/17", "162.158.0.0/15", "104.16.0.0/13",
        "104.24.0.0/14", "172.64.0.0/13", "131.0.72.0/22",
    )
]

_GENERIC_PATH = re.compile(r"^/?$|favicon|robots\.txt|^/cdn-cgi/|apple-touch-icon|\.well-known", re.I)
_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
_REQUEST_TRACKERS = {
    "meta_pixel": re.compile(r"facebook\.com/tr/?\?(?:[^#]*&)?id=(\d{10,20})"),
    "google_ads": re.compile(r"/pagead/(?:viewthroughconversion|conversion)/(\d{8,12})"),
    "ga4": re.compile(r"[?&](?:id|tid)=(G-[A-Z0-9]{8,12})\b"),
    "gtm": re.compile(r"[?&]id=(GTM-[A-Z0-9]{5,8})\b"),
}
_BODY_TRACKERS = {**TRACKERS, "google_ads": [re.compile(r"\bAW-(\d{8,12})\b")]}
MAX_KIT_PATHS = 60
MAX_BODY = 2_000_000


@dataclass
class HarSummary:
    page_url: str = ""
    started_at: str = ""
    html: str = ""
    chain: list[dict] = field(default_factory=list)
    observations: list[Observation] = field(default_factory=list)
    server_ips: list[str] = field(default_factory=list)


def decode_content(content: dict) -> bytes:
    text = content.get("text") or ""
    if content.get("encoding") == "base64":
        try:
            return base64.b64decode(text)
        except ValueError:
            return b""
    return text.encode("utf-8", errors="replace")


def image_blobs(data: dict, limit: int = 120) -> list[bytes]:
    """Treść odpowiedzi będących obrazami. Z nich liczymy hasze percepcyjne strony."""
    blobs = []
    for entry in data.get("log", {}).get("entries", []):
        content = entry["response"]["content"]
        mime = content.get("mimeType") or ""
        if mime.startswith("image/") and "svg" not in mime and content.get("text"):
            blobs.append(decode_content(content))
            if len(blobs) >= limit:
                break
    return blobs


def is_cloudflare(ip: str) -> bool:
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(address in net for net in CLOUDFLARE_NETS)


def asset_host_value(host: str) -> str:
    return host if host.endswith(TENANT_SUFFIXES) else registered_domain(host)


def _header(entry: dict, name: str) -> str:
    return next((h["value"] for h in entry["response"].get("headers", []) if h["name"].lower() == name), "")


def parse_har(data: dict) -> HarSummary:
    entries = data.get("log", {}).get("entries", [])
    summary = HarSummary()
    if not entries:
        return summary

    def is_document(e: dict) -> bool:
        mime = e["response"]["content"].get("mimeType") or ""
        return e["request"]["method"] == "GET" and e["response"]["status"] == 200 and "text/html" in mime

    main_index = next((i for i, e in enumerate(entries) if is_document(e)), 0)
    main = entries[main_index]
    summary.page_url = main["request"]["url"]
    summary.started_at = entries[0].get("startedDateTime", "")
    summary.html = decode_content(main["response"]["content"]).decode("utf-8", errors="replace")
    own = registered_domain(urlsplit(summary.page_url).hostname or "")

    observations: list[Observation] = []
    # Wszystko, co prowadziło do dokumentu, to łańcuch przekierowań.
    for e in entries[:main_index]:
        if 300 <= e["response"]["status"] < 400:
            summary.chain.append({"url": e["request"]["url"], "status": e["response"]["status"], "via": "http"})
            hop = registered_domain(urlsplit(e["request"]["url"]).hostname or "")
            if hop and hop != own:
                observations.append(Observation("redirect_domain", hop))
    summary.chain.append({"url": summary.page_url, "status": main["response"]["status"], "via": "http"})
    hop_domains = {o.value for o in observations}

    kit_paths: list[str] = []
    ips: list[str] = []
    for e in entries[main_index:]:
        request = e["request"]
        parts = urlsplit(request["url"])
        host = (parts.hostname or "").lower()
        domain = registered_domain(host)
        method = request["method"]

        for kind, pattern in _REQUEST_TRACKERS.items():
            observations += [Observation(kind, m.group(1)) for m in pattern.finditer(request["url"])]

        if domain == own:
            ip = e.get("serverIPAddress") or ""
            if ip and ip not in ips:
                ips.append(ip)
            template = path_template(parts.path)
            depth = len([s for s in template.split("/") if s])
            if not _GENERIC_PATH.search(parts.path) and (depth >= 2 or method == "POST"):
                kit_paths.append(f"{method} {template}")
            if method == "POST":
                body = (request.get("postData") or {}).get("text") or ""
                for key, value in parse_qsl(body, keep_blank_values=False):
                    # Identyfikatory obiektów w panelu operatora. Identyfikator wizyty jest jednorazowy, więc odpada.
                    if "uuid" in key.lower() and _UUID.match(value) and value.lower() not in summary.page_url.lower():
                        observations.append(Observation("funnel_id", value.lower(), {"field": key}))
        elif host and domain not in COMMON_DOMAINS and domain not in hop_domains:
            observations.append(Observation("asset_host", asset_host_value(host), {"host": host}))

        mime = e["response"]["content"].get("mimeType") or ""
        if ("javascript" in mime or "html" in mime or "json" in mime) and domain not in COMMON_DOMAINS:
            body = decode_content(e["response"]["content"])[:MAX_BODY].decode("utf-8", errors="replace")
            for kind, patterns in _BODY_TRACKERS.items():
                for pattern in patterns:
                    observations += [Observation(kind, m.group(m.lastindex or 0)) for m in pattern.finditer(body)]

    observations += [Observation("kit_path", p) for p in sorted(set(kit_paths))[:MAX_KIT_PATHS]]

    summary.server_ips = ips
    for ip in ips:
        # Adres z puli Cloudflare dzielą miliony stron. Zapisujemy sam fakt użycia CDN.
        observations.append(Observation("cdn", "cloudflare") if is_cloudflare(ip) else Observation("ip", ip))

    server = _header(main, "server").split("/")[0].strip().lower()
    via = "caddy" if "caddy" in _header(main, "via").lower() else ""
    signature = "|".join(part for part in (server, via) if part)
    if signature:
        observations.append(Observation("server_sig", signature))

    summary.observations = list(dict.fromkeys(observations))
    return summary
