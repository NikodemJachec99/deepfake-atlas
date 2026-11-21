"""Alerty: reklama dołączyła do kampanii albo operatora, które były w korpusie, zanim ją zobaczyliśmy."""

from django.db.models import Q

from ads.models import Ad
from evidence.kinds import KINDS

from .models import Alert, CampaignMembership, Edge, EdgeEvidence, OperatorMembership

EVIDENCE_LIMIT = 3
EXISTING = {"joined", "merged"}  # grupa miała już członków, w odróżnieniu od "created" i "none"


def top_evidence(ad: Ad, member_ids) -> list[dict]:
    """Typy markerów o największym wkładzie w krawędzie reklamy do członków grupy (najlepsza wartość z każdego typu)."""
    edges = Edge.objects.filter(Q(ad_a=ad, ad_b_id__in=member_ids) | Q(ad_b=ad, ad_a_id__in=member_ids)).exclude(verdict=Edge.Verdict.REJECTED)
    best: dict[str, EdgeEvidence] = {}
    for row in EdgeEvidence.objects.filter(edge__in=edges, weight_bits__gt=0):
        if row.kind not in best or row.weight_bits > best[row.kind].weight_bits:
            best[row.kind] = row
    ranked = sorted(best.values(), key=lambda e: e.weight_bits, reverse=True)[:EVIDENCE_LIMIT]
    return [
        {"kind": e.kind, "label": KINDS[e.kind].label, "family": e.family, "bits": round(e.weight_bits, 2), "value": e.value_a[:120]}
        for e in ranked
    ]


def record(ad: Ad, *, was_in_campaign: bool, was_in_operator: bool, campaign: dict, operator: dict) -> list[Alert]:
    """Zapisuje alerty po przypisaniu reklamy. `campaign` i `operator` to wyniki `assign_campaign` i `assign_operator`.

    Alert wymaga, żeby reklama dopiero co weszła do grupy (nie była w niej przed tym wywołaniem) i żeby grupa
    miała wcześniej innych członków. To czyni zapis odpornym na ponowne uruchomienie etapu.
    """
    joined_campaign = not was_in_campaign and campaign.get("action") in EXISTING
    joined_operator = not was_in_operator and operator.get("operator_action") in EXISTING
    campaign_id, operator_id = campaign.get("campaign_id"), operator.get("operator_id")

    plan = None
    if joined_campaign:
        members = CampaignMembership.objects.filter(campaign_id=campaign_id).exclude(ad=ad).values_list("ad_id", flat=True)
        plan = (
            Alert.Kind.JOINED_CAMPAIGN, members,
            f"Reklama dołączyła do kampanii {campaign['campaign']} ({campaign['size']} reklam)",
        )
    elif joined_operator:
        members = OperatorMembership.objects.filter(operator_id=operator_id).exclude(ad=ad).values_list("ad_id", flat=True)
        plan = (
            Alert.Kind.NEW_CAMPAIGN_KNOWN_OPERATOR, members,
            f"Nowa kampania znanego operatora {operator['operator']} ({operator['operator_size']} reklam)",
        )
    if plan is None:
        return []

    kind, members, description = plan
    alerts = [_store(ad, kind, description, list(members), campaign_id, operator_id)]
    # Reklama-most, która scaliła grupy operatora, to osobne zdarzenie: dwa wcześniej niezależne zaplecza okazały się jednym.
    if joined_campaign and joined_operator and operator.get("operator_action") == "merged":
        op_members = list(OperatorMembership.objects.filter(operator_id=operator_id).exclude(ad=ad).values_list("ad_id", flat=True))
        alerts.append(
            _store(ad, Alert.Kind.JOINED_OPERATOR, f"Reklama połączyła grupy operatora {operator['operator']} ({operator['operator_size']} reklam)", op_members, campaign_id, operator_id)
        )
    return alerts


def _store(ad: Ad, kind: str, description: str, members: list[int], campaign_id: int | None, operator_id: int | None) -> Alert:
    alert, _ = Alert.objects.get_or_create(
        ad=ad,
        kind=kind,
        defaults={
            "campaign_id": campaign_id,
            "operator_id": operator_id,
            "description": description,
            "evidence": top_evidence(ad, members),
        },
    )
    return alert
