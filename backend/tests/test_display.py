import pytest
from rest_framework.test import APIClient

from ads.models import Ad
from evidence import services as markers
from extractors import Observation
from people.display import display_value
from people.models import Person
from similarity.fusion import Shared, score_pair
from similarity.models import Campaign, CampaignMembership
from similarity.service import _store_edge

pytestmark = pytest.mark.django_db


def test_person_markers_carry_the_name_everywhere():
    client = APIClient()
    person = Person.objects.create(name="Jan Testowy")
    value = person.marker_value
    a, b = Ad.objects.create(external_id="t/a"), Ad.objects.create(external_id="t/b")
    for ad in (a, b):
        markers.attach(ad, [Observation("face_match", value, {"name": "Jan Testowy", "score": 0.7}), Observation("domain", f"{ad.pk}.example")])
    edge = _store_edge(a.pk, b.pk, score_pair([Shared("face_match", value, df=2), Shared("funnel_id", "11111111-2222-4333-8444-555555555555", df=2)], [], 1000), {})
    campaign = Campaign.objects.create()
    for ad in (a, b):
        CampaignMembership.objects.create(ad=ad, campaign=campaign)

    genome = client.get(f"/api/ads/{a.pk}").json()["genome"]
    shown = {m["kind"]: m for family in genome for m in family["markers"]}
    assert shown["face_match"]["value"] == value and shown["face_match"]["display_value"] == "Jan Testowy"
    assert shown["domain"]["display_value"] == shown["domain"]["value"]

    evidence = {e["kind"]: e for e in client.get(f"/api/edges/{edge.pk}").json()["evidence"]}
    assert evidence["face_match"]["display_value"] == "Jan Testowy"

    core = {m["kind"]: m for m in client.get(f"/api/campaigns/{campaign.pk}").json()["core_markers"]}
    assert core["face_match"]["display_value"] == "Jan Testowy"

    sim = client.post(f"/api/edges/{edge.pk}/simulate", {"exclude": [evidence["face_match"]["id"]]}, format="json").json()
    assert sim["excluded"][0]["display_value"] == "Jan Testowy"


def test_unknown_person_value_stays_as_is():
    assert display_value("person_mention", "person:999999") == "person:999999"
    assert display_value("domain", "person:1") == "person:1"
