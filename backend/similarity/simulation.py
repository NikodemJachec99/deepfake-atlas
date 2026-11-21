"""Laboratorium dowodów: co zostanie z krawędzi, gdy analityk wyłączy wybrane dowody.

Symulacja liczy parę od nowa tym samym silnikiem (`fusion.score_pair`) z dowodów zapisanych przy
krawędzi, raz ze wszystkimi i raz bez wyłączonych. Niczego nie zapisuje: ani krawędzi, ani decyzji,
ani grup. Nie wykonuje żadnych zapytań poza bazę.

Wpływ na grupy opisuje tylko to, co da się policzyć dokładnie: czy obie reklamy pozostają połączone
inną ścieżką z krawędzi tego samego rodzaju. Jeśli tak, ta krawędź nie jest dla grupy niezbędna.
Jeśli nie, grupa rozpadłaby się na dwie w miejscu tej krawędzi (przy założeniu, że reszta grafu
zostaje bez zmian).
"""

from collections import deque
from dataclasses import dataclass
from datetime import datetime

from evidence.kinds import FAMILIES, KINDS
from people.display import display_value
from similarity import fusion
from similarity.models import Edge, EdgeEvidence

GROUP_RELATIONS = {
    "campaign": [Edge.Relation.SAME_CAMPAIGN],
    "operator": [Edge.Relation.SAME_CAMPAIGN, Edge.Relation.SAME_OPERATOR],
}
RELATION_LABELS = {
    "same_campaign": "ta sama kampania",
    "same_operator": "ten sam operator",
    "similar": "podobna koncepcja",
    None: "brak krawędzi",
}


class SimulationError(Exception):
    def __init__(self, message: str, status: int = 400, **extra):
        super().__init__(message)
        self.status = status
        self.extra = extra


@dataclass
class Inputs:
    shared: list[fusion.Shared]
    soft: list[fusion.Soft]
    corpus_n: int
    skipped: list[str]


def inputs_from(rows: list[EdgeEvidence]) -> Inputs:
    shared, soft, skipped = [], [], []
    for row in rows:
        kind = KINDS.get(row.kind)
        if kind is None:
            skipped.append(row.kind)
        elif kind.soft:
            soft.append(fusion.Soft(row.kind, row.similarity, row.value_a, row.value_b))
        else:
            shared.append(fusion.Shared(row.kind, row.value_a, row.df))
    corpus_n = max((row.corpus_n for row in rows), default=0)
    return Inputs(shared, soft, corpus_n, skipped)


def score(rows: list[EdgeEvidence], corpus_n: int) -> fusion.PairResult:
    data = inputs_from(rows)
    return fusion.score_pair(data.shared, data.soft, corpus_n)


def reasons(result: fusion.PairResult) -> list[str]:
    """Po ludzku: dlaczego wyszła taka relacja. Każde zdanie odpowiada jednej regule z `fusion.score_pair`."""
    if not result.evidence:
        return ["Nie zostały żadne dowody, więc nie ma krawędzi."]
    c = result.checks
    out = []
    if c["probability_ok"]:
        out.append(f"Pewność {result.probability:.3f} spełnia próg {fusion.SAME_PROBABILITY}.")
    else:
        out.append(f"Pewność {result.probability:.3f} jest poniżej progu {fusion.SAME_PROBABILITY} dla wspólnego źródła.")
    if c["decisive"]:
        out.append("Jest rzadki marker rozstrzygający.")
    else:
        out.append("Brak rzadkiego markera rozstrzygającego.")
    groups = ", ".join(FAMILIES.get(g, "ślad silnika lejka" if g == "kit" else g) for g in c["independent"]) or "żadnego"
    out.append(f"Niezależne silne potwierdzenia: {len(c['independent'])} ({groups}).")
    if not c["decisive"] and len(c["independent"]) >= 2 and not c["backed"]:
        out.append("Żadne z potwierdzeń nie dotyczy zaplecza. Treść i obrazy da się skopiować.")
    if c["same_source"]:
        if result.relation == "same_campaign":
            out.append(f"Zgodna opowieść ({c['story_bits']} bitów): ta sama kampania.")
        else:
            out.append(f"Za mało zgodnej opowieści ({c['story_bits']} bitów z wymaganych {fusion.SIMILAR_MIN_BITS}): ten sam operator, inna kampania.")
    elif result.relation == "similar":
        if c["story_bits"] >= fusion.SIMILAR_MIN_BITS or c["concept_bits"] >= fusion.WEAK_SIMILAR_MIN_BITS:
            out.append("Zgodna treść, obrazy albo kilka motywów naraz, ale bez dowodu wspólnego źródła: podobna koncepcja.")
        else:
            out.append("Te same ścieżki zaplecza bez śladu operatora: ten sam silnik lejka, podobna koncepcja.")
    else:
        out.append("Dowody nie wystarczają nawet do relacji podobieństwa.")
    return out


def summary(result: fusion.PairResult) -> dict:
    return {
        "relation": result.relation,
        "relation_label": RELATION_LABELS[result.relation],
        "probability": round(result.probability, 6),
        "bits": round(result.bits, 2),
        "decisive": result.decisive,
        "duplicate": result.duplicate,
        "families": {k: round(v, 2) for k, v in result.families.items()},
        "independent": result.checks.get("independent", []),
        "reasons": reasons(result),
    }


