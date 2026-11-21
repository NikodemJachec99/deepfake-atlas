import pytest
from rest_framework.test import APIClient

from ads.models import Ad
from similarity.fusion import Shared, Soft
from similarity.models import Edge
from tests.test_simulation import ENGINE, FUNNEL, PIXEL, edge

pytestmark = pytest.mark.django_db
ASSET = Shared("asset_host", "zasoby-operatora.example", df=2)


@pytest.fixture
def client():
    return APIClient()


def capture(name: str, *sources: str, creatives=()) -> Ad:
    return Ad.objects.create(source="capture", external_id=f"t/{name}", raw={"sources": list(sources), "creatives": list(creatives)})


def codes(client, e: Edge) -> list[str]:
    body = client.get(f"/api/edges/{e.pk}/suggestions").json()
    assert body["note"]
    for s in body["suggestions"]:
        assert all(s[k] for k in ("missing", "why", "next_step", "limitation", "rule"))
    return [s["code"] for s in body["suggestions"]]


def test_link_resting_on_one_trace_is_flagged_as_fragile(client):
    e = edge(capture("a", "a.html", "a.har"), capture("b", "b.html", "b.har"), [*ENGINE, ASSET])
    assert e.relation == "same_operator"
    body = client.get(f"/api/edges/{e.pk}/suggestions").json()
    fragile = next(s for s in body["suggestions"] if s["code"] == "single_support")
    assert "Host zasobów lub trackera".lower() in fragile["why"] and "silnika lejka" in fragile["why"]


def test_robust_link_with_full_material_needs_nothing(client):
    e = edge(capture("a", "a.html", "a.har"), capture("b", "b.html", "b.har"), [*ENGINE, FUNNEL, PIXEL], [Soft("page_text_minhash", 0.95)])
    assert e.relation == "same_campaign"
    assert codes(client, e) == []


def test_engine_only_asks_for_an_account_trace(client):
    e = edge(capture("a", "a.html", "a.har"), capture("b", "b.html", "b.har"), ENGINE)
    assert e.relation == "similar"
    body = client.get(f"/api/edges/{e.pk}/suggestions").json()
    hint = next(s for s in body["suggestions"] if s["code"] == "engine_without_account")
    assert "Oba HAR-y już przeanalizowano" in hint["limitation"]


def test_copied_content_without_har_asks_for_har_on_the_right_side(client):
    a, b = capture("a", "a.html", "a.har"), capture("b", "b.html")
    e = edge(a, b, [Shared("page_title", "trudna odpowiedź", df=2)], [Soft("page_text_minhash", 0.95)])
    assert e.relation == "similar"
    body = client.get(f"/api/edges/{e.pk}/suggestions").json()
    assert [s["code"] for s in body["suggestions"]] == ["copy_without_backend", "har_missing"]
    har = body["suggestions"][1]
    assert har["sides"] == [f"B (reklama #{b.pk})"]
    assert "Bez HAR" in body["suggestions"][0]["limitation"]
    assert body["materials"]["B"]["har"] is False


def test_screenshot_only_points_to_the_ad_library_when_the_number_is_known(client):
    from evidence.models import AdMarker, Marker

    a = capture("a", creatives=["sha-zrzutu"])
    b = capture("b", "b.html", "b.har", creatives=["sha-zrzutu-2"])
    AdMarker.objects.create(ad=a, marker=Marker.objects.create(kind="meta_ad_ref", value="1982000000000001"))
    e = edge(a, b, [Shared("creative_phash", "c41e0f0f3c3c7e7e", df=2)], [Soft("text_minhash", 1.0)])
    body = client.get(f"/api/edges/{e.pk}/suggestions").json()
    shot = next(s for s in body["suggestions"] if s["code"] == "screenshot_only")
    assert "1982000000000001" in shot["next_step"]


def test_contradictory_data_rejected_edge_keeps_the_verdict(client):
    e = edge(capture("a", "a.html", "a.har"), capture("b", "b.html", "b.har"), [*ENGINE, ASSET])
    Edge.objects.filter(pk=e.pk).update(verdict=Edge.Verdict.REJECTED)
    body = client.get(f"/api/edges/{e.pk}/suggestions").json()
    assert body["warnings"] and Edge.objects.get(pk=e.pk).verdict == Edge.Verdict.REJECTED
