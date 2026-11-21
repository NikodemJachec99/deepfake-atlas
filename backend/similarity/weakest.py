"""Test najsłabszego ogniwa: najmniejsze zestawy grup śladów, których utrata zmienia relację krawędzi.

To symulacja utraty obserwowalności jednej pary (co by było, gdyby tych śladów nie dało się
zobaczyć), a nie przewidywanie działań oszusta, identyfikacja człowieka ani wniosek o grupie w grafie.
Liczy tym samym silnikiem co laboratorium (`simulation.score`), niczego nie zapisuje i nie łączy się
z siecią.

Grupy śladów (jawne reguły metodyki, `docs/laboratorium.md`):
- `kit`: ścieżki zaplecza, zestaw parametrów i szablon ścieżki. Ustawia je jeden silnik lejka.
- `motif`: wzmianka o osobie, twarz, podszycie pod markę, tematyka. Wspólne motywy różnych operatorów.
- `infra`: pozostała infrastruktura (domena, adres, certyfikat, serwery nazw, rejestracja). Ta sama
  domena pociąga za sobą ten sam adres i certyfikat.
- `content`: tytuł i treść strony, tekst reklamy. Kopiowane razem.
- `creative`: zrzut reklamy, plik kreacji, obrazy strony.
- `template`: struktura DOM strony i białej strony.
- `kind:<typ>`: każdy pozostały typ osobno, np. identyfikator w panelu lejka albo piksel. Kilka wartości
  tego samego typu to jedna grupa.
- `unknown:<typ>`: typ spoza bieżącego rejestru. Pokazujemy go, ale nie zgadujemy jego przyczyny.

Przeszukiwanie: najpierw wszystkie pojedyncze grupy, potem wszystkie pary (bez par zawierających
grupę, która sama zmienia relację), do limitu liczby scenariuszy i czasu. Minimalność ogłaszamy tylko
dla ukończonego przeszukiwania i tylko w liczbie grup.
"""

import itertools
import time

from evidence.kinds import KINDS
from similarity import simulation
from similarity.models import Edge

INFRA_KINDS = {code for code, k in KINDS.items() if k.family == "infra" and not k.kit}
CONTENT_KINDS = {"page_title", "page_text_minhash", "text_minhash", "text_embedding"}
CREATIVE_KINDS = {"creative_sha256", "creative_phash", "image_set", "video_frames"}
TEMPLATE_KINDS = {"dom_hash", "dom_minhash", "white_dom_hash"}
GROUP_LABELS = {
    "kit": "Ślady silnika lejka",
    "motif": "Wspólne motywy (osoba, twarz, marka, tematyka)",
    "infra": "Infrastruktura domeny",
    "content": "Treść strony i reklamy",
    "creative": "Kreacja i obrazy",
    "template": "Szablon strony",
}
MAX_GROUP_SIZE = 2
DEFAULT_SCENARIOS = 500
DEFAULT_TIME_MS = 3000


def scenarios(n: int) -> str:
    if n == 1:
        return "1 scenariusz"
    if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        return f"{n} scenariusze"
    return f"{n} scenariuszy"


def group_of(kind_code: str) -> str:
    kind = KINDS.get(kind_code)
    if kind is None:
        return f"unknown:{kind_code}"
    if kind.kit:
        return "kit"
    if kind.motif:
        return "motif"
    if kind_code in INFRA_KINDS:
        return "infra"
    if kind_code in CONTENT_KINDS:
        return "content"
    if kind_code in CREATIVE_KINDS:
        return "creative"
    if kind_code in TEMPLATE_KINDS:
        return "template"
    return f"kind:{kind_code}"


def group_label(group: str) -> str:
    if group in GROUP_LABELS:
        return GROUP_LABELS[group]
    prefix, _, code = group.partition(":")
    if prefix == "unknown":
        return f"Nieznany typ: {code}"
    return KINDS[code].label


