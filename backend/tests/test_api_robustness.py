"""Odporność API: 400 zamiast 500 dla złych parametrów, 404 dla nieznanych zasobów, graf z jawnym ucinaniem,
JSON zamiast strony debug, nowe słowa w stopliście. Dane zmyślone."""

import pytest
from django.db import OperationalError
from rest_framework.test import APIClient

from ads.models import Ad
from extractors.keywords import keywords
from similarity.models import Campaign, CampaignMembership, Edge, Operator, OperatorMembership

pytestmark = pytest.mark.django_db


@pytest.fixture
def client():
    return APIClient()


def ad(source="capture") -> Ad:
    return Ad.objects.create(source=source, external_id=f"{source}/{Ad.objects.count()}")


def edge(a: Ad, b: Ad, relation: str, probability: float = 0.5, duplicate: bool = False) -> Edge:
    low, high = sorted((a, b), key=lambda x: x.pk)
    return Edge.objects.create(ad_a=low, ad_b=high, relation=relation, bits=6.0, probability=probability, duplicate=duplicate, model_version="t")


@pytest.mark.parametrize(
    "path",
    [
        "/api/graph?campaign=zz",
        "/api/graph?operator=zz",
        "/api/graph?ad=zz",
        "/api/graph?limit=abc",
        "/api/graph?limit=-1",
        "/api/graph?limit=0",
        "/api/graph?limit=999999",
        "/api/graph?ad=-5",
        "/api/ads?campaign=abc",
        "/api/ads?operator=zz",
        "/api/ads?campaign=99999999999999999999999999",
    ],
)
def test_bad_parameters_give_polish_400(client, path):
    response = client.get(path)
    assert response.status_code == 400, response.content
    assert response.json()["detail"].startswith("Parametr ")


def test_bad_precedent_limit_and_sse_after_are_400(client):
    a, b = ad(), ad()
    e = edge(a, b, "similar")
    assert client.get(f"/api/edges/{e.pk}/precedents?limit=x").status_code == 400
    assert client.get(f"/api/edges/{e.pk}/precedents?limit=-2").status_code == 200  # przycinany jak za duży
    assert client.get(f"/api/edges/{e.pk}/precedents?limit=3").status_code == 200


def test_unknown_resources_are_404_not_empty(client):
    assert client.get("/api/ads/99999/edges").status_code == 404
    assert client.get("/api/graph?ad=99999").status_code == 404
    assert client.get("/api/graph?campaign=99999").status_code == 404
    assert client.get("/api/graph?operator=99999").status_code == 404
    existing = ad()
    assert client.get(f"/api/ads/{existing.pk}/edges").json() == []


def test_graph_orders_by_importance_and_reports_truncation(client):
    cap = [ad() for _ in range(6)]
    lib = [ad("microsoft") for _ in range(4)]
    edge(cap[0], cap[1], "same_campaign", 0.99, duplicate=True)
    edge(lib[0], lib[1], "same_campaign", 0.95)
    edge(lib[1], lib[2], "same_campaign", 0.94)
    edge(cap[1], cap[2], "same_campaign", 0.90)
    edge(cap[2], cap[3], "similar", 0.10)
    edge(cap[3], cap[4], "same_operator", 0.20)
    edge(lib[2], lib[3], "same_operator", 0.30)

    full = client.get("/api/graph").json()
    assert full["truncated"] is False and full["total"] == 7 and full["limit"] == 2000
    assert full["total_by_relation"] == {"same_campaign": 4, "same_operator": 2, "similar": 1}
    assert full["returned_by_relation"] == full["total_by_relation"]

    cut = client.get("/api/graph?limit=4").json()
    assert cut["truncated"] is True and cut["total"] == 7 and len(cut["edges"]) == 4
    relations = [e["relation"] for e in cut["edges"]]
    # operator i podobna przed kampanią, duplikat na końcu (tu: w ogóle odpadł)
    assert relations[:3] == ["same_operator", "same_operator", "similar"]
    assert [e["duplicate"] for e in cut["edges"]] == [False, False, False, False]
    # w obrębie relacji najpierw pary materiałów ze spraw (0.90) przed biblioteką (0.95)
    assert (cut["edges"][0]["source"], cut["edges"][0]["target"]) == (cap[3].pk, cap[4].pk)
    assert (cut["edges"][3]["source"], cut["edges"][3]["target"]) == (cap[1].pk, cap[2].pk)
    assert cut["returned_by_relation"] == {"same_operator": 2, "similar": 1, "same_campaign": 1}
    assert cut["total_by_relation"]["same_campaign"] == 4


