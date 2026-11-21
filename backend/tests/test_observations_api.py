"""API porównania obserwacji. Dane zmyślone."""

import json

import pytest
from rest_framework.test import APIClient

from ads.models import Ad
from similarity.models import Edge
from tests.test_observations import OFFER, URL, WHITE, har, imported

pytestmark = pytest.mark.django_db


@pytest.fixture
def client():
    return APIClient()


def test_candidates_and_comparison_with_links(client, tmp_path):
    a, b = imported(tmp_path, "61", [
        ("oferta.har", har(URL, OFFER, "2026-10-20T12:03:42Z", "Microsoft Edge")),
        ("portal.har", har(URL, WHITE, "2026-10-20T12:06:23Z")),
    ])
    found = client.get(f"/api/ads/{a.pk}/observations").json()
    assert [c["ad"] for c in found["candidates"]] == [b.pk] and found["candidates"][0]["url_match"] == "exact"
    assert found["artifacts"]["har"]["download"].startswith("/api/artifacts/")

    body = client.get(f"/api/observations/compare?a={a.pk}&b={b.pk}").json()
    assert body["url_match"] == "exact" and body["verdict"] == "different"
    assert body["a"]["artifacts"]["page_screenshot"] is None
    assert body["graph"] == f"/api/graph?ad={a.pk}"
    edge = Edge.objects.filter(ad_a_id=min(a.pk, b.pk), ad_b_id=max(a.pk, b.pk)).first()
    assert (body["edge"] or {}).get("id") == (edge.pk if edge else None)
    text = json.dumps(body)
    assert "<html" not in text and "<script" not in text  # żadnego wykonywalnego HTML w odpowiedzi
    assert client.get(body["a"]["artifacts"]["har"]["download"]).status_code == 200


def test_mismatched_urls_and_no_context(client, tmp_path):
    a, b = imported(tmp_path, "d", [
        ("a.har", har("https://dwie-twarze.example/oferta?x=1", OFFER, "2026-10-20T10:00:00Z")),
        ("b.har", har("https://inna-domena.example/", WHITE, "")),
    ])
    for ad in (a, b):
        ad.raw["observation"]["context"] = {}
        ad.save()
    body = client.get(f"/api/observations/compare?a={a.pk}&b={b.pk}").json()
    assert body["url_match"] == "different" and body["seconds_between"] is None
    assert any("kontekstu przeglądarki nie da się porównać" in limit for limit in body["limitations"])
    assert client.get(f"/api/ads/{a.pk}/observations").json()["candidates"] == []


def test_missing_artifacts_and_errors(client):
    bare = Ad.objects.create(external_id="t/bare", raw={"observation": {"exact_url": "https://x.example/", "normalized_url": "https://x.example/", "domain": "x.example"}})
    other = Ad.objects.create(external_id="t/other", raw={"observation": {"exact_url": "https://x.example/", "normalized_url": "https://x.example/", "domain": "x.example"}})
    body = client.get(f"/api/observations/compare?a={bare.pk}&b={other.pk}").json()
    assert body["a"]["artifacts"]["har"] is None and body["a"]["artifacts"]["html"] is None
    assert body["verdict"] == "insufficient"
    assert client.get("/api/observations/compare?a=1").status_code == 400
    assert client.get(f"/api/observations/compare?a={bare.pk}&b={bare.pk}").status_code == 400
    assert client.get(f"/api/observations/compare?a={bare.pk}&b=999999").status_code == 404
    assert client.get(f"/api/ads/{Ad.objects.create(external_id='t/none').pk}/observations").json()["message"]


def test_redaction_reaches_the_api(client, tmp_path):
    secret = "https://dwie-twarze.example/?access_token=EAATESTfake0000000000000000000000tokenQ&x=1"
    a, b = imported(tmp_path, "s", [("a.har", har(secret, OFFER, "2026-10-20T10:00:00Z")), ("b.har", har(secret, OFFER, "2026-10-20T10:01:00Z"))])
    text = json.dumps(client.get(f"/api/observations/compare?a={a.pk}&b={b.pk}").json())
    assert "EAATESTfake" not in text and "sha256-" in text