def weakest_link(edge: Edge, max_group_size: int = MAX_GROUP_SIZE, max_scenarios: int = DEFAULT_SCENARIOS,
                 time_limit_ms: int = DEFAULT_TIME_MS, edge_version: str | None = None, clock=time.monotonic) -> dict:
    current_version = simulation.check_version(edge, edge_version, "test")
    rows = list(edge.evidence.all())
    corpus_n = max((r.corpus_n for r in rows), default=0)
    base = simulation.score(rows, corpus_n)

    members: dict[str, list] = {}
    for row in rows:
        members.setdefault(group_of(row.kind), []).append(row)
    groups = [
        {"id": g, "label": group_label(g), "evidence_ids": sorted(r.pk for r in rs), "weight_bits": round(sum(r.weight_bits for r in rs), 2)}
        for g, rs in sorted(members.items())
    ]
    searched = {"max_group_size": max_group_size, "scenarios_checked": 0, "scenario_limit": max_scenarios,
                "time_limit_ms": time_limit_ms, "complete": True, "stopped_reason": ""}
    result = {
        "edge": edge.pk,
        "edge_version": current_version,
        "baseline": simulation.summary(base),
        "groups": groups,
        "searched": searched,
        "solutions": [],
        "minimal_size": None,
        "message": "",
    }
    if not rows:
        result["message"] = "Krawędź nie ma zapisanych dowodów, więc nie ma czego wyłączać."
        return result
    if base.relation is None:
        result["message"] = "Przy bieżącym modelu te materiały nie są połączone. Nie ma relacji, którą można by utracić."
        return result

    started = clock()
    ids = sorted(members)
    found: list[tuple[str, ...]] = []
    for size in range(1, max_group_size + 1):
        for combo in itertools.combinations(ids, size):
            if any(set(prev) <= set(combo) for prev in found):
                continue  # nadzbiór znalezionego zestawu nie jest minimalny
            if searched["scenarios_checked"] >= max_scenarios:
                searched.update(complete=False, stopped_reason=f"osiągnięto limit {max_scenarios} scenariuszy")
                break
            if (clock() - started) * 1000 >= time_limit_ms:
                searched.update(complete=False, stopped_reason=f"osiągnięto limit czasu {time_limit_ms} ms")
                break
            searched["scenarios_checked"] += 1
            removed = {r.pk for g in combo for r in members[g]}
            after = simulation.score([r for r in rows if r.pk not in removed], corpus_n)
            if after.relation != base.relation:
                found.append(combo)
                result["solutions"].append({
                    "groups": list(combo),
                    "labels": [group_label(g) for g in combo],
                    "excluded_evidence": sorted(removed),
                    "simulated": simulation.summary(after),
                    "change": f"{simulation.RELATION_LABELS[base.relation]} → {simulation.RELATION_LABELS[after.relation]}",
                })
        if not searched["complete"]:
            break
        if found:
            break  # mamy najmniejszy rozmiar; większe zestawy nie są minimalne

    scope = f"pojedyncze grupy{' i pary' if max_group_size >= 2 else ''}, {scenarios(searched['scenarios_checked'])}"
    if result["solutions"]:
        size = len(result["solutions"][0]["groups"])
        if searched["complete"]:
            result["minimal_size"] = size
            result["message"] = (
                f"Najmniejszy zestaw zmieniający relację ma {size} {'grupę' if size == 1 else 'grupy'} śladów "
                f"(w sprawdzonym zakresie: {scope}). Rozwiązań tego rozmiaru: {len(result['solutions'])}."
            )
        else:
            result["message"] = f"Znaleziono zestawy zmieniające relację, ale przeszukiwanie jest niepełne ({searched['stopped_reason']}), więc nie twierdzimy, że są najmniejsze."
    elif searched["complete"]:
        result["message"] = f"Nie znaleziono w sprawdzonych scenariuszach ({scope})."
    else:
        result["message"] = f"Nie znaleziono w sprawdzonych scenariuszach, a przeszukiwanie jest niepełne ({searched['stopped_reason']})."
    return result
