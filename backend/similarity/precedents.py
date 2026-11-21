"""Pamięć sprzeciwu: podobne wcześniejsze rozstrzygnięcia dla bieżącej krawędzi.

Reguły są deterministyczne i jawne:

1. Kandydat to najnowsza decyzja o każdej innej parze reklam, która ma migawkę. Decyzje bez migawki
   (sprzed pamięci sprzeciwu) tylko liczymy: wiemy, co zdecydowano, ale nie na jakiej podstawie,
   więc nie pokazujemy ich jako precedensów.
2. Ślady obu stron sprowadzamy do grup z testu najsłabszego ogniwa (`weakest.group_of`): ślady jednej
   przyczyny (np. silnik lejka) to jedna grupa.
3. Kandydat musi dzielić z bieżącą krawędzią co najmniej jedną grupę inną niż wspólne motywy. Sama
   osoba albo marka to za mało, różni operatorzy grają na tych samych nazwiskach.
4. Podobieństwo to Jaccard zbiorów grup. Kolejność: podobieństwo, ta sama relacja, nowsza decyzja, id.

Wynik jest doradczy. Wcześniejsza decyzja nie przesądza o tej krawędzi, a moduł niczego nie zmienia:
ani krawędzi, ani wag, ani grup, ani decyzji.
"""

from evidence.kinds import KINDS
from similarity.models import Edge, EdgeDecision
from similarity.weakest import group_label, group_of

DEFAULT_LIMIT = 5
MAX_LIMIT = 20
NOTICE = "Wcześniejsze decyzje są punktem odniesienia, a nie rozstrzygnięciem tej krawędzi. Oceń ją na jej własnych dowodach."
RELATION_LABELS = {"same_campaign": "ta sama kampania", "same_operator": "ten sam operator", "similar": "podobna koncepcja"}


def _groups(kinds) -> set[str]:
    return {group_of(kind) for kind in kinds}


def _independent(group: str) -> bool:
    """Grupa, która może być niezależnym potwierdzeniem wspólnego źródła: nie motyw i nie sam silnik lejka."""
    return group not in ("motif", "kit")


def _named(groups) -> list[dict]:
    return [{"group": g, "label": group_label(g)} for g in sorted(groups)]


def find(edge: Edge, limit: int = DEFAULT_LIMIT) -> dict:
    limit = max(1, min(int(limit), MAX_LIMIT))
    now_groups = _groups(row.kind for row in edge.evidence.all() if row.weight_bits > 0)
    pair = (edge.ad_a_id, edge.ad_b_id)

    latest: dict[tuple, EdgeDecision] = {}
    for decision in EdgeDecision.objects.exclude(ad_a_id=pair[0], ad_b_id=pair[1]).select_related("user").order_by("-created_at", "-id"):
        key = (decision.ad_a_id, decision.ad_b_id) if decision.ad_a_id or decision.ad_b_id else ("decision", decision.pk)
        latest.setdefault(key, decision)

    skipped = 0
    candidates = []
    for decision in latest.values():
        if not decision.snapshot:
            skipped += 1
            continue
        snap = decision.snapshot
        then_groups = _groups(e["kind"] for e in snap.get("evidence", []) if e.get("weight_bits", 0) > 0)
        shared = now_groups & then_groups
        if not {g for g in shared if g != "motif"}:
            continue
        union = now_groups | then_groups
        candidates.append((len(shared) / len(union), snap.get("relation") == edge.relation, decision, shared, then_groups))

    candidates.sort(key=lambda c: (-c[0], not c[1], -c[2].created_at.timestamp(), -c[2].pk))
    precedents = [_describe(edge, now_groups, *c) for c in candidates[:limit]]
    verdicts = {p["verdict"] for p in precedents if p["verdict"] in (Edge.Verdict.CONFIRMED, Edge.Verdict.REJECTED)}
    return {
        "edge": edge.pk,
        "edge_version": edge.updated_at.isoformat(),
        "relation": edge.relation,
        "groups": _named(now_groups),
        "status": "found" if precedents else "none",
        "considered": len(latest),
        "matching": len(candidates),
        "skipped_without_snapshot": skipped,
        "limit": limit,
        "conflict": len(verdicts) > 1,
        "notice": NOTICE,
        "precedents": precedents,
    }


def _describe(edge: Edge, now_groups: set[str], score: float, same_relation: bool, decision: EdgeDecision,
              shared: set[str], then_groups: set[str]) -> dict:
    snap = decision.snapshot
    only_now, only_then = now_groups - then_groups, then_groups - now_groups
    new_independent = {g for g in only_now if _independent(g)}
    why = [f"Wspólne grupy śladów: {', '.join(group_label(g) for g in sorted(shared))}."]
    if same_relation:
        why.append(f"Ta sama relacja wyliczona przez silnik: {RELATION_LABELS.get(edge.relation, edge.relation)}.")
    differences = []
    if new_independent:
        differences.append(
            "Ta krawędź ma niezależne ślady, których precedens nie miał: "
            + ", ".join(group_label(g) for g in sorted(new_independent)) + ". Wcześniejsza decyzja ich nie oceniała."
        )
    if only_then:
        differences.append("Precedens miał ślady, których tu nie ma: " + ", ".join(group_label(g) for g in sorted(only_then)) + ".")
    if not same_relation:
        differences.append(
            f"Inna relacja: wtedy {RELATION_LABELS.get(snap.get('relation'), snap.get('relation'))}, "
            f"teraz {RELATION_LABELS.get(edge.relation, edge.relation)}."
        )
    if snap.get("model_version") and snap.get("model_version") != edge.model_version:
        differences.append(f"Inna wersja modelu: wtedy {snap['model_version']}, teraz {edge.model_version}.")
    reason_known = decision.reason != EdgeDecision.Reason.UNKNOWN
    if not reason_known:
        differences.append("Decyzja nie ma podanego powodu, więc nie wiadomo, co przesądziło.")
    return {
        "decision": decision.pk,
        "edge": decision.edge_id,
        "ad_a": decision.ad_a_id,
        "ad_b": decision.ad_b_id,
        "verdict": decision.verdict,
        "reason": decision.reason,
        "reason_label": EdgeDecision.Reason(decision.reason).label,
        "reason_known": reason_known,
        "note": decision.note,
        "user": decision.user.get_username() if decision.user else None,
        "created_at": decision.created_at.isoformat(),
        "source": "decyzja analityka z migawką dowodów",
        "similarity": round(score, 3),
        "same_relation": same_relation,
        "relation_then": snap.get("relation"),
        "relation_now": edge.relation,
        "model_then": snap.get("model_version"),
        "shared_groups": _named(shared),
        "only_now": _named(only_now),
        "only_then": _named(only_then),
        "new_independent": _named(new_independent),
        "why": why,
        "differences": differences,
        "evidence_then": [
            {"kind": e["kind"], "label": KINDS[e["kind"]].label if e["kind"] in KINDS else e["kind"], "weight_bits": e.get("weight_bits", 0)}
            for e in snap.get("evidence", [])
        ][:12],
    }
