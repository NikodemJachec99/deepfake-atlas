"""Evidence Fusion, etap 1: model Fellegi-Sunter z ważeniem rzadkością.

Wejście: markery wspólne dla dwóch reklam i podobieństwa markerów miękkich.
Wyjście: relacja, pewność i lista dowodów z wkładem każdego w bitach.

Moduł nie zna bazy ani Django. Całą logikę łączenia da się uruchomić na liczbach z ręki.
"""

import math
from dataclasses import dataclass, field

from evidence.kinds import CONCEPT_FAMILIES, KINDS

MODEL_VERSION = "fs-5"  # fs-5: podobieństwo treści odporne na doklejoną sekcję

PRIOR = 1e-4  # szansa, że dwie losowe reklamy z korpusu należą do jednej kampanii
PRIOR_STRENGTH = 1000  # ile "wirtualnych reklam" waży częstość bazowa typu markera
SAME_PROBABILITY = 0.9  # próg pewności dla relacji "ta sama kampania"
DECISIVE_BITS = 10.0  # marker rozstrzygający musi być do tego rzadki
FAMILY_MIN_BITS = 4.0  # od tylu bitów rodzina liczy się jako niezależne potwierdzenie
SIMILAR_MIN_BITS = 4.0  # zgodność treści wystarczająca do "tej samej opowieści"
WEAK_SIMILAR_MIN_BITS = 5.5  # albo kilka zgodnych motywów naraz: osoba, marka i tematyka
FAMILY_DISCOUNT = 0.5  # kolejne markery w tej samej rodzinie są skorelowane
DUPLICATE_TEXT = 0.97  # od takiej zgodności treści i struktury mówimy o duplikacie
DUPLICATE_DOM = 0.97


@dataclass(frozen=True)
class Shared:
    """Marker twardy o tej samej wartości w obu reklamach.

    `df` to liczba niezależnych źródeł z tą wartością, w tym obie porównywane reklamy liczone jako dwa.
    Źródłem jest kampania albo reklama, która do żadnej nie należy.
    """

    kind: str
    value: str
    df: int


@dataclass(frozen=True)
class Soft:
    """Podobieństwo markera miękkiego w zakresie 0..1."""

    kind: str
    similarity: float
    value_a: str = ""
    value_b: str = ""


@dataclass
class EvidenceItem:
    family: str
    kind: str
    value_a: str
    value_b: str
    similarity: float
    df: int
    corpus_n: int
    raw_bits: float
    weight_bits: float = 0.0
    decisive: bool = False


@dataclass
class PairResult:
    bits: float = 0.0
    probability: float = 0.0
    relation: str | None = None
    decisive: bool = False
    duplicate: bool = False
    families: dict[str, float] = field(default_factory=dict)
    evidence: list[EvidenceItem] = field(default_factory=list)


def frequency(df: int, corpus_n: int, f0: float) -> float:
    """Częstość wartości wśród pozostałych reklam, wygładzona częstością bazową typu.

    Dwie porównywane reklamy odejmujemy: to, że obie mają tę wartość, jest właśnie pytaniem,
    a nie dowodem na jej pospolitość.
    """
    others = max(df - 2, 0)
    population = max(corpus_n - 2, 0)
    return (others + PRIOR_STRENGTH * f0) / (population + PRIOR_STRENGTH)


def exact_bits(kind_code: str, df: int, corpus_n: int) -> float:
    k = KINDS[kind_code]
    if k.cap <= 0:
        return 0.0
    f = frequency(df, corpus_n, k.f0)
    return max(0.0, min(k.cap, math.log2(k.m / f)))


def soft_bits(kind_code: str, similarity: float) -> float:
    k = KINDS[kind_code]
    if similarity < k.lo:
        return 0.0
    return k.cap * min(1.0, (similarity - k.lo) / (k.hi - k.lo))


