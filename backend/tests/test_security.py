"""Bezpieczeństwo API (#186): pochodzenie zapisu, klucz, rozmiar, parsery, upload, SSRF przy TLS."""

import io
import zipfile
from unittest import mock

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from ads.models import Ad
from api import views
from enrichment.providers import LiveEnricher
from similarity.models import Edge

pytestmark = pytest.mark.django_db
EVIL = "https://zla-strona.example"


@pytest.fixture
def edge():
    a = Ad.objects.create(external_id="s/1")
    b = Ad.objects.create(external_id="s/2")
    return Edge.objects.create(ad_a=a, ad_b=b, relation="similar", bits=10, probability=0.5)


def verdict(client, edge, **headers):
    return client.post(f"/api/edges/{edge.pk}/verdict", {"verdict": "rejected"}, format="json", **headers)


def test_write_from_foreign_origin_is_refused(edge):
    client = APIClient()
    assert verdict(client, edge, HTTP_ORIGIN=EVIL).status_code == 403
    edge.refresh_from_db()
    assert edge.verdict == ""
    # interfejs z listy CORS, brak Origin (curl) i własny host przechodzą
    assert verdict(client, edge, HTTP_ORIGIN="http://localhost:3000").status_code == 200
    assert verdict(client, edge).status_code == 200
    assert verdict(client, edge, HTTP_ORIGIN="http://testserver").status_code == 200


def test_reads_are_not_affected_by_origin(edge):
    assert APIClient().get(f"/api/edges/{edge.pk}", HTTP_ORIGIN=EVIL).status_code == 200


def test_form_encoded_write_is_unsupported(edge):
    response = APIClient().post(f"/api/edges/{edge.pk}/verdict", {"verdict": "rejected"})  # multipart, jak formularz
    assert response.status_code == 415
    edge.refresh_from_db()
    assert edge.verdict == ""


@override_settings(API_WRITE_KEY="tajny-klucz-testowy")
def test_optional_write_key(edge):
    client = APIClient()
    assert verdict(client, edge).status_code == 401
    assert verdict(client, edge, HTTP_X_API_KEY="zly").status_code == 401
    assert verdict(client, edge, HTTP_X_API_KEY="tajny-klucz-testowy").status_code == 200
    assert verdict(client, edge, HTTP_AUTHORIZATION="Bearer tajny-klucz-testowy").status_code == 200
    assert client.get(f"/api/edges/{edge.pk}").status_code == 200  # odczyt bez klucza


@override_settings(UPLOAD_MAX_BYTES=100)
def test_oversized_request_is_refused_before_reading():
    response = APIClient().post("/api/analyses/upload", {"files": [io.BytesIO(b"x" * 500)]}, format="multipart")
    assert response.status_code == 413


@pytest.mark.parametrize("name", ["..", ".", ".htaccess"])
def test_upload_rejects_unsafe_file_names(name):
    upload = io.BytesIO(b"<html></html>")
    upload.name = name
    assert APIClient().post("/api/analyses/upload", {"files": [upload]}, format="multipart").status_code == 400


def zipped(entries: dict[str, bytes]) -> io.BytesIO:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
    buffer.seek(0)
    buffer.name = "sprawa.zip"
    return buffer


def test_zip_slip_and_bomb_are_refused(monkeypatch):
    client = APIClient()
    slip = client.post("/api/analyses/upload", {"files": [zipped({"../../poza.html": b"x"})]}, format="multipart")
    assert slip.status_code == 400 and "poza katalogiem" in slip.json()["files"]
    monkeypatch.setattr(views, "MAX_ZIP_BYTES", 1000)
    bomb = client.post("/api/analyses/upload", {"files": [zipped({"a.html": b"0" * 5000})]}, format="multipart")
    assert bomb.status_code == 400 and "za duże" in bomb.json()["files"]


def test_responses_forbid_framing(edge):
    assert APIClient().get(f"/api/edges/{edge.pk}")["X-Frame-Options"] == "DENY"


def test_tls_fingerprint_never_connects_to_private_address():
    with mock.patch("enrichment.providers.socket.create_connection", side_effect=AssertionError("połączenie do sieci wewnętrznej")):
        assert LiveEnricher(timeout=1).tls_fingerprint("127.0.0.1") == ""
        assert LiveEnricher(timeout=1).tls_fingerprint("localhost") == ""


def test_analyses_are_rate_limited(monkeypatch):
    from django.core.cache import cache

    cache.clear()
    monkeypatch.setattr(views.AnalysesThrottle, "THROTTLE_RATES", {"analyses": "2/min"})
    client = APIClient()
    codes = [client.post("/api/analyses", {"kind": "text", "value": f"test {i}"}, format="json").status_code for i in range(3)]
    assert codes[:2] == [201, 201] and codes[2] == 429
    cache.clear()
