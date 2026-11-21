"""Pamięć sprzeciwu: podobne wcześniejsze rozstrzygnięcia. Pary i ślady zmyślone."""

import itertools

import pytest
from rest_framework.test import APIClient

from ads.models import Ad
from evidence.kinds import KINDS
from similarity import decisions, precedents
from similarity.models import Edge, EdgeDecision, EdgeEvidence

pytestmark = pytest.mark.django_db
_ids = itertools.count(1)
META_TOKEN = "EAAB" + "q9" * 20


def make_edge(kinds: list[str], relation: str = "same_operator") -> Edge:
    a = Ad.objects.create(source="capture", external_id=f"t/{next(_ids)}")
    b = Ad.objects.create(source="capture", external_id=f"t/{next(_ids)}")
    edge = Edge.objects.create(ad_a=a, ad_b=b, relation=relation, bits=20, probability=0.99, model_version="fs-5")
    for kind in kinds:
        EdgeEvidence.objects.create(edge=edge, family=KINDS[kind].family, kind=kind, value_a="v", value_b="v", raw_bits=4, weight_bits=4)
    return edge


def find(edge: Edge, **params) -> dict:
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return APIClient().get(f"/api/edges/{edge.pk}/precedents?{query}").json()


ENGINE_AND_ACCOUNT = ["kit_path", "url_param_keys", "funnel_id", "meta_pixel"]


def test_similar_case_is_found_with_reasons():
    old = make_edge(ENGINE_AND_ACCOUNT)
    decisions.decide(old.pk, "rejected", "shared_tool", "ten sam silnik, różne konta")
    current = make_edge(ENGINE_AND_ACCOUNT)
    body = find(current)
    assert body["status"] == "found" and body["notice"]
    [p] = body["precedents"]
    assert (p["verdict"], p["reason"], p["reason_known"], p["similarity"], p["same_relation"]) == ("rejected", "shared_tool", True, 1.0, True)
    assert {g["group"] for g in p["shared_groups"]} == {"kit", "kind:funnel_id", "kind:meta_pixel"}
    assert p["new_independent"] == [] and p["differences"] == []
    assert p["why"][0].startswith("Wspólne grupy śladów")


def test_apparently_similar_case_shows_new_independent_evidence():
    old = make_edge(["kit_path", "person_mention"])
    decisions.decide(old.pk, "rejected", "shared_tool")
    current = make_edge(["kit_path", "url_param_keys", "funnel_id"])
    [p] = find(current)["precedents"]
    assert [g["group"] for g in p["new_independent"]] == ["kind:funnel_id"]
    assert any("niezależne ślady" in d for d in p["differences"])
    assert any("Precedens miał ślady" in d for d in p["differences"])  # osoba była tylko wtedy


def test_motif_only_overlap_is_not_a_precedent():
    old = make_edge(["person_mention", "brand_impersonated"], relation="similar")
    decisions.decide(old.pk, "rejected", "no_independent_confirmation")
    current = make_edge(["person_mention", "funnel_id"])
    body = find(current)
    assert body["status"] == "none" and body["precedents"] == [] and body["matching"] == 0


def test_conflicting_precedents_are_flagged():
    for verdict, reason in (("rejected", "shared_tool"), ("confirmed", "confirmed_by_analyst")):
        decisions.decide(make_edge(ENGINE_AND_ACCOUNT).pk, verdict, reason)
    body = find(make_edge(ENGINE_AND_ACCOUNT))
    assert body["conflict"] is True
    assert {p["verdict"] for p in body["precedents"]} == {"rejected", "confirmed"}


def test_incomplete_decisions_are_not_presented_as_justified():
    legacy = make_edge(ENGINE_AND_ACCOUNT)
    EdgeDecision.objects.create(edge=legacy, ad_a=legacy.ad_a, ad_b=legacy.ad_b, verdict="rejected", reason="unknown",
                                legacy=True, created_at=legacy.created_at)
    no_reason = make_edge(ENGINE_AND_ACCOUNT)
    decisions.decide(no_reason.pk, "rejected")
    body = find(make_edge(ENGINE_AND_ACCOUNT))
    assert body["skipped_without_snapshot"] == 1
    [p] = body["precedents"]
    assert p["edge"] == no_reason.pk and p["reason_known"] is False
    assert any("nie ma podanego powodu" in d for d in p["differences"])


def test_only_latest_decision_per_pair_and_not_own_pair():
    old = make_edge(ENGINE_AND_ACCOUNT)
    decisions.decide(old.pk, "rejected", "shared_tool")
    decisions.decide(old.pk, "confirmed", "confirmed_by_analyst")
    current = make_edge(ENGINE_AND_ACCOUNT)
    decisions.decide(current.pk, "unsure", "other")  # własna historia to nie precedens
    body = find(current)
    assert [(p["edge"], p["verdict"]) for p in body["precedents"]] == [(old.pk, "confirmed")]
    assert body["considered"] == 1


def test_recomputed_evidence_gives_the_same_precedents():
    decisions.decide(make_edge(ENGINE_AND_ACCOUNT).pk, "rejected", "shared_tool")
    current = make_edge(ENGINE_AND_ACCOUNT)
    before = precedents.find(current)
    # przeliczenie: te same rodzaje śladów, nowe wiersze dowodów
    rows = list(current.evidence.values("family", "kind", "value_a", "value_b", "raw_bits", "weight_bits"))
    current.evidence.all().delete()
    EdgeEvidence.objects.bulk_create([EdgeEvidence(edge=current, **row) for row in rows])
    after = precedents.find(current)
    assert after["precedents"] == before["precedents"]


def test_limit_and_ordering():
    made = []
    for extra in (["meta_pixel"], [], ["meta_pixel", "ga4"], ["ga4"], [], ["meta_pixel"], []):
        edge = make_edge(["kit_path", "funnel_id", *extra])
        decisions.decide(edge.pk, "rejected", "shared_tool")
        made.append(edge.pk)
    current = make_edge(["kit_path", "funnel_id", "meta_pixel"])
    body = find(current, limit=3)
    assert body["limit"] == 3 and body["matching"] == 7 and len(body["precedents"]) == 3
    scores = [p["similarity"] for p in body["precedents"]]
    assert scores == sorted(scores, reverse=True) and scores[0] == 1.0
    # przy równym podobieństwie nowsza decyzja pierwsza
    assert [p["edge"] for p in body["precedents"][:2]] == [made[5], made[0]]
    assert find(current, limit=500)["limit"] == precedents.MAX_LIMIT
    assert APIClient().get(f"/api/edges/{current.pk}/precedents?limit=dużo").status_code == 400


def test_notes_are_only_the_redacted_ones():
    old = make_edge(ENGINE_AND_ACCOUNT)
    decisions.decide(old.pk, "rejected", "other", f"token {META_TOKEN} z reklamy")
    raw = str(find(make_edge(ENGINE_AND_ACCOUNT)))
    assert META_TOKEN not in raw and "sha256-" in raw


def test_no_side_effects():
    old = make_edge(ENGINE_AND_ACCOUNT)
    decisions.decide(old.pk, "rejected", "shared_tool")
    current = make_edge(ENGINE_AND_ACCOUNT)
    state = lambda: (  # noqa: E731
        list(Edge.objects.order_by("pk").values_list("pk", "relation", "bits", "verdict", "updated_at")),
        EdgeDecision.objects.count(), EdgeEvidence.objects.count(),
    )
    before = state()
    find(current)
    assert state() == before


def test_missing_edge_is_404():
    assert APIClient().get("/api/edges/999999/precedents").status_code == 404
