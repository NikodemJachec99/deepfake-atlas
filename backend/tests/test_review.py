"""Kolejka "Do oceny": powody, filtry, stronicowanie, redakcja, stats. Dane zmyślone."""

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from ads.models import Ad
from similarity.models import Alert, Campaign, CampaignMembership, Edge, EdgeDecision, EdgeEvidence, Premise

pytestmark = pytest.mark.django_db

BACKED = [("domain", "infra", 18, True, 1), ("kit_path", "tmpl", 8, False, 1)]
CONCEPT = [("page_text_minhash", "narr", 9, False, 1)]
TOKEN = "EAAB" + "x7" * 20


def ad(source: str = "capture", **fields) -> Ad:
    return Ad.objects.create(source=source, external_id=f"{source}/{Ad.objects.count()}", title="Reklama", landing_url="https://scam.example/p", **fields)


def edge(a: Ad, b: Ad, relation="same_operator", probability=0.95, evidence=BACKED, **fields) -> Edge:
    a, b = sorted((a, b), key=lambda x: x.pk)
    created = Edge.objects.create(ad_a=a, ad_b=b, relation=relation, bits=20, probability=probability, model_version="fs-test", **fields)
    for kind, family, bits, decisive, df in evidence:
        EdgeEvidence.objects.create(edge=created, kind=kind, family=family, value_a=f"{kind}-a", value_b=f"{kind}-b", df=df, raw_bits=bits, weight_bits=bits, decisive=decisive)
    return created


def pair(**kw) -> Edge:
    return edge(ad(), ad(), **kw)


def get(query: str = ""):
    return APIClient().get(f"/api/review{query}")


def reasons() -> dict[int, str]:
    return {r["id"]: r["reason"] for r in get().json()["results"]}


def test_challenged_premise_trace_takes_priority():
    hit = pair(evidence=[*BACKED, ("ip", "infra", 3, False, 2)], probability=0.6)
    EdgeEvidence.objects.filter(edge=hit, kind="ip").update(value_a="203.0.113.5")
    other = pair(evidence=[*BACKED, ("ip", "infra", 3, False, 2)])
    EdgeEvidence.objects.filter(edge=other, kind="ip").update(value_a="203.0.113.6", value_b="203.0.113.6")
    Premise.objects.create(kind="ip", value="203.0.113.5", reason="wspólny hosting")
    restored = Premise.objects.create(kind="ip", value="203.0.113.6", reason="x", status="restored")
    assert restored.status == "restored"
    got = reasons()
    assert got[hit.pk] == "challenged" and got[other.pk] == "other"
    first = get().json()["results"][0]
    assert first["id"] == hit.pk and first["reason_label"].startswith("Krawędź używa śladu")
    assert [r["id"] for r in get("?reason=challenged").json()["results"]] == [hit.pk]


def test_unbacked_without_infrastructure_and_single_decisive():
    concept_only = pair(evidence=CONCEPT)
    single = pair(evidence=[("domain", "infra", 18, True, 1)])
    fine = pair()
    got = reasons()
    assert got[concept_only.pk] == "unbacked" and got[single.pk] == "unbacked"
    assert got[fine.pk] == "other"
    item = next(r for r in get().json()["results"] if r["id"] == concept_only.pk)
    assert "brak śladu zaplecza" in item["limitations"]
    assert "kopia treści bez wspólnej infrastruktury" in item["limitations"]
    assert item["reason_label"].startswith("Relacja bez śladu zaplecza")
    assert any("jeden decydujący" in s for s in next(r for r in get().json()["results"] if r["id"] == single.pk)["limitations"])


def test_similar_relation_is_not_unbacked_and_borderline_score():
    similar = pair(relation="similar", probability=0.7, evidence=CONCEPT)
    sure = pair(relation="similar", probability=0.95, evidence=CONCEPT)
    got = reasons()
    assert got[similar.pk] == "borderline" and got[sure.pk] == "other"


def test_changed_after_decision_in_group():
    campaign = Campaign.objects.create()
    a, b, c = ad(), ad(), ad()
    for member in (a, b, c):
        CampaignMembership.objects.create(ad=member, campaign=campaign)
    decided = edge(a, b, verdict="confirmed")
    EdgeDecision.objects.create(edge=decided, ad_a=a, ad_b=b, verdict="confirmed", created_at=timezone.now() - timedelta(days=1))
    changed = edge(b, c)
    outside = pair()
    got = reasons()
    assert got[changed.pk] == "changed_after_decision"
    assert got[outside.pk] == "other"
    assert decided.pk not in got  # krawędź z werdyktem nie wchodzi do kolejki
    # decyzja późniejsza niż zmiana krawędzi zdejmuje powód
    EdgeDecision.objects.create(edge=decided, ad_a=a, ad_b=b, verdict="confirmed", created_at=timezone.now() + timedelta(hours=1))
    assert reasons()[changed.pk] == "other"


