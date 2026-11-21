"""MinHash i pasma LSH.

Sygnatura służy do policzenia podobieństwa dwóch zbiorów (szablon strony, tekst reklamy).
Pasma zamieniają sygnaturę na markery twarde, żeby kandydatów szukać zwykłym indeksem
odwróconym zamiast porównywać każdą reklamę z każdą.
"""

import hashlib
from collections.abc import Iterable, Sequence

NUM_PERM = 64
BANDS = 16
ROWS = NUM_PERM // BANDS
_PRIME = (1 << 61) - 1


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
    return [min((a * h + b) % _PRIME for h in hashed) for a, b in _COEFFS]


def similarity(sig_a: Sequence[int], sig_b: Sequence[int]) -> float:
    """Estymata podobieństwa Jaccarda. Pusta sygnatura nie jest podobna do niczego."""
    if len(sig_a) != NUM_PERM or len(sig_b) != NUM_PERM:
        return 0.0
    return sum(1 for x, y in zip(sig_a, sig_b, strict=True) if x == y) / NUM_PERM


def bands(sig: Sequence[int]) -> list[str]:
    if len(sig) != NUM_PERM:
        return []
    out = []
    for i in range(BANDS):
        chunk = ",".join(str(v) for v in sig[i * ROWS : (i + 1) * ROWS])
        out.append(f"{i}:{hashlib.blake2b(chunk.encode(), digest_size=6).hexdigest()}")
    return out
