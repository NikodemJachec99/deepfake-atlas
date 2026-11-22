"""Kolejka "Do oceny": krawędzie bez werdyktu z powodem, dla którego analityk powinien na nie spojrzeć.

Powód jest jeden na krawędź, w kolejności priorytetu (REASONS). Krawędź z werdyktem do kolejki nie wchodzi.
Kolejność w kolejce: priorytet powodu, potem malejący wynik modelu."""

from collections import defaultdict
from urllib.parse import urlsplit

from ads.models import Analysis
from evidence.kinds import CONCEPT_FAMILIES, FAMILIES, KINDS
from extractors.url import redact_url
from people.display import PERSON_KINDS, display_value, person_names
from similarity.fusion import FAMILY_MIN_BITS
from similarity.models import Alert, CampaignMembership, Edge, EdgeDecision, EdgeEvidence, OperatorMembership, Premise

# (kod, opis dla człowieka). Kolejność to priorytet.
REASONS: list[tuple[str, str]] = [
    ("challenged", "Krawędź używa śladu z zakwestionowanej przesłanki"),
    ("changed_after_decision", "Krawędź zmieniona po decyzji w jej grupie"),
    ("unbacked", "Relacja bez śladu zaplecza albo oparta na jednym decydującym śladzie"),
    ("borderline", "Wynik modelu na granicy (0,5 do 0,9)"),
    ("new_in_group", "Nowa reklama w znanej grupie, bez decyzji na jej krawędziach"),
    ("operator_to_confirm", "Wspólne zaplecze do potwierdzenia"),
    ("campaign_to_confirm", "Ta sama kampania do potwierdzenia"),
    ("content_only", "Podobna treść bez wspólnego zaplecza"),
    ("other", "Bez decyzji"),
]
RELATION_REASON = {"same_operator": "operator_to_confirm", "same_campaign": "campaign_to_confirm", "similar": "content_only"}
REASON_LABELS = dict(REASONS)
PRIORITY = {code: i for i, (code, _) in enumerate(REASONS)}

BORDERLINE_LOW, BORDERLINE_HIGH = 0.5, 0.9
HIGH_DF = 5  # ślad współdzielony przez tyle reklam i więcej jest ostrzeżeniem
TOP_EVIDENCE = 3
VALUE_MAX = 200
JOINED_ALERTS = ("joined_campaign", "new_campaign_known_operator", "joined_operator")


def _independent_families(rows) -> list[str]:
    """Rodziny, które liczą się jako niezależne potwierdzenie (jak w fusion.py: motywy pomijamy, ślady lejka to jedna grupa)."""
    bits: dict[str, float] = {}
    for row in rows:
        kind = KINDS.get(row.kind)
        if kind is None or kind.motif:
            continue
        group = "kit" if kind.kit else row.family
        bits[group] = bits.get(group, 0.0) + row.weight_bits
    return [f for f, b in bits.items() if b >= FAMILY_MIN_BITS]


def is_unbacked(edge: Edge, rows) -> bool:
    if edge.relation not in (Edge.Relation.SAME_OPERATOR, Edge.Relation.SAME_CAMPAIGN):
        return False
    strong = _independent_families(rows)
    backed = any(f not in CONCEPT_FAMILIES for f in strong)
    single_decisive = sum(1 for r in rows if r.decisive) == 1 and len(strong) < 2
    return not backed or single_decisive


def _group_ids(ad_ids: set[int]) -> tuple[dict[int, int], dict[int, int]]:
    campaigns = dict(CampaignMembership.objects.filter(ad_id__in=ad_ids).values_list("ad_id", "campaign_id"))
    operators = dict(OperatorMembership.objects.filter(ad_id__in=ad_ids).values_list("ad_id", "operator_id"))
    return campaigns, operators


