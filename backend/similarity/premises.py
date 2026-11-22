"""Zakwestionowanie przesłanki: globalne podważenie jednego śladu (rodzaj i wartość).

Ślad bywa wspólny nie przez operatora, tylko przez wspólnego usługodawcę albo skopiowany materiał.
Podgląd liczy, co stałoby się z krawędziami i grupami bez tego śladu, i niczego nie zapisuje.
Zapis dodaje wiersz `Premise`, po czym `service.pair_inputs` pomija ślad przy budowie dowodów,
reklamy z tym śladem są łączone od nowa (`link_ad`), a grupy rozdzielane (`recluster`).
Przywrócenie robi odwrotnie. Wiersz zostaje w historii razem ze stanem przed i po.
"""

from collections import defaultdict

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from ads.models import Ad
from evidence.kinds import FAMILIES, KINDS
from evidence.models import AdMarker, AuditLog, Marker
from people.display import display_value

from . import fusion, service, simulation
from .decisions import redact_note
from .models import Edge, EdgeEvidence, Premise

REASON_MAX = 2000
TOP_KINDS = 3


def check(kind: str, value: str) -> list[int]:
    """Sprawdza rodzaj i wartość, zwraca id reklam z tym markerem. SimulationError 400 albo 404."""
    spec = KINDS.get(kind)
    if spec is None:
        raise simulation.SimulationError("Nieznany rodzaj śladu.", kind=kind)
    if spec.soft:
        raise simulation.SimulationError(
            "Ślad miękki (podobieństwo) nie ma jednej wartości do zakwestionowania. Wyłącz dowód w laboratorium krawędzi.", kind=kind
        )
    marker = Marker.objects.filter(kind=kind, value_hash=Marker.hash_value(value)).first()
    ads = sorted(AdMarker.objects.filter(marker=marker).values_list("ad_id", flat=True)) if marker else []
    if not ads:
        raise simulation.SimulationError("Żadna reklama nie ma takiego śladu.", status=404, kind=kind)
    return ads


def _hit(row: EdgeEvidence, kind: str, value: str) -> bool:
    return row.kind == kind and value in (row.value_a, row.value_b)


def _hit_edges(kind: str, value: str):
    ids = EdgeEvidence.objects.filter(kind=kind).filter(Q(value_a=value) | Q(value_b=value)).values_list("edge_id", flat=True)
    return Edge.objects.filter(pk__in=ids).exclude(verdict=Edge.Verdict.REJECTED).order_by("pk")


def _kind_info(kind: str) -> dict:
    spec = KINDS[kind]
    return {"kind": kind, "label": spec.label, "family": spec.family, "family_label": FAMILIES.get(spec.family, spec.family)}


def _group_key(model, pk: int) -> str:
    return model(pk=pk).key


def state(ad_ids) -> dict:
    """Grupy (skład) i krawędzie dotkniętych reklam w tej chwili. Do porównania przed i po."""
    ad_ids = list(ad_ids)
    groups = {}
    for name, (_rels, group_model, membership_model, field) in service.RECLUSTER_KINDS.items():
        gids = set(membership_model.objects.filter(ad_id__in=ad_ids).values_list(f"{field}_id", flat=True))
        members = defaultdict(list)
        for ad_id, gid in membership_model.objects.filter(**{f"{field}_id__in": gids}).values_list("ad_id", f"{field}_id"):
            members[gid].append(ad_id)
        groups[name] = [{"key": _group_key(group_model, gid), "ads": sorted(ads)} for gid, ads in sorted(members.items())]
    edges = [
        {"id": e.pk, "ad_a": e.ad_a_id, "ad_b": e.ad_b_id, "relation": e.relation, "bits": round(e.bits, 2), "probability": round(e.probability, 4)}
        for e in Edge.objects.filter(ad_a_id__in=ad_ids, ad_b_id__in=ad_ids).exclude(verdict=Edge.Verdict.REJECTED).order_by("pk")
    ]
    return {"groups": groups, "edges": edges}


