import itertools

import pytest
from rest_framework.test import APIClient

from similarity import weakest
from similarity.fusion import Shared, Soft
from similarity.models import Edge, EdgeEvidence
from tests.test_simulation import ENGINE, FUNNEL, PIXEL, ad, edge, snapshot

pytestmark = pytest.mark.django_db
ASSET = Shared("asset_host", "zasoby-operatora.example", df=2)
GADS = Shared("google_ads", "18463917747", df=2)


@pytest.fixture
def client():
    return APIClient()


def run(client, e: Edge, **params):
    response = client.post(f"/api/edges/{e.pk}/weakest-link", params, format="json")
    assert response.status_code == 200, response.content
    return response.json()


def test_one_group_changes_the_relation(client):
    e = edge(ad("a"), ad("b"), [*ENGINE, ASSET])
    body = run(client, e)
    assert body["minimal_size"] == 1 and body["searched"]["complete"]
    assert sorted(s["groups"][0] for s in body["solutions"]) == ["kind:asset_host", "kit"]
    assert all(s["simulated"]["relation"] != "same_operator" for s in body["solutions"])


def test_only_a_pair_changes_the_relation(client):
    # Dwa niezależne rozstrzygające ślady: żaden z osobna nie wystarcza do zmiany, dopiero oba razem.
    e = edge(ad("a"), ad("b"), [FUNNEL, PIXEL, *ENGINE])
    body = run(client, e)
    assert body["minimal_size"] == 2
    assert [s["groups"] for s in body["solutions"]] == [["kind:funnel_id", "kind:meta_pixel"]]
    assert "2 grupy" in body["message"]


def test_several_equivalent_solutions_are_all_listed_in_a_fixed_order(client):
    e = edge(ad("a"), ad("b"), [FUNNEL, PIXEL, GADS, *ENGINE])
    first, second = run(client, e), run(client, e)
    assert first["solutions"] == second["solutions"]
    assert first["minimal_size"] is None or first["minimal_size"] >= 2
    sizes = [len(s["groups"]) for s in first["solutions"]]
    assert sizes == sorted(sizes)


def test_dependent_traces_form_one_group(client):
    e = edge(ad("a"), ad("b"), [*ENGINE, ASSET])
    groups = {g["id"]: g for g in run(client, e)["groups"]}
    kit_kinds = set(EdgeEvidence.objects.filter(pk__in=groups["kit"]["evidence_ids"]).values_list("kind", flat=True))
    assert kit_kinds == {"kit_path", "url_param_keys"}
    assert weakest.group_of("person_mention") == weakest.group_of("brand_impersonated") == "motif"
    assert weakest.group_of("ip") == weakest.group_of("tls_serial") == "infra"
    assert weakest.group_of("nie-ma-takiego") == "unknown:nie-ma-takiego"


def test_no_solution_within_the_searched_scenarios(client):
    e = edge(ad("a"), ad("b"), [FUNNEL, PIXEL, GADS, Shared("gtm", "GTM-TEST01", df=2)])
    body = run(client, e, max_group_size=1)
    assert body["solutions"] == [] and body["searched"]["complete"]
    assert body["message"].startswith("Nie znaleziono w sprawdzonych scenariuszach")


def test_no_evidence_and_already_unlinked(client):
    e = edge(ad("a"), ad("b"), [FUNNEL])
    EdgeEvidence.objects.filter(edge=e).delete()
    assert "nie ma zapisanych dowodów" in run(client, e)["message"]
    weak = edge(ad("c"), ad("d"), [Shared("brand_impersonated", "Marka", df=2), Shared("person_mention", "Q1", df=2), Shared("topic", "zdrowie", df=2)])
    EdgeEvidence.objects.filter(edge=weak, kind="person_mention").delete()
    assert "nie są połączone" in run(client, weak)["message"]


def test_scenario_limit_marks_the_search_incomplete(client):
    e = edge(ad("a"), ad("b"), [FUNNEL, PIXEL, *ENGINE])
    body = run(client, e, max_scenarios=2)
    assert body["searched"]["complete"] is False and "limit 2 scenariuszy" in body["searched"]["stopped_reason"]
    assert body["minimal_size"] is None and "niepełne" in body["message"]


def test_time_limit_marks_the_search_incomplete():
    e = edge(ad("a"), ad("b"), [FUNNEL, PIXEL, *ENGINE])
    ticks = itertools.count(step=1.0)  # każde wywołanie zegara to sekunda
    body = weakest.weakest_link(e, time_limit_ms=1500, clock=lambda: next(ticks))
    assert body["searched"]["complete"] is False and "limit czasu" in body["searched"]["stopped_reason"]


def test_solutions_match_manual_simulation(client):
    e = edge(ad("a"), ad("b"), [*ENGINE, ASSET])
    for solution in run(client, e)["solutions"]:
        manual = client.post(f"/api/edges/{e.pk}/simulate", {"exclude": solution["excluded_evidence"]}, format="json").json()
        assert manual["simulated"] == solution["simulated"]


def test_large_edge_respects_the_limits(client):
    shared = [Shared("kit_path", f"GET /zasob-{i}.js", df=2) for i in range(5)]
    shared += [Shared("funnel_param", f"klucz-{i}", df=2) for i in range(1)]
    shared += [FUNNEL, PIXEL, GADS, ASSET, Shared("gtm", "GTM-TEST01", df=2), Shared("ga4", "G-TEST000001", df=2)]
    shared += [Shared("phone", "+48 500 000 000", df=2), Shared("email", "kontakt@przyklad.example", df=2)]
    e = edge(ad("a"), ad("b"), shared, [Soft("page_text_minhash", 0.95), Soft("image_set", 0.9)])
    body = run(client, e, max_scenarios=1000, time_limit_ms=5000)
    assert len(body["groups"]) >= 10
    assert body["searched"]["scenarios_checked"] <= 1000


def test_no_side_effects_and_stale_version(client):
    e = edge(ad("a"), ad("b"), [*ENGINE, ASSET])
    before = snapshot()
    run(client, e)
    assert snapshot() == before
    stale = client.post(f"/api/edges/{e.pk}/weakest-link", {"edge_version": "2000-01-01T00:00:00+00:00"}, format="json")
    assert stale.status_code == 409