def _decision_times() -> tuple[dict[tuple[str, int], object], set[int]]:
    """Czas ostatniej decyzji w każdej grupie i reklamy, które mają jakąkolwiek decyzję na swoich krawędziach."""
    rows = list(EdgeDecision.objects.values_list("ad_a_id", "ad_b_id", "created_at"))
    ads = {a for r in rows for a in r[:2] if a}
    campaigns, operators = _group_ids(ads)
    last: dict[tuple[str, int], object] = {}
    for ad_a, ad_b, at in rows:
        for ad in (ad_a, ad_b):
            for kind, mapping in (("campaign", campaigns), ("operator", operators)):
                gid = mapping.get(ad)
                key = (kind, gid)
                if gid is not None and (key not in last or last[key] < at):
                    last[key] = at
    decided_ads = ads | set(Edge.objects.exclude(verdict="").values_list("ad_a_id", flat=True)) | set(
        Edge.objects.exclude(verdict="").values_list("ad_b_id", flat=True))
    return last, decided_ads


def queue(source: str = "capture", relation: str = "", reason: str = "") -> list[dict]:
    """Posortowana kolejka: lista `{edge, rows, reason}`. Dowody ładowane są hurtem, bez zapytania na krawędź."""
    edges = Edge.objects.filter(verdict="").select_related("ad_a", "ad_b")
    if source != "all":
        edges = edges.filter(ad_a__source=source, ad_b__source=source)
    if relation:
        edges = edges.filter(relation=relation)
    edges = list(edges)
    if not edges:
        return []

    evidence: dict[int, list] = defaultdict(list)
    for row in EdgeEvidence.objects.filter(edge_id__in=[e.pk for e in edges]).order_by("-weight_bits", "kind", "pk"):
        evidence[row.edge_id].append(row)

    ad_ids = {a for e in edges for a in (e.ad_a_id, e.ad_b_id)}
    campaigns, operators = _group_ids(ad_ids)
    last_decision, decided_ads = _decision_times()
    joined = set(Alert.objects.filter(kind__in=JOINED_ALERTS, ad_id__in=ad_ids).values_list("ad_id", flat=True))

    challenged = defaultdict(set)
    for kind, value in Premise.objects.filter(status=Premise.Status.CHALLENGED).values_list("kind", "value"):
        challenged[kind].add(value)

    out = []
    for edge in edges:
        rows = evidence[edge.pk]
        groups = [(k, m[a]) for a in (edge.ad_a_id, edge.ad_b_id) for k, m in (("campaign", campaigns), ("operator", operators)) if a in m]
        if any(r.value_a in challenged[r.kind] or r.value_b in challenged[r.kind] for r in rows if r.kind in challenged):
            code = "challenged"
        elif any((g in last_decision and edge.updated_at > last_decision[g]) for g in groups):
            code = "changed_after_decision"
        elif is_unbacked(edge, rows):
            code = "unbacked"
        elif BORDERLINE_LOW <= edge.probability < BORDERLINE_HIGH:
            code = "borderline"
        elif joined & {edge.ad_a_id, edge.ad_b_id} and not ({edge.ad_a_id, edge.ad_b_id} & decided_ads):
            code = "new_in_group"
        else:
            code = RELATION_REASON.get(edge.relation, "other")
        if reason and code != reason:
            continue
        out.append({"edge": edge, "rows": rows, "reason": code})
    out.sort(key=lambda item: (PRIORITY[item["reason"]], -item["edge"].probability, item["edge"].pk))
    return out


def pending_count() -> int:
    return len(queue("capture"))


