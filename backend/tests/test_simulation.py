import pytest
from rest_framework.test import APIClient

from ads.models import Ad
from evidence.models import AuditLog
from similarity.fusion import Shared, Soft, score_pair
from similarity.models import CampaignMembership, Edge, EdgeEvidence, OperatorMembership
from similarity.service import _store_edge

pytestmark = pytest.mark.django_db
N = 1000

ENGINE = [
    Shared("kit_path", "POST /api/v1/trigger/field/{id}/", df=2),
    Shared("kit_path", "GET /aio-static/sdk/main.js", df=2),
    Shared("url_param_keys", "utm_id,utm_visit", df=2),
]
FUNNEL = Shared("funnel_id", "11111111-2222-4333-8444-555555555555", df=2)
PIXEL = Shared("meta_pixel", "1500000000000003", df=2)
ASSET = Shared("asset_host", "zasoby-operatora.example", df=2)


@pytest.fixture
def client():
    return APIClient()


def ad(name: str) -> Ad:
    return Ad.objects.create(external_id=f"t/{name}", title=name)


def edge(a: Ad, b: Ad, shared, soft=()) -> Edge:
    stored = _store_edge(a.pk, b.pk, score_pair(list(shared), list(soft), N), {})
    assert stored is not None
    return stored


def ids(e: Edge, *kinds: str) -> list[int]:
    return list(e.evidence.filter(kind__in=kinds).values_list("pk", flat=True))


def simulate(client, e: Edge, exclude, **extra):
    return client.post(f"/api/edges/{e.pk}/simulate", {"exclude": exclude, **extra}, format="json")


def snapshot():
    return (
        list(Edge.objects.order_by("pk").values_list("pk", "relation", "bits", "updated_at", "verdict")),
        EdgeEvidence.objects.count(),
        AuditLog.objects.count(),
        list(CampaignMembership.objects.values_list("ad_id", "campaign_id")),
        list(OperatorMembership.objects.values_list("ad_id", "operator_id")),
    )


def test_no_exclusions_reproduces_the_production_engine(client):
    e = edge(ad("a"), ad("b"), [*ENGINE, FUNNEL, PIXEL])
    body = simulate(client, e, []).json()
    assert body["baseline"]["relation"] == e.relation == "same_operator"
    assert body["baseline"]["bits"] == pytest.approx(e.bits, abs=0.01)
    assert body["simulated"] == body["baseline"]
    assert body["relation_changed"] is False
    assert not any("różni się" in w for w in body["warnings"])
    assert all("id" in ev for ev in client.get(f"/api/edges/{e.pk}").json()["evidence"])


def test_one_removed_decisive_marker_leaves_the_other(client):
    e = edge(ad("a"), ad("b"), [*ENGINE, FUNNEL, PIXEL])
    body = simulate(client, e, ids(e, "funnel_id")).json()
    assert body["simulated"]["relation"] == "same_operator"
    assert body["simulated"]["bits"] < body["baseline"]["bits"]
    assert [x["kind"] for x in body["excluded"]] == ["funnel_id"]


def test_removing_every_operator_trace_leaves_only_the_engine(client):
    e = edge(ad("a"), ad("b"), [*ENGINE, FUNNEL, PIXEL])
    body = simulate(client, e, ids(e, "funnel_id", "meta_pixel")).json()
    assert body["relation_changed"] is True
    assert body["simulated"]["relation"] == "similar"
    assert any("silnik lejka" in r for r in body["simulated"]["reasons"])


def test_traces_of_one_engine_are_one_confirmation(client):
    # Silnik plus własny host zasobów to operator. Bez hosta zostaje sam silnik, mimo że jego ślady są w dwóch rodzinach.
    e = edge(ad("a"), ad("b"), [*ENGINE, ASSET])
    assert e.relation == "same_operator"
    body = simulate(client, e, ids(e, "asset_host")).json()
    assert body["simulated"]["relation"] == "similar"
    assert body["simulated"]["independent"] == ["kit"]


def test_removing_everything_leaves_no_edge(client):
    e = edge(ad("a"), ad("b"), [FUNNEL], [Soft("page_text_minhash", 0.95)])
    body = simulate(client, e, list(e.evidence.values_list("pk", flat=True))).json()
    assert body["simulated"]["relation"] is None
    assert body["simulated"]["relation_label"] == "brak krawędzi"


def test_campaign_can_drop_to_operator(client):
    e = edge(ad("a"), ad("b"), [*ENGINE, FUNNEL], [Soft("page_text_minhash", 0.95)])
    assert e.relation == "same_campaign"
    body = simulate(client, e, ids(e, "page_text_minhash")).json()
    assert body["simulated"]["relation"] == "same_operator"
    assert body["group_impact"]["campaign"]["binds_after"] is False
    assert body["group_impact"]["operator"]["binds_after"] is True


def test_evidence_of_another_edge_is_rejected(client):
    a, b, c = ad("a"), ad("b"), ad("c")
    first, second = edge(a, b, [FUNNEL]), edge(b, c, [PIXEL])
    response = simulate(client, first, ids(second, "meta_pixel"))
    assert response.status_code == 400
    assert response.json()["unknown"] == ids(second, "meta_pixel")


def test_stale_edge_version_is_a_conflict(client):
    e = edge(ad("a"), ad("b"), [FUNNEL])
    response = simulate(client, e, [], edge_version="2000-01-01T00:00:00+00:00")
    assert response.status_code == 409
    assert response.json()["edge_version"] == e.updated_at.isoformat()
    assert simulate(client, e, [], edge_version=e.updated_at.isoformat()).status_code == 200


def test_group_impact_checks_alternative_paths(client):
    a, b, c, d, f = ad("a"), ad("b"), ad("c"), ad("d"), ad("f")
    ab = edge(a, b, [FUNNEL])
    edge(b, c, [PIXEL])
    edge(a, c, [Shared("google_ads", "18463917747", df=2)])
    lonely = edge(d, f, [Shared("gtm", "GTM-TEST01", df=2)])

    in_triangle = simulate(client, ab, ids(ab, "funnel_id")).json()["group_impact"]["operator"]
    assert in_triangle["binds_before"] and not in_triangle["binds_after"]
    assert in_triangle["pair_still_connected"] is True and in_triangle["path_length"] == 2

    alone = simulate(client, lonely, ids(lonely, "gtm")).json()["group_impact"]["operator"]
    assert alone["pair_still_connected"] is False and "rozpadłaby" in alone["note"]


def test_rejected_path_does_not_count_as_alternative(client):
    a, b, c = ad("a"), ad("b"), ad("c")
    ab = edge(a, b, [FUNNEL])
    edge(b, c, [PIXEL])
    ac = edge(a, c, [Shared("google_ads", "18463917747", df=2)])
    Edge.objects.filter(pk=ac.pk).update(verdict=Edge.Verdict.REJECTED)
    impact = simulate(client, ab, ids(ab, "funnel_id")).json()["group_impact"]["operator"]
    assert impact["pair_still_connected"] is False


def test_simulation_has_no_side_effects(client):
    a, b, c = ad("a"), ad("b"), ad("c")
    e = edge(a, b, [*ENGINE, FUNNEL, PIXEL])
    edge(b, c, [PIXEL])
    before = snapshot()
    for exclude in ([], ids(e, "funnel_id"), list(e.evidence.values_list("pk", flat=True))):
        assert simulate(client, e, exclude).status_code == 200
    assert snapshot() == before
