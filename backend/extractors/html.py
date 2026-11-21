"""Markery ze strony docelowej: identyfikatory śledzące, lejek, kontakty i odcisk szablonu."""

import hashlib
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from . import Observation, minhash
from .text import contact_observations, digits
from .url import host_of, registered_domain

TRACKERS: dict[str, list[re.Pattern]] = {
    "ga4": [re.compile(r"\bG-[A-Z0-9]{8,12}\b")],
    "ga_ua": [re.compile(r"\bUA-\d{4,10}-\d{1,4}\b")],
    "gtm": [re.compile(r"\bGTM-[A-Z0-9]{5,8}\b")],
    "meta_pixel": [
        re.compile(r"fbq\(\s*['\"]init['\"]\s*,\s*['\"](\d{10,20})['\"]"),
        re.compile(r"facebook\.com/tr/?\?(?:[^'\"\s]*&(?:amp;)?)?id=(\d{10,20})"),
    ],
    "yandex_metrica": [re.compile(r"\bym\(\s*(\d{6,10})\s*,"), re.compile(r"mc\.yandex\.[a-z]+/watch/(\d{6,10})")],
    "tiktok_pixel": [re.compile(r"ttq\.load\(\s*['\"]([A-Z0-9]{18,24})['\"]")],
}

SHINGLE_TOKENS = 3
MIN_DOM_TOKENS = 20
_SKIP_TEXT = {"script", "style", "noscript", "template"}


class _Collector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tokens: list[str] = []
        self.text: list[str] = []
        self.hrefs: list[str] = []
        self.script_srcs: list[str] = []
        self.form_actions: list[str] = []
        self.favicon: str | None = None
        self.title = ""
        self._stack: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {k: (v or "") for k, v in attrs}
        classes = ".".join(sorted(attr.get("class", "").split())[:4])
        self.tokens.append(f"{tag}.{classes}" if classes else tag)
        self._stack.append(tag)
        if tag == "a" and attr.get("href"):
            self.hrefs.append(attr["href"])
        elif tag == "script" and attr.get("src"):
            self.script_srcs.append(attr["src"])
        elif tag == "form" and attr.get("action"):
            self.form_actions.append(attr["action"])
        elif tag == "link" and "icon" in attr.get("rel", "").lower() and attr.get("href") and not self.favicon:
            self.favicon = attr["href"]

    def handle_endtag(self, tag: str) -> None:
        if tag in self._stack:
            while self._stack and self._stack.pop() != tag:
                pass

    def handle_data(self, data: str) -> None:
        current = self._stack[-1] if self._stack else ""
        if current == "title":
            self.title += data
        elif current not in _SKIP_TEXT and data.strip():
            self.text.append(data.strip())


@dataclass
class PageFeatures:
    title: str = ""
    observations: list[Observation] = field(default_factory=list)
    dom_hash: str = ""
    dom_signature: list[int] = field(default_factory=list)
    favicon_url: str | None = None
    visible_text: str = ""


def extract_page(html: str, base_url: str) -> PageFeatures:
    collector = _Collector()
    collector.feed(html)
    collector.close()

    own_domain = registered_domain(host_of(base_url))
    observations: list[Observation] = []

    for kind, patterns in TRACKERS.items():
        for pattern in patterns:
            for match in pattern.finditer(html):
                observations.append(Observation(kind, match.group(match.lastindex or 0)))

    # Kontaktów szukamy w tym, co widzi człowiek, i w odnośnikach. Zminifikowany JS daje fałszywe trafienia.
    visible = " ".join(collector.text)
    observations += contact_observations(visible + " " + " ".join(collector.hrefs))
    for href in collector.hrefs:
        if href.lower().startswith("tel:") and len(digits(href)) >= 9:
            observations.append(Observation("phone", digits(href)))

    for src in collector.script_srcs:
        host = host_of(urljoin(base_url, src))
        if host and registered_domain(host) != own_domain:
            observations.append(Observation("script_host", host))

    # Formularz wysyłający dane poza własną domenę zdradza zaplecze, które zbiera leady.
    for action in collector.form_actions:
        target = urlsplit(urljoin(base_url, action))
        host = (target.hostname or "").lower()
        if host and registered_domain(host) != own_domain:
            observations.append(Observation("form_action", f"{host}{target.path}".rstrip("/")))

    page = PageFeatures(
        title=collector.title.strip(),
        observations=list(dict.fromkeys(observations)),
        favicon_url=urljoin(base_url, collector.favicon) if collector.favicon else None,
        visible_text=visible,
    )
    if len(collector.tokens) >= MIN_DOM_TOKENS:
        page.dom_hash = hashlib.sha1("\n".join(collector.tokens).encode()).hexdigest()[:20]
        page.dom_signature = minhash.signature(minhash.shingles(collector.tokens, SHINGLE_TOKENS))
    return page
