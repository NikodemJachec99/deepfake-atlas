"""Łączenie reklamy z resztą korpusu: kandydaci z indeksu markerów, ocena par, zapis krawędzi z dowodami."""

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

from django.db import transaction
from django.db.models import BigIntegerField, Case, Count, F, FloatField, Q, Sum, Value, When
from django.db.models.functions import Coalesce
from pgvector.django import CosineDistance

from ads.models import Ad
from evidence.kinds import BAND_KINDS, BAND_OF, KINDS
from evidence.models import AdMarker, AdSignature, AuditLog
from extractors import images, minhash

from . import fusion
from .models import Campaign, CampaignMembership, Edge, EdgeEvidence, Operator, OperatorMembership

MAX_CANDIDATES = 500
# Sąsiedzi z indeksu HNSW po znaczeniu treści: najwyżej tylu, i tylko bliżsi niż ten dystans kosinusowy.
SEMANTIC_NEIGHBOURS = 20
SEMANTIC_MAX_DISTANCE = 0.25  # poniżej progu lo=0,75 marker i tak nic nie wnosi
IMAGE_NEIGHBOURS = 20
IMAGE_MAX_DISTANCE = 0.18  # poniżej progu lo=0,82 marker i tak nic nie wnosi
# Zbiory obrazów porównujemy po odległości Hamminga, pozostałe sygnatury to MinHash.
# Treść jest odporna na doklejoną sekcję: zapis strony z komentarzami to wciąż ten sam artykuł.
SOFT_SIMILARITY = {
    "image_set": images.set_similarity,
    "video_frames": images.set_similarity,
    "page_text_minhash": minhash.text_similarity,
    "text_minhash": minhash.text_similarity,
}


SOFT_OF_BAND = {band: soft for soft, band in BAND_OF.items()}


