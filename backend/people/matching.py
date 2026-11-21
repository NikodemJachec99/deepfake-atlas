"""Rozpoznawanie osób po wzmiance w tekście, z tolerancją na polską odmianę.

"Jana Kowalskiego" i "Janowi Kowalskiemu" to wciąż Jan Kowalski. Porównujemy tematy wyrazów
i wymagamy, żeby imię i nazwisko stały obok siebie.
"""

import re
from functools import lru_cache


def stem(token: str) -> str:
    if len(token) <= 3:
        return token[:2]
    if len(token) <= 5:
        return token[:-1]
    return token[:-2]


@lru_cache(maxsize=4096)
def name_pattern(name: str) -> re.Pattern | None:
    tokens = [t for t in re.split(r"[\s-]+", name.strip()) if len(t) >= 2]
    if len(tokens) < 2:
        return None
    parts = [re.escape(stem(t)) + r"\w{0,5}" for t in tokens[:3]]
    return re.compile(r"\b" + r"[\s-]+".join(parts) + r"\b", re.IGNORECASE)


def find_people(text: str, people: list[tuple[int, str, list[str]]]) -> list[int]:
    """Zwraca identyfikatory osób wspomnianych w tekście. `people` to lista (id, imię i nazwisko, aliasy)."""
    found = []
    for person_id, name, aliases in people:
        for candidate in [name, *aliases]:
            pattern = name_pattern(candidate)
            if pattern and pattern.search(text):
                found.append(person_id)
                break
    return found
