"""Zakwestionowanie przesłanki: podgląd, zapis, przywrócenie. Dane zmyślone, markery zakładane wprost."""

import pytest
from rest_framework.test import APIClient

from ads.models import Ad
from evidence import services as markers
from evidence.models import AuditLog
from extractors import Observation
from similarity import service
from similarity.models import CampaignMembership, Edge, EdgeEvidence, OperatorMembership, Premise

pytestmark = pytest.mark.django_db

X = "G-AAAAAAAAAA"
Y = "G-BBBBBBBBBB"
P = "111111111111111"


@pytest.fixture
def client():
    return APIClient()


def make_ad(n: int, *obs) -> Ad:
    ad = Ad.objects.create(source="manual", external_id=f"p{n}")
    markers.attach(ad, [Observation(kind, value) for kind, value in obs])
    return ad


def build(*ads):
    for ad in ads:
        service.link_ad(ad)
    for ad in ads:
        service.assign_campaign(ad)
        service.assign_operator(ad)


def memberships():
    return (
        sorted(CampaignMembership.objects.values_list("ad_id", "campaign_id")),
        sorted(OperatorMembership.objects.values_list("ad_id", "operator_id")),
    )


def operator_of(ad):
    m = OperatorMembership.objects.filter(ad=ad).first()
    return m.operator_id if m else None


def bridge():
    """A-B łączy ślad X, B-C ślad Y."""
    a = make_ad(1, ("ga4", X))
    b = make_ad(2, ("ga4", X), ("ga4", Y))
    c = make_ad(3, ("ga4", Y))
    build(a, b, c)
    assert Edge.objects.count() == 2
    assert operator_of(a) == operator_of(b) == operator_of(c) is not None
    return a, b, c


def state_snapshot():
    return (
        list(Edge.objects.order_by("pk").values_list("pk", "relation", "bits", "verdict")),
        EdgeEvidence.objects.count(),
        memberships(),
        Premise.objects.count(),
        AuditLog.objects.count(),
    )


def challenge(client, value, reason="test", kind="ga4"):
    return client.post("/api/premises", {"kind": kind, "value": value, "reason": reason}, format="json")


def test_bridge_premise_splits_group(client):
    a, b, c = bridge()
    resp = challenge(client, Y, "wspólny usługodawca analityki")
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "challenged"
    assert Edge.objects.count() == 1
    assert operator_of(a) == operator_of(b) is not None
    assert operator_of(c) is None
    assert CampaignMembership.objects.filter(ad=c).count() == 0
    [change] = body["regroup"]["operator"]
    assert change["released"] == [c.pk] and change["before"] == [a.pk, b.pk, c.pk]
    assert [p["ads"] for p in change["after"]] == [[a.pk, b.pk]]
    assert body["before"]["groups"]["operator"][0]["ads"] == [a.pk, b.pk, c.pk]
    assert body["after"]["groups"]["operator"][0]["ads"] == [a.pk, b.pk]
    assert AuditLog.objects.filter(action="premise.challenge").count() == 1


def test_premise_is_skipped_for_new_ads(client):
    bridge()
    challenge(client, Y)
    d = make_ad(4, ("ga4", Y))
    assert all(not pair.shared for pair in service.pair_inputs(d))
    build(d)
    assert not Edge.objects.filter(ad_a=d).exists() and not Edge.objects.filter(ad_b=d).exists()
    assert operator_of(d) is None


def test_group_backed_by_independent_evidence_stays(client):
    a = make_ad(1, ("ga4", X), ("meta_pixel", P))
    b = make_ad(2, ("ga4", X), ("meta_pixel", P))
    build(a, b)
    before = operator_of(a)
    assert before is not None
    prev = client.post("/api/premises/preview", {"kind": "ga4", "value": X}, format="json").json()
    assert prev["split_count"] == 0
    [stay] = prev["groups"]["operator"]["stay"]
    assert stay["before"] == [a.pk, b.pk]
    assert stay["supported_by"][0]["kind"] == "meta_pixel"
    challenge(client, X)
    assert operator_of(a) == operator_of(b) == before
    edge = Edge.objects.get()
    assert not edge.evidence.filter(kind="ga4").exists()
    assert edge.evidence.filter(kind="meta_pixel").exists()