def score_pair(shared: list[Shared], soft: list[Soft], corpus_n: int) -> PairResult:
    items: list[EvidenceItem] = []
    for s in shared:
        k = KINDS[s.kind]
        raw = exact_bits(s.kind, s.df, corpus_n)
        if raw <= 0:
            continue
        items.append(
            EvidenceItem(k.family, s.kind, s.value, s.value, 1.0, s.df, corpus_n, raw, decisive=k.decisive and raw >= DECISIVE_BITS)
        )
    for s in soft:
        k = KINDS[s.kind]
        raw = soft_bits(s.kind, s.similarity)
        if raw <= 0:
            continue
        items.append(EvidenceItem(k.family, s.kind, s.value_a, s.value_b, s.similarity, 0, corpus_n, raw))

    # Markery jednej rodziny zwykle idą w parze (ta sama domena to ten sam IP i certyfikat),
    # więc pełną wagę dostaje tylko najsilniejszy, a każdy kolejny połowę poprzedniego mnożnika.
    families: dict[str, float] = {}
    by_family: dict[str, list[EvidenceItem]] = {}
    for item in items:
        by_family.setdefault(item.family, []).append(item)
    for family, group in by_family.items():
        group.sort(key=lambda e: e.raw_bits, reverse=True)
        factor = 1.0
        for item in group:
            item.weight_bits = item.raw_bits * factor
            factor *= FAMILY_DISCOUNT
        families[family] = sum(e.weight_bits for e in group)

    result = PairResult(families=families, evidence=sorted(items, key=lambda e: e.weight_bits, reverse=True))
    if not items:
        return result

    result.bits = sum(families.values())
    prior_bits = math.log2(PRIOR / (1 - PRIOR))
    result.probability = 1 / (1 + 2 ** -(result.bits + prior_bits))
    result.decisive = any(e.decisive for e in items)

    # Duplikat: ta sama strona przechwycona drugi raz. Ta sama treść i ta sama struktura.
    best = {e.kind: max(e.similarity, 0.0) for e in items if KINDS[e.kind].soft}
    same_text = best.get("page_text_minhash", 0.0) >= DUPLICATE_TEXT or best.get("text_minhash", 0.0) >= DUPLICATE_TEXT
    same_shape = any(e.kind == "dom_hash" for e in items) or best.get("dom_minhash", 0.0) >= DUPLICATE_DOM
    result.duplicate = same_text and same_shape

    # Niezależność liczymy osobno od wag. Ślady silnika lejka z różnych rodzin (ścieżki zaplecza,
    # zestaw parametrów, szablon ścieżki) to jedno potwierdzenie: ten sam program, który mógł kupić
    # każdy. Operatora wskazuje dopiero ślad jego konta albo infrastruktury.
    independent: dict[str, float] = {}
    for item in items:
        if KINDS[item.kind].motif:
            continue
        group = "kit" if KINDS[item.kind].kit else item.family
        independent[group] = independent.get(group, 0.0) + item.weight_bits
    strong_families = [f for f, bits in independent.items() if bits >= FAMILY_MIN_BITS]
    # Ta sama opowieść: zgodna treść, obraz albo kontakt. Sam wspólny motyw (tematyka, osoba, marka)
    # to za mało, bo różni operatorzy grają na tych samych nazwiskach i tych samych redakcjach.
    story_bits = sum(e.weight_bits for e in items if KINDS[e.kind].story)
    concept_bits = sum(bits for f, bits in families.items() if f in CONCEPT_FAMILIES)

    # Reguła bezpieczeństwa: sama wysoka suma nie wystarcza. Potrzebny jest jeden rzadki marker
    # rozstrzygający albo dwie niezależne rodziny, inaczej jeden wspólny szablon skleja wszystko.
    # Co najmniej jedna z tych rodzin musi dotyczyć zaplecza. Treść i obrazy da się skopiować,
    # więc dwie rodziny koncepcyjne nie dowodzą wspólnego źródła.
    backed = any(f not in CONCEPT_FAMILIES for f in strong_families)
    same_source = result.probability >= SAME_PROBABILITY and (result.decisive or (len(strong_families) >= 2 and backed))
    if same_source:
        # To samo źródło i ta sama opowieść to jedna kampania. To samo źródło z inną opowieścią
        # to ten sam operator, który prowadzi kilka kampanii na wspólnym zapleczu.
        result.relation = "same_campaign" if story_bits >= SIMILAR_MIN_BITS else "same_operator"
    elif story_bits >= SIMILAR_MIN_BITS or concept_bits >= WEAK_SIMILAR_MIN_BITS:
        result.relation = "similar"
    elif sum(e.weight_bits for e in items if e.kind == "kit_path") >= FAMILY_MIN_BITS:
        # Te same ścieżki zaplecza bez śladu konkretnego operatora: ten sam silnik lejka.
        # Warto to pokazać, ale nie scalać. Sam szablon ścieżki albo zestaw parametrów to za mało.
        result.relation = "similar"
    return result


def connected_components(pairs: list[tuple[int, int]]) -> list[set[int]]:
    parent: dict[int, int] = {}

    def find(x: int) -> int:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b in pairs:
        root_a, root_b = find(a), find(b)
        if root_a != root_b:
            parent[max(root_a, root_b)] = min(root_a, root_b)

    groups: dict[int, set[int]] = {}
    for node in parent:
        groups.setdefault(find(node), set()).add(node)
    return list(groups.values())