def hub_limit(corpus_n: int) -> int:
    """Marker obecny w większej liczbie niezależnych źródeł jest hubem. Po hubach nie szukamy kandydatów."""
    return max(100, corpus_n // 100)


def _owner():
    # Źródłem jest kampania, a dla reklamy bez kampanii ona sama (ujemny identyfikator, żeby się nie zderzały).
    return Coalesce(F("ad__membership__campaign_id"), F("ad_id") * Value(-1), output_field=BigIntegerField())


def corpus_size() -> int:
    """Liczba niezależnych źródeł: kampanie plus reklamy, które do żadnej nie należą."""
    campaigns = CampaignMembership.objects.values("campaign_id").distinct().count()
    return Ad.objects.filter(membership__isnull=True).count() + campaigns


def source_counts(marker_ids) -> dict[int, int]:
    """W ilu niezależnych źródłach występuje marker.

    Liczenie po reklamach karałoby duże kampanie: ich własny identyfikator wyglądałby na pospolity
    i kolejne odsłony przestałyby się do nich przyklejać.
    """
    rows = (
        AdMarker.objects.filter(marker_id__in=list(marker_ids))
        .annotate(owner=_owner())
        .values("marker_id")
        .annotate(n=Count("owner", distinct=True))
    )
    return {row["marker_id"]: row["n"] for row in rows}


@dataclass
class PairInputs:
    """Wejście modelu dla jednej pary (reklama, kandydat): wspólne markery i podobieństwa miękkie."""

    other_id: int
    shared: list[fusion.Shared]
    soft: list[fusion.Soft]
    artifacts: dict


def _rank_weights(own: dict[int, AdMarker], search_ids: list[int], sources: dict[int, int], corpus_n: int) -> dict[int, float]:
    """Waga rzadkości markera do kolejności kandydatów: marker rozstrzygający liczy się przed wszystkim."""
    out = {}
    for mid in search_ids:
        kind = own[mid].marker.kind
        bits = fusion.exact_bits(kind, sources.get(mid, 1) + 1, corpus_n)
        out[mid] = bits + (1000.0 if KINDS[kind].decisive and bits >= fusion.DECISIVE_BITS else 0.0)
    return out


def pair_inputs(ad: Ad, corpus_n: int | None = None, only: Iterable[int] | None = None) -> list[PairInputs]:
    """Kandydaci reklamy z indeksu markerów, HNSW i pasm LSH, z wejściem modelu. Tylko odczyt.

    Z `only` ocenia dokładnie wskazane reklamy (np. dotychczasowych sąsiadów), bez szukania kandydatów.
    Kandydaci z indeksu markerów idą wg sumy wag rzadkości wspólnych markerów, potem od najnowszych,
    więc limit odcina najsłabsze powiązania, a nie najstarsze.

    Tę samą listę liczy `link_ad` przy zapisie krawędzi i `similarity.learning` przy uczeniu wag,
    więc model uczy się na dokładnie tych parach, które potem ocenia.
    """
    corpus_n = corpus_size() if corpus_n is None else corpus_n
    own = {am.marker_id: am for am in AdMarker.objects.filter(ad=ad).select_related("marker")}
    sources = source_counts(own.keys())
    limit = hub_limit(corpus_n)
    search_ids = [mid for mid, am in own.items() if KINDS[am.marker.kind].candidate and sources.get(mid, 1) <= limit]
    restrict = None if only is None else {pk for pk in only if pk != ad.pk}
    if restrict is not None:
        candidates = sorted(restrict)
    elif search_ids:
        weights = _rank_weights(own, search_ids, sources, corpus_n)
        score = Sum(Case(*[When(marker_id=mid, then=Value(w)) for mid, w in weights.items()], default=Value(0.0), output_field=FloatField()))
        candidates = list(
            AdMarker.objects.filter(marker_id__in=search_ids)
            .exclude(ad=ad)
            .values("ad_id")
            .annotate(score=score)
            .order_by("-score", "-ad_id")
            .values_list("ad_id", flat=True)[:MAX_CANDIDATES]
        )
    else:
        candidates = []
    own_vector = ad.text_embedding
    semantic: dict[int, float] = {}
    if own_vector is not None:
        neighbours = (
            Ad.objects.exclude(pk=ad.pk)
            .filter(text_embedding__isnull=False)
            .annotate(distance=CosineDistance("text_embedding", own_vector))
            .filter(distance__lt=SEMANTIC_MAX_DISTANCE)
            .order_by("distance")
        )
        if restrict is not None:
            neighbours = neighbours.filter(pk__in=restrict)
        neighbours = neighbours.values_list("pk", "distance")[:SEMANTIC_NEIGHBOURS]
        semantic = {pk: 1.0 - float(distance) for pk, distance in neighbours}
        if restrict is None:
            candidates = list(dict.fromkeys([*candidates, *semantic]))
    visual: dict[int, float] = {}
    if ad.image_embedding is not None:
        look = (
            Ad.objects.exclude(pk=ad.pk)
            .filter(image_embedding__isnull=False)
            .annotate(distance=CosineDistance("image_embedding", ad.image_embedding))
            .filter(distance__lt=IMAGE_MAX_DISTANCE)
            .order_by("distance")
        )
        if restrict is not None:
            look = look.filter(pk__in=restrict)
        look = look.values_list("pk", "distance")[:IMAGE_NEIGHBOURS]
        visual = {pk: 1.0 - float(distance) for pk, distance in look}
        if restrict is None:
            candidates = list(dict.fromkeys([*candidates, *visual]))
    if not candidates:
        return []

    shared_by_ad: dict[int, list[AdMarker]] = defaultdict(list)
    for am in AdMarker.objects.filter(ad_id__in=candidates, marker_id__in=own.keys()).select_related("marker"):
        shared_by_ad[am.ad_id].append(am)

    owner_of = dict(CampaignMembership.objects.filter(ad_id__in=[*candidates, ad.pk]).values_list("ad_id", "campaign_id"))
    own_owner = owner_of.get(ad.pk, -ad.pk)

    own_signatures = {s.kind: s.values for s in AdSignature.objects.filter(ad=ad)}
    other_signatures: dict[int, dict[str, list[int]]] = defaultdict(dict)
    if own_signatures:
        for s in AdSignature.objects.filter(ad_id__in=candidates, kind__in=own_signatures.keys()):
            other_signatures[s.ad_id][s.kind] = s.values

    out = []
    for other_id in sorted(candidates):
        theirs = shared_by_ad.get(other_id, [])
        # Model odejmuje parę jako dwa źródła. Gdy obie reklamy są już w jednej kampanii, to jedno źródło.
        pair_units = 1 if owner_of.get(other_id, -other_id) == own_owner else 2
        shared = [
            fusion.Shared(am.marker.kind, am.marker.value, sources.get(am.marker_id, pair_units) - pair_units + 2)
            for am in theirs
            if am.marker.kind not in BAND_KINDS
        ]
        soft = [
            fusion.Soft(kind, SOFT_SIMILARITY.get(kind, minhash.similarity)(values, other_signatures[other_id][kind]))
            for kind, values in own_signatures.items()
            if kind in BAND_OF and kind in other_signatures.get(other_id, {})
        ]
        if other_id in semantic:
            soft.append(fusion.Soft("text_embedding", semantic[other_id]))
        if other_id in visual:
            soft.append(fusion.Soft("image_embedding", visual[other_id]))
        artifacts = {}
        for am in theirs:
            pair = (own[am.marker_id].artifact_id, am.artifact_id)
            kind = am.marker.kind
            if kind in BAND_KINDS:
                # Dowód miękki (podobieństwo sygnatur) wskazuje plik, z którego policzono pasma.
                key = (SOFT_OF_BAND[kind], "")
                if key not in artifacts or not all(artifacts[key]):
                    artifacts[key] = pair
            else:
                artifacts[(kind, am.marker.value)] = pair
        out.append(PairInputs(other_id, shared, soft, artifacts))
    return out


@transaction.atomic
def link_ad(ad: Ad) -> list[Edge]:
    """Liczy krawędzie reklamy do wszystkich kandydatów. Bezpieczne do ponownego uruchomienia."""
    corpus_n = corpus_size()
    edges = []
    pairs = pair_inputs(ad, corpus_n)
    seen = {pair.other_id for pair in pairs}
    # Dotychczasowi sąsiedzi, którzy nie są już kandydatami (znikły wspólne ślady albo wypadli z limitu),
    # też są oceniani od nowa, żeby nie zostawała po nich nieaktualna krawędź.
    neighbours = set(Edge.objects.filter(ad_a=ad).values_list("ad_b_id", flat=True)) | set(
        Edge.objects.filter(ad_b=ad).values_list("ad_a_id", flat=True)
    )
    if neighbours - seen:
        pairs += pair_inputs(ad, corpus_n, only=neighbours - seen)
    for pair in pairs:
        result = fusion.score_pair(pair.shared, pair.soft, corpus_n)
        edge = _store_edge(ad.pk, pair.other_id, result, pair.artifacts)
        if edge:
            edges.append(edge)
    return edges


def _store_edge(ad_id: int, other_id: int, result: fusion.PairResult, artifacts: dict) -> Edge | None:
    a, b = sorted((ad_id, other_id))
    flipped = a != ad_id
    existing = Edge.objects.filter(ad_a_id=a, ad_b_id=b).first()
    if result.relation is None:
        # Decyzji analityka nie kasujemy, nawet gdy model zmienił zdanie.
        if existing and not existing.verdict:
            existing.delete()
            return None
        if not (existing and result.evidence):
            return None
        # Z werdyktem: dowody i liczby się odświeżają, relacja i werdykt zostają.

    edge = existing or Edge(ad_a_id=a, ad_b_id=b)
    if result.relation is not None:
        edge.relation = result.relation
    edge.bits = result.bits
    edge.probability = result.probability
    edge.decisive = result.decisive
    edge.duplicate = result.duplicate
    edge.families = result.families
    edge.model_version = fusion.MODEL_VERSION
    edge.save()

    edge.evidence.all().delete()
    rows = []
    for item in result.evidence:
        art_own, art_other = artifacts.get((item.kind, item.value_a)) or artifacts.get((item.kind, "")) or (None, None)
        art_a, art_b = (art_other, art_own) if flipped else (art_own, art_other)
        value_a, value_b = (item.value_b, item.value_a) if flipped else (item.value_a, item.value_b)
        rows.append(
            EdgeEvidence(
                edge=edge, family=item.family, kind=item.kind, value_a=value_a, value_b=value_b,
                similarity=item.similarity, df=item.df, corpus_n=item.corpus_n, raw_bits=item.raw_bits,
                weight_bits=item.weight_bits, decisive=item.decisive, artifact_a_id=art_a, artifact_b_id=art_b,
            )
        )
    EdgeEvidence.objects.bulk_create(rows)
    return edge


def _assign(ad: Ad, relations: list[str], group_model, membership_model, field: str) -> dict:
    edges = Edge.objects.filter(Q(ad_a=ad) | Q(ad_b=ad), relation__in=relations).exclude(verdict=Edge.Verdict.REJECTED)
    neighbours = {edge.other(ad.pk) for edge in edges}
    current = membership_model.objects.filter(ad=ad).first()
    if not neighbours:
        return {"key": getattr(current, field).key if current else None, "action": "none", "neighbours": 0}

    member_of = dict(membership_model.objects.filter(ad_id__in=neighbours).values_list("ad_id", f"{field}_id"))
    group_ids = set(member_of.values()) | ({getattr(current, f"{field}_id")} if current else set())

    if not group_ids:
        group = group_model.objects.create()
        action = "created"
    else:
        group = group_model.objects.get(pk=min(group_ids))
        action = "joined" if len(group_ids) == 1 else "merged"
        # Reklama okazała się mostem między grupami: scalamy je w najstarszą.
        for other_id in group_ids - {group.pk}:
            membership_model.objects.filter(**{f"{field}_id": other_id}).update(**{field: group})
            group_model.objects.filter(pk=other_id).update(merged_into=group)

    for ad_id in neighbours | {ad.pk}:
        membership_model.objects.update_or_create(ad_id=ad_id, defaults={field: group})
    return {"key": group.key, "id": group.pk, "action": action, "neighbours": len(neighbours), "size": group.memberships.count()}


@transaction.atomic
def assign_campaign(ad: Ad) -> dict:
    """Kampania: reklamy połączone krawędziami `same_campaign`, których analityk nie odrzucił."""
    result = _assign(ad, [Edge.Relation.SAME_CAMPAIGN], Campaign, CampaignMembership, "campaign")
    out = {"campaign": result["key"], "action": result["action"], "neighbours": result["neighbours"]}
    if "id" in result:
        out.update(campaign_id=result["id"], size=result["size"])
    return out


@transaction.atomic
def assign_operator(ad: Ad) -> dict:
    """Operator: reklamy o wspólnym zapleczu, także gdy prowadzą różne kampanie."""
    result = _assign(ad, [Edge.Relation.SAME_CAMPAIGN, Edge.Relation.SAME_OPERATOR], Operator, OperatorMembership, "operator")
    out = {"operator": result["key"], "operator_action": result["action"]}
    if "id" in result:
        out.update(operator_id=result["id"], operator_size=result["size"])
    return out


RECLUSTER_KINDS = {
    "campaign": ([Edge.Relation.SAME_CAMPAIGN], Campaign, CampaignMembership, "campaign"),
    "operator": ([Edge.Relation.SAME_CAMPAIGN, Edge.Relation.SAME_OPERATOR], Operator, OperatorMembership, "operator"),
}


def _split_group(group, rels, membership_model, field: str) -> dict | None:
    """Rozdziela jedną grupę na składowe spójne po nieodrzuconych krawędziach. None, gdy nic się nie zmienia."""
    members = set(membership_model.objects.filter(**{f"{field}_id": group.pk}).values_list("ad_id", flat=True))
    if not members:
        return None
    pairs = list(
        Edge.objects.filter(ad_a_id__in=members, ad_b_id__in=members, relation__in=rels)
        .exclude(verdict=Edge.Verdict.REJECTED)
        .values_list("ad_a_id", "ad_b_id")
    )
    parts = [c for c in fusion.connected_components(pairs) if len(c) >= 2]
    linked = set().union(*parts) if parts else set()
    # Największa składowa zachowuje grupę, przy remisie ta z najmniejszym id reklamy.
    parts.sort(key=lambda c: (-len(c), min(c)))
    if len(parts) == 1 and parts[0] == members:
        return None
    released = sorted(members - linked)
    keeper = parts[0] if parts else set()
    after = []
    if keeper:
        after.append({"key": group.key, "ads": sorted(keeper)})
    group_model = type(group)
    for part in parts[1:]:
        new = group_model.objects.create(label=group.label)
        membership_model.objects.filter(ad_id__in=part).update(**{field: new})
        after.append({"key": new.key, "ads": sorted(part)})
    if released:
        membership_model.objects.filter(ad_id__in=released).delete()
    return {"group": group.key, "before": sorted(members), "after": after, "released": released}


@transaction.atomic
def recluster(ad_ids) -> dict:
    """Przelicza grupy dotkniętych reklam od strony rozdzielania: `_assign` tylko tworzy i scala.

    Dla kampanii i osobno operatorów bierze grupy, do których należą te reklamy, liczy składowe po
    nieodrzuconych krawędziach właściwych relacji i rozdziela grupę. Nowych alertów nie tworzy.
    Zwraca opis zmian per rodzaj grupy, pusty gdy nic się nie zmieniło.
    """
    ad_ids = list(ad_ids)
    out: dict[str, list] = {}
    for name, (rels, group_model, membership_model, field) in RECLUSTER_KINDS.items():
        group_ids = set(membership_model.objects.filter(ad_id__in=ad_ids).values_list(f"{field}_id", flat=True))
        changes = []
        for group in group_model.objects.select_for_update().filter(pk__in=group_ids, merged_into__isnull=True).order_by("pk"):
            change = _split_group(group, rels, membership_model, field)
            if change:
                changes.append(change)
        out[name] = changes
    if any(out.values()):
        AuditLog.objects.create(action="groups.recluster", object_type="ad", object_id=",".join(map(str, ad_ids[:20])), payload=out)
    return out
