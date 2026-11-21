"""Ekstrakcja markerów. Czyste funkcje: tekst lub HTML na wejściu, obserwacje na wyjściu.

Nic tutaj nie dotyka sieci ani bazy, więc każdą regułę da się przetestować na stałym wejściu.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Observation:
    """Jeden marker twardy znaleziony w materiale: typ z `evidence.kinds` i znormalizowana wartość."""

    kind: str
    value: str
    detail: dict = field(default_factory=dict, compare=False, hash=False)