def _parts(pairs: list[tuple[int, int]]) -> list[set[int]]:
    # Tak samo jak `service._split_group`: składowe z co najmniej dwiema reklamami, największa pierwsza.
    parts = [c for c in fusion.connected_components(pairs) if len(c) >= 2]
    parts.sort(key=lambda c: (-len(c), min(c)))
    return parts


def preview(kind: str, value: str) -> dict:
    """Co stałoby się z krawędziami i grupami bez tego śladu. Niczego nie zapisuje."""
    ad_ids = check(kind, value)
    edges = list(_hit_edges(kind, value))
    rows_by_edge: dict[int, list[EdgeEvidence]] = defaultdict(list)
    for row in EdgeEvidence.objects.filter(edge_id__in=[e.pk for e in edges]):
        rows_by_edge[row.edge_id].append(row)

    edge_items, after_relation = [], {}
    for edge in edges:
        rows = rows_by_edge[edge.pk]
        corpus_n = max((r.corpus_n for r in rows), default=0)
        after = simulation.score([r for r in rows if not _hit(r, kind, value)], corpus_n)
        # Krawędź z werdyktem analityka nie znika: zostaje relacja, odświeżają się tylko liczby.
        kept = after.relation is None and bool(edge.verdict)
        relation = edge.relation if kept else after.relation
        after_relation[edge.pk] = relation
        edge_items.append({
            "id": edge.pk,
            "ad_a": edge.ad_a_id,
            "ad_b": edge.ad_b_id,
            "verdict": edge.verdict,
            "before": {"relation": edge.relation, "relation_label": simulation.RELATION_LABELS[edge.relation], "bits": round(edge.bits, 2), "probability": round(edge.probability, 4)},
            "after": {
                "relation": relation,
                "relation_label": simulation.RELATION_LABELS[relation],
                "bits": round(after.bits, 2),
                "probability": round(after.probability, 4),
                "independent": after.checks.get("independent", []),
                "kept_by_verdict": kept,
            },
            "removed": relation is None,
            "relation_changed": relation != edge.relation,
        })

    affected = {a for e in edges for a in (e.ad_a_id, e.ad_b_id)}
    out_groups = {}
    for name, (rels, group_model, membership_model, field) in service.RECLUSTER_KINDS.items():
        gids = set(membership_model.objects.filter(ad_id__in=affected).values_list(f"{field}_id", flat=True))
        split, stay = [], []
        for gid in sorted(gids):
            members = set(membership_model.objects.filter(**{f"{field}_id": gid}).values_list("ad_id", flat=True))
            group_edges = list(
                Edge.objects.filter(ad_a_id__in=members, ad_b_id__in=members, relation__in=rels)
                .exclude(verdict=Edge.Verdict.REJECTED)
            )
            pairs = [(e.ad_a_id, e.ad_b_id) for e in group_edges if after_relation.get(e.pk, e.relation) in rels]
            parts = _parts(pairs)
            key = _group_key(group_model, gid)
            linked = set().union(*parts) if parts else set()
            item = {"key": key, "before": sorted(members)}
            if len(parts) == 1 and parts[0] == members:
                item["supported_by"] = _supported_by(group_edges, kind, value)
                stay.append(item)
            else:
                item["after"] = [{"key": key if i == 0 else None, "ads": sorted(p)} for i, p in enumerate(parts)]
                item["released"] = sorted(members - linked)
                split.append(item)
        out_groups[name] = {"split": split, "stay": stay}

    return {
        **_kind_info(kind),
        "value": value,
        "display_value": display_value(kind, value),
        "ads": ad_ids,
        "edge_count": len(edge_items),
        "edges": edge_items,
        "groups": out_groups,
        "split_count": sum(len(g["split"]) for g in out_groups.values()),
        "model_version": fusion.MODEL_VERSION,
        "warnings": ["Podgląd niczego nie zapisuje. Liczy tylko krawędzie z tym śladem, resztę grafu bierze bez zmian."],
    }


