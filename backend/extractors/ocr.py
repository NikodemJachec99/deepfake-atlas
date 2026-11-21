"""Tekst ze zrzutów reklam: nazwa reklamodawcy, treść i identyfikator z Biblioteki Reklam Mety.

Silnik OCR (RapidOCR, modele PP-OCRv5 dla alfabetu łacińskiego) ładuje się przy pierwszym użyciu.
Rozbiór linii na pola jest osobną, czystą funkcją, żeby dało się go testować bez modelu.
"""

import re
from dataclasses import dataclass, field
from functools import lru_cache

from . import Observation

_LIBRARY_ID = re.compile(r"(?:Identyfikator biblioteki|Library ID)\s*:?\s*(\d{10,20})", re.I)
_SPONSORED = re.compile(r"^(?:Sponsorowane|Sponsored)\b\s*(?:[-·•|:]\s*(.+))?$", re.I)
_NAME_CLEAN = re.compile(r"[^0-9a-ząćęłńóśźż]+", re.I)

# Napisy interfejsu Facebooka i Instagrama. Nie są treścią reklamy.
UI_LINES = {
    "sponsorowane", "sponsored", "dowiedz się więcej", "dowiedz sie więcej", "dowiedz się wiecej", "learn more", "zamknij", "aktywna",
    "nieaktywna", "instagram", "facebook", "meta", "link do reklamy", "platformy", "zobacz szczegóły reklamy", "transparentność w ue",
    "reklama ma kilka wersji.", "niska liczba wyświetleń", "ta reklama pochodzi z linku z adresem url", "www.facebook.com",
    "kup teraz", "zarejestruj się", "zamów teraz", "zainstaluj", "pobierz", "wyślij wiadomość", "obserwuj",
}
_UI_PREFIXES = ("wyświetlenia", "data zamieszczenia", "identyfikator biblioteki", "aktywności:", "library id")


@dataclass
class AdScreenshot:
    advertiser: str = ""
    library_ids: list[str] = field(default_factory=list)
    text: str = ""
    observations: list[Observation] = field(default_factory=list)


def normalize_name(name: str) -> str:
    """Nazwa do porównań: małe litery bez odstępów i znaków. `Jasny Poranek` i `jasnyporanek.example` dają `jasnyporanek`."""
    return _NAME_CLEAN.sub("", name.lower())


def parse_ad_screenshot(lines: list[str]) -> AdScreenshot:
    lines = [line.strip() for line in lines if line and line.strip()]
    result = AdScreenshot()
    joined = "\n".join(lines)
    result.library_ids = list(dict.fromkeys(_LIBRARY_ID.findall(joined)))

    sponsored_at = -1
    for index, line in enumerate(lines):
        match = _SPONSORED.match(line)
        if not match:
            continue
        sponsored_at = index
        if match.group(1):
            result.advertiser = match.group(1).strip()
        elif index > 0 and lines[index - 1].lower() not in UI_LINES and len(lines[index - 1]) >= 3:
            result.advertiser = lines[index - 1]
        break

    content = []
    for index, line in enumerate(lines):
        low = line.lower()
        if low in UI_LINES or low.startswith(_UI_PREFIXES) or _SPONSORED.match(line):
            continue
        if line == result.advertiser and index == sponsored_at - 1:
            continue
        if len(line) < 4 or not any(ch.isalpha() for ch in line):
            continue
        content.append(line)
    result.text = " ".join(content)

    observations = [Observation("meta_ad_ref", library_id, {"from": "zrzut z Biblioteki Reklam"}) for library_id in result.library_ids]
    name = normalize_name(result.advertiser)
    if len(name) >= 5:
        observations.append(Observation("page_name", name, {"from": "zrzut reklamy", "raw": result.advertiser}))
    result.observations = observations
    return result


@lru_cache(maxsize=1)
def _engine():
    from rapidocr import LangRec, ModelType, OCRVersion, RapidOCR

    return RapidOCR(
        params={"Rec.lang_type": LangRec.LATIN, "Rec.ocr_version": OCRVersion.PPOCRV5, "Rec.model_type": ModelType.MOBILE}
    )


def available() -> bool:
    try:
        import rapidocr  # noqa: F401
    except ImportError:
        return False
    return True


def read_bytes(data: bytes) -> list[str]:
    """Jak read_image, ale z obrazu w pamięci (np. klatki nagrania)."""
    if not available():
        return []
    try:
        result = _engine()(data)
    except Exception:  # noqa: BLE001
        return []
    return [text for text in (result.txts or []) if text]


def read_image(path: str) -> list[str]:
    """Linie tekstu z obrazu w kolejności czytania. Pusta lista, gdy silnika nie ma albo obraz jest nieczytelny."""
    if not available():
        return []
    try:
        result = _engine()(path)
    except Exception:  # noqa: BLE001
        return []
    return [text for text in (result.txts or []) if text]