def test_new_in_group_needs_joined_alert_and_no_decision_on_its_edges():
    new, old = ad(), ad()
    Alert.objects.create(ad=new, kind="joined_campaign")
    flagged = edge(new, old)
    # reklama z alertem, ale z już ocenioną krawędzią
    other_new, other_old, third = ad(), ad(), ad()
    Alert.objects.create(ad=other_new, kind="joined_operator")
    edge(other_new, third, verdict="rejected")
    handled = edge(other_new, other_old)
    # alert łowcy nie jest alertem reklamy
    hunt_ad = ad()
    Alert.objects.create(ad=hunt_ad, kind="hunt_confirmed")
    hunted = edge(hunt_ad, ad())
    got = reasons()
    assert got[flagged.pk] == "new_in_group"
    assert got[handled.pk] == "other" and got[hunted.pk] == "other"


def test_order_is_priority_then_probability():
    other_high = pair(probability=0.99)
    borderline = pair(probability=0.6, relation="similar", evidence=CONCEPT)
    unbacked_low = pair(probability=0.8, evidence=CONCEPT)
    unbacked_high = pair(probability=0.97, evidence=CONCEPT)
    ids = [r["id"] for r in get().json()["results"]]
    assert ids == [unbacked_high.pk, unbacked_low.pk, borderline.pk, other_high.pk]


def test_source_default_capture_and_all():
    capture = pair()
    library = edge(ad("microsoft"), ad("microsoft"))
    mixed = edge(ad("capture"), ad("microsoft"))
    assert [r["id"] for r in get().json()["results"]] == [capture.pk]
    assert {r["id"] for r in get("?source=all").json()["results"]} == {capture.pk, library.pk, mixed.pk}
    assert [r["id"] for r in get("?source=microsoft").json()["results"]] == [library.pk]


def test_relation_and_reason_filters_and_validation():
    op = pair()
    sim = pair(relation="similar", probability=0.7, evidence=CONCEPT)
    assert [r["id"] for r in get("?relation=similar").json()["results"]] == [sim.pk]
    assert [r["id"] for r in get("?reason=other").json()["results"]] == [op.pk]
    assert [r["id"] for r in get("?reason=borderline&relation=same_operator").json()["results"]] == []
    assert get("?reason=zly").status_code == 400
    assert get("?relation=zly").status_code == 400


def test_pagination():
    for _ in range(53):
        pair()
    first = get().json()
    assert first["count"] == 53 and len(first["results"]) == 50 and first["next"]
    assert len(get("?page=2").json()["results"]) == 3


def test_item_shape_thumbnail_top_evidence_and_redaction():
    a = ad(raw={"creatives": ["a" * 64]}, first_seen=timezone.now())
    b = Ad.objects.create(source="capture", external_id="capture/x", landing_url=f"https://redirect.example/go?access_token={TOKEN}&x=1")
    e = edge(a, b, evidence=[*BACKED, ("ip", "infra", 3, False, 9), ("asn", "infra", 1, False, 1)])
    EdgeEvidence.objects.filter(edge=e, kind="ip").update(value_a=f"https://t.example/?access_token={TOKEN}")
    body = get().json()["results"][0]
    assert body["id"] == e.pk and body["model_version"] == "fs-test" and body["bits"] == 20
    assert body["ad_a"]["thumbnail"] == {"sha256": "a" * 64, "image": f"/api/artifacts/{'a' * 64}/image"}
    assert body["ad_b"]["thumbnail"] is None and body["ad_b"]["domain"] == "redirect.example"
    assert [x["kind"] for x in body["evidence"]] == ["domain", "kit_path", "ip"]
    assert any("współdzielony przez 9 reklam" in s for s in body["limitations"])
    ip = body["evidence"][2]
    assert TOKEN not in str(body) and "sha256-" in ip["value"]
    assert set(ip) >= {"kind", "label", "family", "weight_bits", "value", "artifact_a", "artifact_b"}


def test_stats_verdicts_and_review_pending():
    pair()
    pair()
    edge(ad("microsoft"), ad("microsoft"))
    edge(ad(), ad(), verdict="confirmed")
    edge(ad(), ad(), verdict="unsure")
    body = APIClient().get("/api/stats").json()
    assert body["verdicts"] == {"none": 3, "confirmed": 1, "rejected": 0, "unsure": 1}
    assert body["review_pending"] == 2


def test_query_count_does_not_grow(django_assert_max_num_queries):
    for _ in range(20):
        pair()
    with django_assert_max_num_queries(16):
        get()
