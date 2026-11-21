"""Rozdzielanie grup po decyzji analityka. Dane zmyślone, krawędzie zakładane wprost."""

import pytest
from django.core.management import call_command
from rest_framework.test import APIClient

from ads.models import Ad
from evidence.models import AuditLog
from similarity import decisions, service
from similarity.models import Alert, Campaign, CampaignMembership, Edge, OperatorMembership

pytestmark = pytest.mark.django_db


def make_ads(n):
    return [Ad.objects.create() for _ in range(n)]


def link(a, b, relation=Edge.Relation.SAME_CAMPAIGN):
    a, b = sorted([a, b], key=lambda ad: ad.pk)
    return Edge.objects.create(ad_a=a, ad_b=b, relation=relation, bits=20.0, probability=0.99, model_version="t")


def group_all(*ads):
    for ad in ads:
        service.assign_campaign(ad)
        service.assign_operator(ad)


def campaign_of(ad):
    m = CampaignMembership.objects.filter(ad=ad).first()
    return m.campaign_id if m else None


def operator_of(ad):
    m = OperatorMembership.objects.filter(ad=ad).first()
    return m.operator_id if m else None


def chain():
    a, b, c = make_ads(3)
    link(a, b)
    bc = link(b, c)
    group_all(a, b, c)
    assert campaign_of(a) == campaign_of(b) == campaign_of(c)
    return a, b, c, bc


def test_rejecting_only_bridge_splits_group():
    a, b, c, bc = chain()
    key = Campaign.objects.get().key
    decision = decisions.decide(bc.pk, "rejected", "shared_tool")
    assert campaign_of(a) == campaign_of(b) is not None
    assert campaign_of(c) is None
    assert operator_of(a) == operator_of(b) and operator_of(c) is None
    [change] = decision.regroup["campaign"]
    assert change["group"] == key and change["released"] == [c.pk]
    assert [p["ads"] for p in change["after"]] == [[a.pk, b.pk]]
    log = AuditLog.objects.get(action="groups.recluster")
    assert log.payload["campaign"][0]["before"] == [a.pk, b.pk, c.pk]


def test_second_path_keeps_group():
    a, b, c, bc = chain()
    link(a, c)
    decision = decisions.decide(bc.pk, "rejected", "shared_tool")
    assert campaign_of(a) == campaign_of(b) == campaign_of(c)
    assert decision.regroup == {"campaign": [], "operator": []}
    assert not AuditLog.objects.filter(action="groups.recluster").exists()


def test_undoing_rejection_merges_back():
    a, b, c, bc = chain()
    decisions.decide(bc.pk, "rejected", "shared_tool")
    assert campaign_of(c) is None
    decisions.decide(bc.pk, "confirmed", "confirmed_by_analyst")
    assert campaign_of(a) == campaign_of(b) == campaign_of(c)
    assert operator_of(a) == operator_of(c)


def test_bigger_part_keeps_key_and_smaller_gets_new_group():
    ads = make_ads(5)
    for x, y in zip(ads, ads[1:], strict=False):
        link(x, y)
    bridge = Edge.objects.get(ad_a=ads[2], ad_b=ads[3])
    group_all(*ads)
    key = campaign_of(ads[0])
    decisions.decide(bridge.pk, "rejected", "shared_tool")
    assert campaign_of(ads[0]) == campaign_of(ads[1]) == campaign_of(ads[2]) == key
    assert campaign_of(ads[3]) == campaign_of(ads[4]) != key
    assert Campaign.objects.count() == 2


def test_tie_goes_to_smallest_ad_id():
    ads = make_ads(4)
    link(ads[0], ads[1])
    bridge = link(ads[1], ads[2])
    link(ads[2], ads[3])
    group_all(*ads)
    key = campaign_of(ads[0])
    decisions.decide(bridge.pk, "rejected", "shared_tool")
    assert campaign_of(ads[0]) == key and campaign_of(ads[2]) != key and campaign_of(ads[2]) is not None


def test_operator_splits_separately_from_campaign():
    a, b, c = make_ads(3)
    link(a, b)
    bridge = link(b, c, Edge.Relation.SAME_OPERATOR)
    group_all(a, b, c)
    assert campaign_of(c) is None or campaign_of(c) != campaign_of(a)
    assert operator_of(a) == operator_of(b) == operator_of(c)
    decisions.decide(bridge.pk, "rejected", "shared_tool")
    assert operator_of(c) is None and operator_of(a) == operator_of(b)


def test_merged_group_is_ignored_and_recluster_creates_no_alerts():
    a, b, c, bc = chain()
    old = Campaign.objects.create(merged_into=Campaign.objects.get())
    before = Alert.objects.count()
    service.recluster([a.pk, b.pk, c.pk])
    assert Alert.objects.count() == before
    assert not CampaignMembership.objects.filter(campaign=old).exists()


def test_recluster_all_command_splits_stale_group():
    a, b, c, bc = chain()
    Edge.objects.filter(pk=bc.pk).update(verdict="rejected")  # decyzja sprzed silnika
    call_command("recluster_all")
    assert campaign_of(c) is None and campaign_of(a) == campaign_of(b)


def test_stale_edge_version_gets_409():
    a, b, c, bc = chain()
    stale = bc.updated_at.isoformat()
    Edge.objects.filter(pk=bc.pk).update(bits=1.0)
    Edge.objects.get(pk=bc.pk).save()  # nowa wersja
    client = APIClient()
    r = client.post(f"/api/edges/{bc.pk}/verdict", {"verdict": "rejected", "reason": "shared_tool", "edge_version": stale}, format="json")
    assert r.status_code == 409
    assert campaign_of(c) == campaign_of(a)
    bc.refresh_from_db()
    ok = client.post(f"/api/edges/{bc.pk}/verdict", {"verdict": "rejected", "reason": "shared_tool", "edge_version": bc.updated_at.isoformat()}, format="json")
    assert ok.status_code == 200 and ok.json()["regroup"]["campaign"][0]["released"] == [c.pk]


def test_ad_recluster_endpoint_returns_regroup():
    a, b, c, bc = chain()
    Edge.objects.filter(pk=bc.pk).update(verdict="rejected")
    r = APIClient().post(f"/api/ads/{c.pk}/recluster")
    assert r.status_code == 200 and r.json()["regroup"]["campaign"][0]["released"] == [c.pk]
