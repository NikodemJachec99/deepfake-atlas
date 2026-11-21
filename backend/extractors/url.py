"""Markery z adresu URL: domena rejestrowa, szablon ścieżki, zestaw nazw parametrów."""

import re
from urllib.parse import parse_qsl, urlsplit

import tldextract

from . import Observation

# Bez pobierania listy sufiksów z sieci: używamy migawki dołączonej do biblioteki.
_extract = tldextract.TLDExtract(suffix_list_urls=(), cache_dir=None)

# Identyfikatory kliknięć doklejane przez platformy. Nie mówią nic o kampanii.
PLATFORM_PARAMS = {"fbclid", "gclid", "gbraid", "wbraid", "ttclid", "msclkid", "yclid", "twclid", "igshid", "_ga", "_gl"}

_NUM = re.compile(r"^\d+$")
_TOKEN = re.compile(r"^(?=.*\d)[A-Za-z0-9_-]{12,}$|^[0-9a-fA-F]{8,}$")


def host_of(url: str) -> str:
    return (urlsplit(url).hostname or "").lower().rstrip(".")


def registered_domain(host: str) -> str:
    """Domena rejestrowa (eTLD+1). Dla nieznanych końcówek bierzemy dwie ostatnie etykiety."""
    host = host.lower().rstrip(".")
    if not host:
        return ""
    parts = _extract(host)
    if parts.suffix and parts.domain:
        return f"{parts.domain}.{parts.suffix}"
    labels = host.split(".")
    return ".".join(labels[-2:]) if len(labels) >= 2 else host


def path_template(path: str) -> str:
    out = []
    for segment in path.split("/"):
        if _NUM.match(segment):
            out.append("{n}")
        elif _TOKEN.match(segment):
            out.append("{id}")
        else:
            out.append(segment.lower())
    return "/".join(out)


def url_observations(url: str) -> list[Observation]:
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    observations = []
    domain = registered_domain(host)
    if domain:
        observations.append(Observation("domain", domain, {"host": host}))

    path = parts.path.rstrip("/")
    if path:
        observations.append(Observation("url_path_tpl", path_template(path)))

    keys = sorted({k.lower() for k, _ in parse_qsl(parts.query, keep_blank_values=True)} - PLATFORM_PARAMS)
    # Sam zestaw utm_* ma połowa internetu. Marker powstaje dopiero, gdy jest coś własnego.
    if any(not k.startswith("utm_") for k in keys):
        observations.append(Observation("url_param_keys", ",".join(keys)))
    return observations