def test_restore_brings_state_back(client):
    a, b, c = bridge()
    start = memberships()
    start_edges = list(Edge.objects.order_by("pk").values_list("ad_a_id", "ad_b_id", "relation"))
    pid = challenge(client, Y).json()["id"]
    assert memberships() != start
    resp = client.post(f"/api/premises/{pid}/restore")
    assert resp.status_code == 200 and resp.json()["status"] == "restored"
    assert memberships() == start
    assert list(Edge.objects.order_by("pk").values_list("ad_a_id", "ad_b_id", "relation")) == start_edges
    assert Premise.objects.get(pk=pid).restored_at is not None
    # po przywróceniu ślad znów buduje dowody dla nowych reklam
    d = make_ad(4, ("ga4", Y))
    assert any(sh.value == Y for pair in service.pair_inputs(d) for sh in pair.shared)
    assert client.post(f"/api/premises/{pid}/restore").status_code == 409
    # można go zakwestionować jeszcze raz, historia ma dwa wpisy
    assert challenge(client, Y, "znowu").status_code == 201
    assert [p["status"] for p in client.get("/api/premises").json()["results"]] == ["challenged", "restored"]


def test_preview_writes_nothing(client):
    a, b, c = bridge()
    snap = state_snapshot()
    resp = client.post("/api/premises/preview", {"kind": "ga4", "value": Y}, format="json")
    assert resp.status_code == 200
    body = resp.json()
    assert body["edge_count"] == 1
    [edge] = body["edges"]
    assert edge["removed"] is True and edge["before"]["relation"] and edge["after"]["relation"] is None
    [split] = body["groups"]["operator"]["split"]
    assert split["before"] == [a.pk, b.pk, c.pk]
    assert [p["ads"] for p in split["after"]] == [[a.pk, b.pk]]
    assert split["released"] == [c.pk]
    assert body["split_count"] >= 1
    assert state_snapshot() == snap


def test_preview_matches_what_challenge_does(client):
    bridge()
    prev = client.post("/api/premises/preview", {"kind": "ga4", "value": Y}, format="json").json()
    body = challenge(client, Y).json()
    predicted = [p["ads"] for s in prev["groups"]["operator"]["split"] for p in s["after"]]
    actual = [g["ads"] for g in body["after"]["groups"]["operator"]]
    assert predicted == actual


def test_validation_errors(client):
    bridge()
    assert client.post("/api/premises/preview", {"kind": "text_minhash", "value": "x"}, format="json").status_code == 400
    assert challenge(client, "x", kind="text_minhash").status_code == 400
    assert client.post("/api/premises/preview", {"kind": "nie_ma_takiego", "value": "x"}, format="json").status_code == 400
    assert client.post("/api/premises/preview", {"kind": "ga4", "value": "G-NIEMA"}, format="json").status_code == 404
    assert client.post("/api/premises", {"kind": "ga4", "value": Y}, format="json").status_code == 400  # brak powodu
    assert Premise.objects.count() == 0


def test_duplicate_challenge_is_409(client):
    bridge()
    assert challenge(client, Y, "a").status_code == 201
    assert challenge(client, Y, "b").status_code == 409
    assert Premise.objects.count() == 1


def test_history_and_detail(client):
    bridge()
    pid = challenge(client, Y).json()["id"]
    listing = client.get("/api/premises").json()
    assert listing["count"] == 1 and "before" not in listing["results"][0]
    detail = client.get(f"/api/premises/{pid}").json()
    assert detail["before"]["groups"] and detail["after"]["groups"] and detail["restored_state"] is None
    assert client.get("/api/premises/9999").status_code == 404


def test_verdict_edge_survives_challenge(client):
    a, b, c = bridge()
    Edge.objects.filter(ad_a=b, ad_b=c).update(verdict=Edge.Verdict.CONFIRMED)
    prev = client.post("/api/premises/preview", {"kind": "ga4", "value": Y}, format="json").json()
    assert prev["edges"][0]["after"]["kept_by_verdict"] is True and prev["split_count"] == 0
    challenge(client, Y)
    assert Edge.objects.count() == 2
    assert operator_of(c) == operator_of(a)


def test_link_ad_reports_removed_neighbours():
    a = make_ad(1, ("ga4", X))
    b = make_ad(2, ("ga4", X))
    build(a, b)
    Premise.objects.create(kind="ga4", value=X, reason="t")
    edges, removed = service.link_ad_detailed(b)
    assert edges == [] and removed == [a.pk]


def test_pipeline_cluster_releases_ad_after_edge_removed():
    from ads.models import Analysis
    from workflows import pipeline

    a, b, c = bridge()
    Premise.objects.create(kind="ga4", value=Y, reason="t")
    analysis = Analysis.objects.create(input_kind="text", input_value="x", ad=c)
    analysis.result = {"fuse": pipeline.stage_fuse(analysis)}
    assert analysis.result["fuse"]["removed"] == [b.pk]
    pipeline.stage_cluster(analysis)
    assert operator_of(c) is None and operator_of(a) == operator_of(b) is not None
