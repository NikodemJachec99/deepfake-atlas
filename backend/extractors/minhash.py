"""MinHash i pasma LSH.

Sygnatura służy do policzenia podobieństwa dwóch zbiorów (szablon strony, tekst reklamy).
Pasma zamieniają sygnaturę na markery twarde, żeby kandydatów szukać zwykłym indeksem
odwróconym zamiast porównywać każdą reklamę z każdą.

Sygnatura ma NUM_PERM wartości i na końcu liczność zbioru. Z liczności i Jaccarda da się oszacować,
jaką część mniejszego zbioru zawiera większy. Starsze sygnatury bez liczności dalej się porównują.
"""

import hashlib
from collections.abc import Iterable, Sequence

NUM_PERM = 64
BANDS = 16
ROWS = NUM_PERM // BANDS
_PRIME = (1 << 61) - 1
# Zawieranie liczymy tylko dla tekstów, które mają z czego się składać, i gdy doklejona część
# nie przerasta kilkukrotnie wspólnej. Inaczej baner albo stopka zawarte w każdej stronie
# robiłyby z różnych stron ten sam tekst. Przy prawie równych rozmiarach zawieranie to tylko
# podbity Jaccard (współczynnik Dice), a pełne zawieranie i tak daje wysoki Jaccard, więc je pomijamy.
CONTAINMENT_MIN_ITEMS = 300
CONTAINMENT_MIN_RATIO = 0.3
CONTAINMENT_MAX_RATIO = 0.9
# Krótszy tekst musi prawie cały siedzieć w dłuższym. Częściowa zgodność to sprawa Jaccarda.
CONTAINMENT_MIN = 0.85


def _hash64(data: str) -> int:
    return int.from_bytes(hashlib.blake2b(data.encode("utf-8"), digest_size=8).digest(), "big")


# Stałe współczynniki permutacji. Sygnatury z różnych uruchomień muszą być porównywalne.
_COEFFS = [
    (_hash64(f"scamdna-a-{i}") % (_PRIME - 1) + 1, _hash64(f"scamdna-b-{i}") % _PRIME) for i in range(NUM_PERM)
]


def shingles(tokens: Sequence[str], k: int) -> set[str]:
    if len(tokens) < k:
        return set()
    return {"\x1f".join(tokens[i : i + k]) for i in range(len(tokens) - k + 1)}


def signature(items: Iterable[str]) -> list[int]:
    hashed = [_hash64(item) % _PRIME for item in set(items)]
    if not hashed:
        return []
    return [min((a * h + b) % _PRIME for h in hashed) for a, b in _COEFFS] + [len(hashed)]


def _parts(sig: Sequence[int]) -> tuple[Sequence[int], int | None] | None:
    if len(sig) == NUM_PERM:
        return sig, None
    if len(sig) == NUM_PERM + 1:
        return sig[:NUM_PERM], sig[NUM_PERM]
    return None


def similarity(sig_a: Sequence[int], sig_b: Sequence[int]) -> float:
    """Estymata podobieństwa Jaccarda. Pusta sygnatura nie jest podobna do niczego."""
    a, b = _parts(sig_a), _parts(sig_b)
    if a is None or b is None:
        return 0.0
    return sum(1 for x, y in zip(a[0], b[0], strict=True) if x == y) / NUM_PERM


def text_similarity(sig_a: Sequence[int], sig_b: Sequence[int]) -> float:
    """Podobieństwo treści odporne na doklejoną sekcję: zawieranie, gdy krótszy tekst siedzi w dłuższym, inaczej Jaccard.

    Zawieranie to część mniejszego zbioru obecna w większym: |A∩B| = J(|A|+|B|)/(1+J).
    Zapis strony z komentarzami albo dodatkowym blokiem ma ten sam artykuł, a Jaccard spada
    o tyle, ile doklejono.
    """
    jaccard = similarity(sig_a, sig_b)
    a, b = _parts(sig_a), _parts(sig_b)
    if not jaccard or a is None or b is None or a[1] is None or b[1] is None:
        return jaccard
    small, large = sorted((a[1], b[1]))
    if small < CONTAINMENT_MIN_ITEMS or not CONTAINMENT_MIN_RATIO <= small / large <= CONTAINMENT_MAX_RATIO:
        return jaccard
    contained = min(1.0, jaccard * (small + large) / (1 + jaccard) / small)
    return contained if contained >= CONTAINMENT_MIN else jaccard


def bands(sig: Sequence[int]) -> list[str]:
    parts = _parts(sig)
    if parts is None:
        return []
    sig = parts[0]
    out = []
    for i in range(BANDS):
        chunk = ",".join(str(v) for v in sig[i * ROWS : (i + 1) * ROWS])
        out.append(f"{i}:{hashlib.blake2b(chunk.encode(), digest_size=6).hexdigest()}")
    return out
