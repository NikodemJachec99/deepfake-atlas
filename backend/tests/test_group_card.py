"""Karta grupy: miniatury reklam i wkład śladów w bitach. Dane zmyślone."""

import pytest
from rest_framework.test import APIClient

from ads.models import Ad, Analysis
from evidence.models import AdMarker, Marker
from similarity.models import Campaign, CampaignMembership, Edge, EdgeEvidence, Operator, OperatorMembership

pytestmark = pytest.mark.django_db
SHA = "c" * 64
SHOT = "d" * 64


def marker(kind: str, value: str, ads: list[Ad]) -> None:
    m = Marker.objects.create(kind=kind, value=value, value_hash=Marker.hash_value(value), ad_count=len(ads))
    for ad in ads:
        AdMarker.objects.create(ad=ad, marker=m)


def link(a: Ad, b: Ad, bits: float, kind="domain", value="d.example", relation="same_campaign", verdict="") -> Edge:
    a, b = sorted((a, b), key=lambda x: x.pk)
    edge = Edge.objects.create(ad_a=a, ad_b=b, relation=relation, bits=bits, probability=0.95, model_version="t", verdict=verdict)
    EdgeEvidence.objects.create(edge=edge, kind=kind, family="infra", value_a=value, value_b=value, raw_bits=bits, weight_bits=bits)
    return edge


@pytest.fixture
def group():
    a = Ad.objects.create(source="capture", external_id="g/1", raw={"creatives": [SHA]})
    b = Ad.objects.create(source="capture", external_id="g/2")
    c = Ad.objects.create(source="capture", external_id="g/3")
    campaign, operator = Campaign.objects.create(), Operator.objects.create()
    for ad in (a, b, c):
        CampaignMembership.objects.create(ad=ad, campaign=campaign)
        OperatorMembership.objects.create(ad=ad, operator=operator)
    Analysis.objects.create(ad=b, input_kind="url", input_value="https://x.example", state={"pages": {"victim": {"screenshot_sha": SHOT}}})
    marker("domain", "d.example", [a, b, c])
    marker("kit_path", "/panel", [a, b])
    link(a, b, 10.0)
    link(b, c, 6.5)
    link(a, c, 5.0, verdict="rejected")  # odrzucona nie liczy się do wkładu
    return campaign, operator, (a, b, c)


def test_ads_have_thumbnail_from_creative_or_screenshot_or_null(group):
    campaign, _, (a, b, c) = group
    ads = {x["id"]: x for x in APIClient().get(f"/api/campaigns/{campaign.pk}").json()["ads"]}
    assert ads[a.pk]["thumbnail"] == {"sha256": SHA, "image": f"/api/artifacts/{SHA}/image"}
    assert ads[b.pk]["thumbnail"] == {"sha256": SHOT, "image": f"/api/artifacts/{SHOT}/image"}
    assert ads[c.pk]["thumbnail"] is None


def test_core_markers_have_bits_sum_and_edge_count(group):
    campaign, operator, _ = group
    for url in (f"/api/campaigns/{campaign.pk}", f"/api/operators/{operator.pk}"):
        core = {m["kind"]: m for m in APIClient().get(url).json()["core_markers"]}
        assert (core["domain"]["bits"], core["domain"]["edges"]) == (16.5, 2)
        assert core["domain"]["in_group"] == 3 and core["domain"]["ad_count"] == 3  # stare pola bez zmian
        assert (core["kit_path"]["bits"], core["kit_path"]["edges"]) == (None, 0)


def test_operator_card_counts_operator_edges_too(group):
    _, operator, (a, b, c) = group
    Edge.objects.filter(verdict="rejected").delete()
    link(a, c, 3.0, kind="kit_path", value="/panel", relation="same_operator")
    core = {m["kind"]: m for m in APIClient().get(f"/api/operators/{operator.pk}").json()["core_markers"]}
    assert (core["kit_path"]["bits"], core["kit_path"]["edges"]) == (3.0, 1)
    campaign_core = {m["kind"]: m for m in APIClient().get(f"/api/campaigns/{a.membership.campaign_id}").json()["core_markers"]}
    assert campaign_core["kit_path"]["bits"] is None  # relacja same_operator nie należy do karty kampanii


def test_query_count_does_not_grow(group, django_assert_max_num_queries):
    campaign, _, (a, b, c) = group
    for i in range(10):
        extra = Ad.objects.create(source="capture", external_id=f"g/x{i}")
        CampaignMembership.objects.create(ad=extra, campaign=campaign)
        link(a, extra, 2.0)
    with django_assert_max_num_queries(14):
        APIClient().get(f"/api/campaigns/{campaign.pk}")
