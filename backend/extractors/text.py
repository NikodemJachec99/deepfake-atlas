"""Markery z tekstu: dane kontaktowe i sygnatura do wykrywania prawie identycznych treści."""

import re
import unicodedata
from dataclasses import dataclass, field

from . import Observation, minhash

_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+\b")
_PHONE = re.compile(r"(?<![\w+])\+\d{1,3}(?:[\s.-]?\d{2,4}){2,5}(?!\d)")
_TELEGRAM = re.compile(r"(?:t\.me|telegram\.me)/(?:joinchat/)?\+?([A-Za-z0-9_]{4,64})", re.I)
_WHATSAPP = re.compile(r"(?:wa\.me/|api\.whatsapp\.com/send\?phone=)\+?(\d{8,15})", re.I)
_BTC = re.compile(r"\b(bc1[ac-hj-np-z02-9]{25,59}|[13][a-km-zA-HJ-NP-Z1-9]{25,34})\b")
_ETH = re.compile(r"\b0x[a-fA-F0-9]{40}\b")
_IBAN_PL = re.compile(r"\bPL\s?\d{2}(?:\s?\d{4}){6}\b")

_URL = re.compile(r"https?://\S+|\bwww\.\S+", re.I)
_NON_WORD = re.compile(r"[^\w\s]", re.U)
_SPACE = re.compile(r"\s+")

SHINGLE_CHARS = 5
MIN_TEXT_CHARS = 40


def digits(value: str) -> str:
    return re.sub(r"\D", "", value)


def contact_observations(text: str) -> list[Observation]:
    """Kontakty i adresy płatności. Wspólny numer albo portfel to jeden z najmocniejszych śladów."""
    out: list[Observation] = []
    out += [Observation("email", m.group(0).lower()) for m in _EMAIL.finditer(text)]
    out += [Observation("phone", digits(m.group(0))) for m in _PHONE.finditer(text)]
    out += [Observation("telegram", m.group(1).lower()) for m in _TELEGRAM.finditer(text)]
    out += [Observation("whatsapp", m.group(1)) for m in _WHATSAPP.finditer(text)]
    out += [Observation("crypto_btc", m.group(1)) for m in _BTC.finditer(text)]
    out += [Observation("crypto_eth", m.group(0).lower()) for m in _ETH.finditer(text)]
    out += [Observation("iban", digits(m.group(0))) for m in _IBAN_PL.finditer(text)]
    return list(dict.fromkeys(out))


def normalize(text: str) -> str:
    """Sprowadza tekst do postaci, w której drobne przeróbki znikają: kwoty, interpunkcja, wielkość liter."""
    text = unicodedata.normalize("NFKC", text).lower()
    text = _URL.sub(" ", text)
    text = re.sub(r"\d", "0", text)
    text = _NON_WORD.sub(" ", text)
    return _SPACE.sub(" ", text).strip()


@dataclass
class TextFeatures:
    observations: list[Observation] = field(default_factory=list)
    signature: list[int] = field(default_factory=list)
    normalized: str = ""


def extract_text(text: str) -> TextFeatures:
    features = TextFeatures(observations=contact_observations(text), normalized=normalize(text))
    norm = features.normalized
    if len(norm) >= MIN_TEXT_CHARS:
        grams = {norm[i : i + SHINGLE_CHARS] for i in range(len(norm) - SHINGLE_CHARS + 1)}
        features.signature = minhash.signature(grams)
    return features