def limitations(edge: Edge, rows, reason: str) -> list[str]:
    out = []
    non_concept = [r for r in rows if r.family not in CONCEPT_FAMILIES]
    if not non_concept:
        out.append("brak śladu zaplecza")
        if any(KINDS[r.kind].story for r in rows if r.kind in KINDS):
            out.append("kopia treści bez wspólnej infrastruktury")
    if edge.relation in (Edge.Relation.SAME_OPERATOR, Edge.Relation.SAME_CAMPAIGN) and sum(1 for r in rows if r.decisive) == 1 and len(_independent_families(rows)) < 2:
        out.append("jeden decydujący ślad, bez niezależnego potwierdzenia")
    shared: dict[str, int] = {}
    for row in rows:
        if row.df >= HIGH_DF:
            label = KINDS[row.kind].label if row.kind in KINDS else row.kind
            shared[label] = max(shared.get(label, 0), row.df)
    for label, df in sorted(shared.items(), key=lambda t: -t[1])[:2]:
        out.append(f"ślad „{label}” współdzielony przez {df} reklam")
    if rows and all(KINDS[r.kind].motif for r in rows if r.kind in KINDS):
        out.append("tylko wspólny motyw (osoba, marka, tematyka)")
    if edge.duplicate:
        out.append("ta sama strona przechwycona ponownie")
    if BORDERLINE_LOW <= edge.probability < BORDERLINE_HIGH:
        out.append("wynik modelu na granicy progu")
    if not rows:
        out.append("brak zapisanych dowodów krawędzi")
    return out


def thumbnails(ads) -> dict[int, str | None]:
    """Pierwsza kreacja reklamy, a gdy jej nie ma zrzut strony docelowej z ostatniej analizy."""
    thumbs: dict[int, str | None] = {}
    for ad in ads:
        creatives = ad.raw.get("creatives") if isinstance(ad.raw, dict) else None
        thumbs[ad.pk] = next((c for c in creatives or [] if isinstance(c, str) and c), None)
    missing = [pk for pk, sha in thumbs.items() if not sha]
    if missing:
        seen: set[int] = set()
        for analysis in Analysis.objects.filter(ad_id__in=missing).order_by("-created_at").only("ad_id", "state"):
            if analysis.ad_id in seen:
                continue
            victim = ((analysis.state or {}).get("pages") or {}).get("victim") or {}
            shot = victim.get("screenshot_sha")
            if isinstance(shot, str) and shot:
                thumbs[analysis.ad_id] = shot
                seen.add(analysis.ad_id)
    return thumbs


def _domain(url: str) -> str:
    return (urlsplit(redact_url(url or "")).hostname or "").lower()


def serialize(items: list[dict]) -> list[dict]:
    """Pozycje kolejki w kształcie `ReviewItem`. Wywołuj tylko dla bieżącej strony."""
    ads = {}
    for item in items:
        for ad in (item["edge"].ad_a, item["edge"].ad_b):
            ads[ad.pk] = ad
    thumbs = thumbnails(ads.values())
    names = person_names()

    def ad_out(ad) -> dict:
        sha = thumbs.get(ad.pk)
        return {
            "id": ad.pk,
            "external_id": ad.external_id,
            "source": ad.source,
            "title": ad.title,
            "domain": _domain(ad.landing_url),
            "first_seen": ad.first_seen,
            "thumbnail": {"sha256": sha, "image": f"/api/artifacts/{sha}/image"} if sha else None,
        }

    def value(row) -> str:
        shown = display_value(row.kind, row.value_a, names) if row.kind in PERSON_KINDS else row.value_a
        if shown.lower().startswith(("http://", "https://")):
            shown = redact_url(shown)
        return shown[:VALUE_MAX]

    result = []
    for item in items:
        edge, rows = item["edge"], item["rows"]
        result.append({
            "id": edge.pk,
            "relation": edge.relation,
            "probability": edge.probability,
            "bits": edge.bits,
            "model_version": edge.model_version,
            "updated_at": edge.updated_at,
            "reason": item["reason"],
            "reason_label": REASON_LABELS[item["reason"]],
            "ad_a": ad_out(edge.ad_a),
            "ad_b": ad_out(edge.ad_b),
            "evidence": [
                {
                    "kind": r.kind,
                    "label": KINDS[r.kind].label if r.kind in KINDS else r.kind,
                    "family": r.family,
                    "family_label": FAMILIES.get(r.family, r.family),
                    "weight_bits": round(r.weight_bits, 2),
                    "value": value(r),
                    "artifact_a": r.artifact_a_id,
                    "artifact_b": r.artifact_b_id,
                }
                for r in rows[:TOP_EVIDENCE]
            ],
            "limitations": limitations(edge, rows, item["reason"]),
        })
    return result