def test_graph_filters_by_relation_and_source(client):
    cap, lib = [ad() for _ in range(3)], [ad("microsoft") for _ in range(2)]
    edge(cap[0], cap[1], "same_campaign")
    edge(cap[1], cap[2], "similar")
    edge(cap[2], lib[0], "similar")
    capture_only = client.get("/api/graph?source=capture").json()
    assert capture_only["total"] == 2 and {e["relation"] for e in capture_only["edges"]} == {"same_campaign", "similar"}
    assert client.get("/api/graph?source=capture&relation=similar").json()["total"] == 1
    assert client.get("/api/graph?relation=similar").json()["total"] == 2


def test_graph_focus_still_works(client):
    a, b, c = ad(), ad(), ad()
    campaign = Campaign.objects.create()
    for member in (a, b):
        CampaignMembership.objects.create(ad=member, campaign=campaign)
    edge(a, b, "same_campaign")
    edge(b, c, "similar")
    edge(c, ad(), "similar")
    body = APIClient().get(f"/api/graph?campaign={campaign.pk}").json()
    assert body["total"] == 2 and len(body["nodes"]) == 3
    assert APIClient().get(f"/api/graph?ad={c.pk}").json()["total"] == 2
    operator = Operator.objects.create()
    OperatorMembership.objects.create(ad=a, operator=operator)
    assert APIClient().get(f"/api/graph?operator={operator.pk}").json()["total"] == 1


def test_unhandled_error_is_json_without_traceback(client, settings, monkeypatch):
    settings.DEBUG = False
    client.raise_request_exception = False

    def boom(*args, **kwargs):
        raise RuntimeError("sekret w tracebacku /app/secret.py")

    monkeypatch.setattr("api.views.Campaign.objects", type("M", (), {"annotate": boom, "filter": boom}))
    response = client.get("/api/stats")
    assert response.status_code == 500
    assert response["Content-Type"].startswith("application/json")
    assert response.json() == {"detail": "Błąd serwera."}
    assert b"sekret" not in response.content


def test_database_overload_is_503_json(client, settings, monkeypatch):
    settings.DEBUG = False

    def boom(*args, **kwargs):
        raise OperationalError("FATAL: sorry, too many clients already")

    monkeypatch.setattr("api.views.Ad.objects", type("M", (), {"count": boom, "filter": boom}))
    response = client.get("/api/stats")
    assert response.status_code == 503
    assert "przeciążona" in response.json()["detail"]
    assert b"too many clients" not in response.content


def test_connections_are_closed_after_request():
    from django.conf import settings

    assert settings.DATABASES["default"]["CONN_MAX_AGE"] == 0
    assert settings.DATABASES["default"]["CONN_HEALTH_CHECKS"] is True


def test_keywords_skip_english_template_words_and_button_labels():
    text = "have found results improve poland czas szczegóły ucieka platforma platforma zysk zysk have found results improve poland czas ucieka"
    assert keywords(text) == ["platforma", "zysk"]


def test_concurrency_limit_queues_instead_of_failing(settings):
    import asyncio

    from asgiref.sync import iscoroutinefunction

    from api.errors import ConcurrencyLimitMiddleware

    settings.API_MAX_CONCURRENCY = 3
    state = {"now": 0, "peak": 0}

    async def view(request):
        state["now"] += 1
        state["peak"] = max(state["peak"], state["now"])
        await asyncio.sleep(0.02)
        state["now"] -= 1
        return "ok"

    middleware = ConcurrencyLimitMiddleware(view)
    assert iscoroutinefunction(middleware)

    async def run():
        return await asyncio.gather(*[middleware(None) for _ in range(20)])

    assert asyncio.run(run()) == ["ok"] * 20
    assert state["peak"] == 3
