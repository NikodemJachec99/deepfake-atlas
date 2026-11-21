"""Warstwa wizualna: hash percepcyjny obrazów.

Hash różnicowy (dHash, 64 bity) jest odporny na zmianę rozmiaru, kompresję i drobne przeróbki.
Dwa obrazy uznajemy za ten sam, gdy ich hasze różnią się najwyżej o kilka bitów.

Dwa zastosowania:
- zrzut reklamy: jeden hash, porównywany wprost (ta sama kreacja wrzucona drugi raz),
- strona: zbiór haszy jej obrazów, porównywany jako zbiór (te same zdjęcia na różnych domenach).
"""

import io
from collections.abc import Iterable

MIN_SIDE = 160  # ikony i piksele śledzące niczego nie mówią o kampanii
MIN_BYTES = 1024
MAX_IMAGES = 80
MAX_DISTANCE = 6
BAND_BITS = 16
MIN_SET = 3  # przy mniejszych zbiorach jedno wspólne zdjęcie nie może dać pełnego podobieństwa


def dhash(data: bytes) -> int | None:
    """Hash percepcyjny obrazu albo None, gdy bajty nie są obrazem lub obraz jest za mały."""
    if len(data) < MIN_BYTES:
        return None
    try:
        from PIL import Image

        with Image.open(io.BytesIO(data)) as image:
            if min(image.size) < MIN_SIDE:
                return None
            small = image.convert("L").resize((9, 8), Image.Resampling.LANCZOS)
            pixels = small.tobytes()
    except Exception:  # noqa: BLE001
        return None
    value = 0
    for row in range(8):
        for col in range(8):
            value = (value << 1) | (1 if pixels[row * 9 + col] > pixels[row * 9 + col + 1] else 0)
    return value


def to_hex(value: int) -> str:
    return f"{value:016x}"


def distance(a: int, b: int) -> int:
    return (a ^ b).bit_count()


def hash_set(blobs: Iterable[bytes]) -> list[int]:
    """Unikalne hasze obrazów strony, z pominięciem jednolitych plansz."""
    out: list[int] = []
    for data in blobs:
        value = dhash(data)
        if value is None or value in (0, (1 << 64) - 1) or value in out:
            continue
        out.append(value)
        if len(out) >= MAX_IMAGES:
            break
    return out


def bands(values: Iterable[int]) -> list[str]:
    """Klucze do wyszukiwania kandydatów: hash pocięty na 4 części. Obrazy różniące się o kilka bitów dzielą co najmniej jedną."""
    out = []
    for value in values:
        for index in range(64 // BAND_BITS):
            part = (value >> (index * BAND_BITS)) & ((1 << BAND_BITS) - 1)
            out.append(f"{index}:{part:04x}")
    return list(dict.fromkeys(out))


def set_similarity(a: list[int], b: list[int]) -> float:
    """Jaka część obrazów jest wspólna dla obu stron (0..1)."""
    if not a or not b:
        return 0.0
    remaining = list(b)
    matched = 0
    for value in a:
        hit = next((other for other in remaining if distance(value, other) <= MAX_DISTANCE), None)
        if hit is not None:
            matched += 1
            remaining.remove(hit)
    union = len(a) + len(b) - matched
    return matched / max(union, MIN_SET)