def _supported_by(group_edges: list[Edge], kind: str, value: str) -> list[dict]:
    """Najmocniejsze rodzaje śladów, które trzymają grupę mimo utraty zakwestionowanego."""
    best: dict[str, float] = {}
    for row in EdgeEvidence.objects.filter(edge_id__in=[e.pk for e in group_edges]):
        if _hit(row, kind, value):
            continue
        best[row.kind] = max(best.get(row.kind, 0.0), row.weight_bits)
    top = sorted(best.items(), key=lambda kv: (-kv[1], kv[0]))[:TOP_KINDS]
    return [{**_kind_info(k), "bits": round(bits, 2)} for k, bits in top if bits > 0]


def _relink(ad_ids: list[int]) -> list[int]:
    removed: set[int] = set()
    for ad in Ad.objects.filter(pk__in=ad_ids).order_by("pk"):
        _edges, gone = service.link_ad_detailed(ad)
        removed.update(gone)
    return sorted(removed | set(ad_ids))


@transaction.atomic
def challenge(kind: str, value: str, reason: str, user=None) -> Premise:
    ad_ids = check(kind, value)
    if Premise.objects.select_for_update().filter(kind=kind, value=value, status=Premise.Status.CHALLENGED).exists():
        raise simulation.SimulationError("Ta przesłanka jest już zakwestionowana.", status=409, kind=kind)
    before = state(ad_ids)
    premise = Premise.objects.create(kind=kind, value=value, reason=redact_note(reason)[:REASON_MAX], user=user, before=before)
    touched = _relink(ad_ids)
    regroup = service.recluster(touched)
    premise.after = {**state(ad_ids), "regroup": regroup}
    premise.save(update_fields=["after"])
    AuditLog.objects.create(
        user=user, action="premise.challenge", object_type="premise", object_id=str(premise.pk),
        payload={"kind": kind, "ads": len(ad_ids), "reason": premise.reason},
    )
    premise.regroup = regroup
    return premise


@transaction.atomic
def restore(premise_id: int, user=None) -> Premise:
    premise = Premise.objects.select_for_update().get(pk=premise_id)
    if premise.status != Premise.Status.CHALLENGED:
        raise simulation.SimulationError("Ta przesłanka jest już przywrócona.", status=409)
    ad_ids = check_ads(premise.kind, premise.value)
    premise.status = Premise.Status.RESTORED
    premise.restored_at = timezone.now()
    premise.save(update_fields=["status", "restored_at"])
    touched = _relink(ad_ids)
    for ad in Ad.objects.filter(pk__in=ad_ids).order_by("pk"):
        service.assign_campaign(ad)
        service.assign_operator(ad)
    regroup = service.recluster(touched)
    premise.restored_state = {**state(ad_ids), "regroup": regroup}
    premise.save(update_fields=["restored_state"])
    AuditLog.objects.create(
        user=user, action="premise.restore", object_type="premise", object_id=str(premise.pk),
        payload={"kind": premise.kind, "ads": len(ad_ids)},
    )
    premise.regroup = regroup
    return premise


def check_ads(kind: str, value: str) -> list[int]:
    marker = Marker.objects.filter(kind=kind, value_hash=Marker.hash_value(value)).first()
    return sorted(AdMarker.objects.filter(marker=marker).values_list("ad_id", flat=True)) if marker else []


def serialize(premise: Premise, with_state: bool = True) -> dict:
    spec = KINDS.get(premise.kind)
    out = {
        "id": premise.pk,
        "kind": premise.kind,
        "label": spec.label if spec else premise.kind,
        "value": premise.value,
        "display_value": display_value(premise.kind, premise.value),
        "status": premise.status,
        "status_label": Premise.Status(premise.status).label,
        "reason": premise.reason,
        "user": premise.user.get_username() if premise.user else None,
        "created_at": premise.created_at.isoformat(),
        "restored_at": premise.restored_at.isoformat() if premise.restored_at else None,
    }
    if with_state:
        out.update(before=premise.before, after=premise.after, restored_state=premise.restored_state or None)
    return out
