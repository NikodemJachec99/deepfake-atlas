import pytest
from asgiref.sync import async_to_sync
from django.test import AsyncClient
from rest_framework.test import APIClient

from ads.models import Ad
from evidence.models import AuditLog
from similarity.models import Edge
from tests import fakes
from tests.test_extractors import LANDING_A

pytestmark = pytest.mark.django_db


@pytest.fixture
def client():
    return APIClient()


def submit(client, url):
    response = client.post("/api/analyses", {"kind": "url", "value": url}, format="json")
    assert response.status_code == 201, response.content
    return response.json()


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_discovery_flow_from_submission_to_evidence(client):
    fakes.page("https://a.example/1", LANDING_A)
    fakes.page("https://b.example/2", LANDING_A)
    submit(client, "https://a.example/1")
    second = submit(client, "https://b.example/2")
    assert second["status"] == "done"
    assert second["events_url"] == f"/api/analyses/{second['id']}/events"
    ad_id = second["ad"]

    ad = client.get(f"/api/ads/{ad_id}").json()
    assert ad["campaign"].startswith("K-")
    assert [f["family"] for f in ad["genome"]] == ["infra", "track", "tmpl", "crea", "narr", "pers", "beh"]
    track = next(f for f in ad["genome"] if f["family"] == "track")
    ga = next(m for m in track["markers"] if m["kind"] == "ga4")
    assert ga["value"] == "G-7K2QX9LM4T" and ga["ad_count"] == 2
    assert not any(m["kind"].endswith("_band") for f in ad["genome"] for m in f["markers"])

    edges = client.get(f"/api/ads/{ad_id}/edges").json()
    assert len(edges) == 1
    detail = client.get(f"/api/edges/{edges[0]['id']}").json()
    assert detail["relation"] == "same_campaign"
    assert len(detail["ads"]) == 2
    top = detail["evidence"][0]
    assert top["weight_bits"] >= detail["evidence"][-1]["weight_bits"]
    assert {"family_label", "label", "value_a", "value_b", "df", "corpus_n", "artifact_a"} <= top.keys()

    campaigns = client.get("/api/campaigns").json()["results"]
    assert campaigns[0]["size"] == 2
    campaign = client.get(f"/api/campaigns/{campaigns[0]['id']}").json()
    assert len(campaign["ads"]) == 2 and len(campaign["edges"]) == 1
    assert any(m["kind"] == "ga4" and m["in_group"] == 2 for m in campaign["core_markers"])

    graph = client.get(f"/api/graph?campaign={campaigns[0]['id']}").json()
    assert len(graph["nodes"]) == 2 and len(graph["edges"]) == 1
    assert graph["nodes"][0]["campaign"] == campaigns[0]["key"]
    assert graph["edges"][0]["family"] in {"track", "narr", "tmpl", "infra"}
    assert all(n["member"] is True for n in graph["nodes"])
    assert "member" not in client.get(f"/api/graph?ad={ad_id}").json()["nodes"][0]

    # Sąsiad spoza grupy, dołączony krawędzią podobieństwa, ma member=false, a członkowie true.
    outsider = Ad.objects.create(source="capture", external_id="outsider/1")
    a, b = sorted([ad_id, outsider.pk])
    Edge.objects.create(ad_a_id=a, ad_b_id=b, relation="similar", bits=5.0, probability=0.5, model_version="fs-5")
    graph = client.get(f"/api/graph?campaign={campaigns[0]['id']}").json()
    by_id = {n["id"]: n["member"] for n in graph["nodes"]}
    assert by_id[outsider.pk] is False and by_id[ad_id] is True and sum(by_id.values()) == 2
    operator = client.get("/api/operators").json()["results"][0]
    assert {n["member"] for n in client.get(f"/api/graph?operator={operator['id']}").json()["nodes"]} == {True, False}


@pytest.mark.django_db(transaction=True)
def test_events_endpoint_streams_all_events_and_closes(client):
    fakes.page("https://a.example/1", LANDING_A)
    analysis = submit(client, "https://a.example/1")

    async def read():
        response = await AsyncClient().get(analysis["events_url"])
        assert response.status_code == 200
        assert response["Content-Type"] == "text/event-stream"
        return b"".join([chunk async for chunk in response.streaming_content]).decode()

    body = async_to_sync(read)()
    assert "event: ingest" in body and "event: cluster" in body
    assert body.rstrip().endswith("event: close\ndata: {}")


def test_verdict_is_saved_and_audited(client):
    fakes.page("https://a.example/1", LANDING_A)
    fakes.page("https://b.example/2", LANDING_A)
    submit(client, "https://a.example/1")
    submit(client, "https://b.example/2")
    edge = Edge.objects.get()
    response = client.post(f"/api/edges/{edge.pk}/verdict", {"verdict": "rejected", "note": "inny operator"}, format="json")
    assert response.status_code == 200
    edge.refresh_from_db()
    assert edge.verdict == "rejected" and edge.verdict_note == "inny operator"
    assert AuditLog.objects.filter(action="edge.verdict", object_id=str(edge.pk)).count() == 1


def test_artifact_is_served_as_inert_attachment(client):
    fakes.page("https://a.example/1", LANDING_A)
    ad_id = submit(client, "https://a.example/1")["ad"]
    genome = client.get(f"/api/ads/{ad_id}").json()["genome"]
    sha = next(m["artifact"] for f in genome for m in f["markers"] if m["artifact"])
    response = client.get(f"/api/artifacts/{sha}")
    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/plain")
    assert "attachment" in response["Content-Disposition"]
    assert "G-7K2QX9LM4T" in response.content.decode()


def test_invalid_submission_is_rejected(client):
    response = client.post("/api/analyses", {"kind": "url", "value": "javascript:alert(1)"}, format="json")
    assert response.status_code == 400
    assert client.post("/api/analyses", {"kind": "plik", "value": "x"}, format="json").status_code == 400


def test_kinds_dictionary_and_schema(client):
    kinds = client.get("/api/kinds").json()
    assert len(kinds["families"]) == 7
    assert client.get("/api/schema/").status_code == 200
