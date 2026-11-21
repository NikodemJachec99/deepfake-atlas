"""Markery z adresu URL: domena, szablon ścieżki, zestaw parametrów i identyfikatory przemycane w parametrach."""

import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import tldextract

from . import Observation

# Bez pobierania listy sufiksów z sieci: używamy migawki dołączonej do biblioteki.
_extract = tldextract.TLDExtract(suffix_list_urls=(), cache_dir=None)

# Identyfikatory kliknięć doklejane przez platformy. Nie mówią nic o kampanii.
PLATFORM_PARAMS = {"fbclid", "gclid", "gbraid", "wbraid", "ttclid", "msclkid", "yclid", "twclid", "igshid", "_ga", "_gl"}
STANDARD_UTM = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "utm_id"}

# Parametry, w których lejki oszustów przenoszą własne identyfikatory.
PIXEL_PARAMS = {"pxl", "fbpx", "fbpixel", "pixel", "px", "fb_pixel"}
FUNNEL_PARAMS = {"key", "lpkey", "acc", "land_id", "_camp_id", "affid", "aff_id", "offer_id", "flow", "stream"}
AD_REF_PARAMS = {"ad_id", "adset_id", "campaign_id", "utm_id", "utm_content", "utm_term"}
AD_NAMING_PARAMS = {"ad_name", "adset_name", "campaign_name", "utm_campaign"}
SECRET_PARAMS = {"access_token", "token", "auth_token", "id_token", "api_key", "apikey", "secret", "signature"}
# Token dostępu Mety ma stały przedrostek. Łapiemy go pod każdą nazwą parametru.
_META_TOKEN = re.compile(r"^EAA[A-Za-z0-9]{30,}$")

_NUM = re.compile(r"^\d+$")
_TOKEN = re.compile(r"^(?=.*\d)[A-Za-z0-9_-]{12,}$|^[0-9a-fA-F]{8,}$")
_META_ID = re.compile(r"^\d{15,20}$")
_PIXEL_ID = re.compile(r"^\d{10,20}$")
_CYRILLIC = re.compile(r"[Ѐ-ӿ]{2,}")
_PLACEHOLDER = re.compile(r"[{}\[\]]|^%7b", re.I)


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


def domain_label(host: str) -> str:
    """Nazwa własna domeny bez końcówki, np. `jasnyporanek` dla `www.jasnyporanek.example`."""
    return registered_domain(host).split(".")[0]


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


def secret_hash(value: str) -> str:
    """Skrót sekretu. Pozwala powiązać dwa użycia tego samego tokenu bez przechowywania go."""
    if value.startswith("sha256-"):
        return value
    return "sha256-" + hashlib.sha256(value.encode()).hexdigest()[:16]


def is_secret(name: str, value: str) -> bool:
    return name.lower() in SECRET_PARAMS or bool(_META_TOKEN.match(value.strip()))


def redact_url(url: str) -> str:
    """Zamienia sekrety w adresie na skróty. Tokeny dostępu z cudzych kont nie mogą trafić do bazy ani do API."""
    parts = urlsplit(url)
    params = parse_qsl(parts.query, keep_blank_values=True)
    if not any(is_secret(k, v) for k, v in params):
        return url
    pairs = [(k, secret_hash(v) if is_secret(k, v) else v) for k, v in params]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(pairs), parts.fragment))


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

    params = [(k.lower(), v) for k, v in parse_qsl(parts.query, keep_blank_values=True)]
    keys = sorted({k for k, _ in params} - PLATFORM_PARAMS)
    # Standardowy zestaw utm_* ma połowa internetu. Marker powstaje dopiero, gdy jest coś własnego.
    if any(k not in STANDARD_UTM for k in keys):
        observations.append(Observation("url_param_keys", ",".join(keys)))

    for name, value in params:
        value = value.strip()
        if not value or _PLACEHOLDER.search(value):
            continue
        if is_secret(name, value):
            # Marker tokenu Mety tylko dla tokenów Mety. Inne sekrety po prostu nie trafiają do bazy.
            if name == "access_token" or _META_TOKEN.match(value) or value.startswith("sha256-"):
                observations.append(Observation("capi_token", secret_hash(value)))
        elif name in PIXEL_PARAMS and _PIXEL_ID.match(value):
            observations.append(Observation("meta_pixel", value, {"param": name}))
        elif name in AD_REF_PARAMS and _META_ID.match(value):
            observations.append(Observation("meta_ad_ref", value, {"param": name}))
        elif name in FUNNEL_PARAMS and len(value) >= 4:
            observations.append(Observation("funnel_param", f"{name}={value}"))
        elif name in AD_NAMING_PARAMS and len(value) >= 5 and not _NUM.match(value):
            observations.append(Observation("ad_naming", f"{name}={value}"))
        if _CYRILLIC.search(value):
            observations.append(Observation("lang_trace", "cyrillic", {"where": f"parametr {name}"}))
    return list(dict.fromkeys(observations))
