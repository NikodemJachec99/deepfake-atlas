"""Alerty: nowy materiał w znanej kampanii albo u znanego operatora (#208). Dane zmyślone, sieć podstawiona."""

import pytest
from rest_framework.test import APIClient

from ads.models import Ad
from collectors import bundle
from extractors import ocr
from people.models import Person
from similarity.models import Alert, Operator
from tests import fakes
from tests.test_bundle import ARTICLE_X, ARTICLE_Y, make_case, run
from tests.test_extractors import LANDING_A
from tests.test_pipeline import analyze_url
from workflows import pipeline

pytestmark = pytest.mark.django_db


@pytest.fixture
def client():
    return APIClient()


def three_variants():
    for url in ("https://a.example/1", "https://b.example/2", "https://c.example/3"):
        fakes.page(url, LANDING_A)
    return [analyze_url(url) for url in ("https://a.example/1", "https://b.example/2", "https://c.example/3")]


def test_third_variant_joining_existing_campaign_raises_alert_but_first_two_do_not():
    first, second, third = three_variants()
    assert first.result["cluster"]["alerts"] == []
    # Druga reklama tworzy kampanię z pierwszą: grupa nie istniała wcześniej.
    assert second.result["cluster"]["alerts"] == []
    assert third.result["cluster"]["alerts"] == ["joined_campaign"]

    alert = Alert.objects.get()
    assert alert.kind == Alert.Kind.JOINED_CAMPAIGN
    assert alert.ad_id == third.ad_id
    assert alert.campaign.key == third.result["cluster"]["campaign"]
    assert alert.operator.key == third.result["cluster"]["operator"]
    assert not alert.seen and alert.seen_at is None
    assert alert.description.startswith("Reklama dołączyła do kampanii K-")
    assert 1 <= len(alert.evidence) <= 3
    bits = [e["bits"] for e in alert.evidence]
    assert bits == sorted(bits, reverse=True) and all(b > 0 for b in bits)
    assert {"kind", "label", "family", "bits", "value"} <= alert.evidence[0].keys()


def test_rerunning_stages_does_not_duplicate_alerts():
    *_, third = three_variants()
    assert Alert.objects.count() == 1
    pipeline.run_stage(str(third.pk), "fuse")
    pipeline.run_stage(str(third.pk), "cluster")
    pipeline.run_all(str(third.pk))
    assert Alert.objects.count() == 1


def test_new_campaign_of_known_operator_raises_matching_alert(tmp_path, monkeypatch):
    monkeypatch.setattr(ocr, "read_image", lambda path: ["Jasny Poranek Media", "Sponsorowane"])
    Person.objects.create(name="Jan Testowy")
    cases = [
        make_case(tmp_path, "1", "civic.example", "Zamach na biznesmena — Gazeta.pl", ARTICLE_X + " Jana Testowego nie było.", screenshot=True),
        make_case(tmp_path, "2", "across.example", "Zamach na biznesmena — Gazeta.pl", ARTICLE_X + " Jana Testowego nie było.", ip="198.51.100.9"),
        make_case(tmp_path, "48", "novum.example", "Po programie zatrzymano prowadzącego", ARTICLE_Y, ip="192.0.2.44"),
    ]
    analyses = []
    for case in cases:
        analyses += run(bundle.import_case(case, bundle="nask"))

    assert [a.result["cluster"]["alerts"] for a in analyses] == [[], [], ["new_campaign_known_operator"]]
    alert = Alert.objects.get()
    assert alert.ad.labels["case"] == "48"
    assert alert.campaign is None
    assert alert.operator == Operator.objects.get()
    assert alert.description.startswith("Nowa kampania znanego operatora O-")
    assert alert.evidence


def test_api_list_unseen_seen_and_counter(client):
    *_, third = three_variants()
    ad = Ad.objects.get(pk=third.ad_id)
    older = Alert.objects.create(ad=Ad.objects.exclude(pk=ad.pk).first(), kind=Alert.Kind.JOINED_OPERATOR, description="starszy")
    alert = Alert.objects.get(ad=ad)

    assert client.get("/api/stats").json()["alerts_unseen"] == 2
    listing = client.get("/api/alerts").json()
    assert listing["count"] == 2
    assert [r["id"] for r in listing["results"]] == [older.id, alert.id]  # najnowsze pierwsze
    row = next(r for r in listing["results"] if r["id"] == alert.id)
    assert row["kind"] == "joined_campaign" and row["kind_label"] == "Nowa odsłona znanej kampanii"
    assert row["ad"] == ad.pk and row["campaign"].startswith("K-") and row["operator"].startswith("O-")
    assert row["seen"] is False and row["evidence"]

    done = client.post(f"/api/alerts/{alert.id}/seen")
    assert done.status_code == 200
    assert done.json()["seen"] is True and done.json()["seen_at"]
    assert client.post(f"/api/alerts/{alert.id}/seen").json()["seen"] is True  # idempotentne

    unseen = client.get("/api/alerts?unseen=1").json()
    assert [r["id"] for r in unseen["results"]] == [older.id]
    assert client.get("/api/stats").json()["alerts_unseen"] == 1

    assert client.post(f"/api/alerts/{alert.id}/seen", {"seen": False}, format="json").json()["seen"] is False
    assert client.get("/api/stats").json()["alerts_unseen"] == 2
    assert client.post("/api/alerts/999999/seen").status_code == 404


def test_seen_requires_api_key_when_configured(client, settings):
    *_, third = three_variants()
    alert = Alert.objects.get()
    settings.API_WRITE_KEY = "klucz-testowy"
    assert client.post(f"/api/alerts/{alert.id}/seen").status_code in (401, 403)
    assert client.post(f"/api/alerts/{alert.id}/seen", HTTP_X_API_KEY="klucz-testowy").status_code == 200