def path_length(edge: Edge, relations: list[str]) -> int | None:
    """Najkrótsza ścieżka od ad_a do ad_b po krawędziach tego rodzaju, bez tej krawędzi i bez odrzuconych."""
    pairs = (
        Edge.objects.filter(relation__in=relations)
        .exclude(pk=edge.pk)
        .exclude(verdict=Edge.Verdict.REJECTED)
        .values_list("ad_a_id", "ad_b_id")
    )
    neighbours: dict[int, list[int]] = {}
    for a, b in pairs:
        neighbours.setdefault(a, []).append(b)
        neighbours.setdefault(b, []).append(a)
    seen = {edge.ad_a_id: 0}
    queue = deque([edge.ad_a_id])
    while queue:
        node = queue.popleft()
        if node == edge.ad_b_id:
            return seen[node]
        for other in neighbours.get(node, []):
            if other not in seen:
                seen[other] = seen[node] + 1
                queue.append(other)
    return None


def group_impact(edge: Edge, before: str | None, after: str | None) -> dict:
    out = {}
    rejected = edge.verdict == Edge.Verdict.REJECTED
    for group, relations in GROUP_RELATIONS.items():
        binds_before = before in relations and not rejected
        binds_after = after in relations and not rejected
        entry = {"binds_before": binds_before, "binds_after": binds_after, "pair_still_connected": None, "path_length": None}
        if binds_before and not binds_after:
            length = path_length(edge, relations)
            entry["pair_still_connected"] = length is not None
            entry["path_length"] = length
            entry["note"] = (
                f"Obie reklamy zostają w jednej grupie przez inne krawędzie (ścieżka długości {length})."
                if length is not None
                else "Bez tej krawędzi obie reklamy nie łączą się żadną inną ścieżką: grupa rozpadłaby się w tym miejscu na dwie."
            )
        elif binds_before:
            entry["note"] = "Krawędź nadal spina grupę."
        elif binds_after:
            entry["note"] = "Krawędź zaczęłaby spinać grupę."
        else:
            entry["note"] = "Krawędź nie spina tej grupy ani przed, ani po."
        out[group] = entry
    return out


def check_version(edge: Edge, edge_version: str | None, what: str) -> str:
    """Wersja krawędzi to chwila `updated_at`. Porównujemy chwile, nie napisy: ta sama chwila z innym
    przesunięciem strefy (`Z`, `+00:00`, `+01:00`) to ta sama wersja, mikrosekundy się liczą."""
    current = edge.updated_at.isoformat()
    if not edge_version:
        return current
    try:
        given = datetime.fromisoformat(edge_version.strip().replace("Z", "+00:00"))
    except ValueError:
        raise SimulationError("Wersja krawędzi nie jest datą ISO 8601.", edge_version=current) from None
    if given.tzinfo is None:
        raise SimulationError("Wersja krawędzi musi mieć strefę czasową.", edge_version=current)
    if given != edge.updated_at:
        raise SimulationError(
            f"Krawędź zmieniła się od chwili, w której ją wczytano. Odśwież dowody i powtórz {what}.", status=409, edge_version=current
        )
    return current


def simulate(edge: Edge, exclude: list[int], edge_version: str | None = None) -> dict:
    rows = list(edge.evidence.all())
    by_id = {row.pk: row for row in rows}
    unknown = sorted({i for i in exclude if i not in by_id})
    if unknown:
        raise SimulationError("Te dowody nie należą do tej krawędzi.", unknown=unknown)
    current_version = check_version(edge, edge_version, "symulację")
    excluded_ids = set(exclude)
    corpus_n = max((row.corpus_n for row in rows), default=0)
    base = score(rows, corpus_n)
    after = score([r for r in rows if r.pk not in excluded_ids], corpus_n)

    warnings = []
    skipped = inputs_from(rows).skipped
    if skipped:
        warnings.append(f"Typy markerów spoza bieżącego rejestru pominięte: {', '.join(sorted(set(skipped)))}.")
    if base.relation != edge.relation or abs(base.bits - edge.bits) > 0.05:
        warnings.append(
            f"Zapisana krawędź ({edge.relation}, {edge.bits:.1f} bitów, model {edge.model_version}) różni się od przeliczenia "
            f"bieżącym modelem {fusion.MODEL_VERSION} ({base.relation}, {base.bits:.1f} bitów). Porównujemy z przeliczeniem."
        )
    if edge.verdict == Edge.Verdict.REJECTED:
        warnings.append("Analityk odrzucił tę krawędź, więc już teraz niczego nie spina.")
    warnings.append("Wynik dotyczy tylko tej pary. Pozostałe krawędzie liczymy bez zmian.")

    return {
        "edge": edge.pk,
        "edge_version": current_version,
        "model_version": fusion.MODEL_VERSION,
        "stored": {"relation": edge.relation, "bits": round(edge.bits, 2), "model_version": edge.model_version},
        "baseline": summary(base),
        "simulated": summary(after),
        "relation_changed": base.relation != after.relation,
        "excluded": [
            {
                "id": row.pk,
                "family": row.family,
                "kind": row.kind,
                "label": KINDS[row.kind].label if row.kind in KINDS else row.kind,
                "value": row.value_a,
                "display_value": display_value(row.kind, row.value_a),
                "weight_bits": round(row.weight_bits, 2),
                "decisive": row.decisive,
            }
            for row in rows
            if row.pk in excluded_ids
        ],
        "group_impact": group_impact(edge, base.relation, after.relation),
        "warnings": warnings,
    }
