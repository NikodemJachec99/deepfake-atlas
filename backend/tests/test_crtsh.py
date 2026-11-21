"""crt.sh: certyfikaty domeny z dzienników CT. Odpowiedź w formacie crt.sh, domeny zmyślone."""

import json
from pathlib import Path

import httpx
import pytest

from ads.models import Analysis
from enrichment import crtsh, providers
from enrichment.models import CertLookup
from evidence.models import AdMarker, Marker
from similarity.models import Edge
from tests import fakes
from tests.test_extractors import LANDING_A
from tests.test_pipeline import analyze_url

RECORDED = json.loads((Path(__file__).parent / "data" / "crtsh_zysk-a.json").read_text(encoding="utf-8"))
SHARED = "065d3197023fcd8e256be424608c75b4fe04"
OWN = "04aa11bb22cc33dd44ee55ff66778899aabb"
CDN = "0127168277e6fc69e162991dcfaa0490"


@pytest.fixture(autouse=True)
def _crtsh_up(monkeypatch):
    monkeypatch.setattr(providers, "CRTSH_INTERVAL", 0)
    monkeypatch.setattr(providers, "_crtsh_down_until", 0.0)


def test_parse_merges_precertificate_and_sorts_newest_first():
    certs = crtsh.parse(RECORDED)
    assert [c.serial for c in certs] == [SHARED, CDN, OWN]
    shared = certs[0]
    assert shared.crtsh_id == 9100000001
    assert shared.domains == ["inwest-b.example", "zysk-a.example"]


def test_observations_skip_certificate_shared_by_cdn():
    obs, neighbours = crtsh.observations("zysk-a.example", crtsh.parse(RECORDED))
    assert {o.value for o in obs} == {SHARED, OWN}
    assert all(o.kind == "tls_serial" for o in obs)
    assert neighbours == ["inwest-b.example"]
    by_value = {o.value: o for o in obs}
    assert by_value[SHARED].detail["domains"] == ["inwest-b.example"]
    assert "domains" not in by_value[OWN].detail


def test_live_enricher_reads_recorded_response(monkeypatch):
    monkeypatch.setattr(providers, "CRTSH_INTERVAL", 0)
    seen = {}

    def fake_get(url, params=None, timeout=None):
        seen.update(url=url, params=params, timeout=timeout)
        return httpx.Response(200, json=RECORDED)

    monkeypatch.setattr(providers.httpx, "get", fake_get)
    assert providers.LiveEnricher().crtsh("zysk-a.example") == RECORDED
    assert seen["params"] == {"q": "zysk-a.example", "output": "json"}
    assert seen["timeout"] == providers.CRTSH_TIMEOUT


@pytest.mark.parametrize("response", [httpx.Response(502, text="Bad Gateway"), httpx.Response(200, text="<html>")])
def test_live_enricher_returns_none_on_bad_answer(monkeypatch, response):
    monkeypatch.setattr(providers, "CRTSH_INTERVAL", 0)
    monkeypatch.setattr(providers.httpx, "get", lambda *a, **k: response)
    assert providers.LiveEnricher().crtsh("zysk-a.example") is None


def test_after_failure_crtsh_is_skipped_for_a_while(monkeypatch):
    calls = []

    def down(*a, **k):
        calls.append(1)
        raise httpx.ConnectTimeout("crt.sh nie odpowiada")

    monkeypatch.setattr(providers.httpx, "get", down)
    live = providers.LiveEnricher()
    assert live.crtsh("zysk-a.example") is None
    assert live.crtsh("inwest-b.example") is None
    assert len(calls) == 1


def test_live_enricher_returns_none_on_timeout(monkeypatch):
    monkeypatch.setattr(providers, "CRTSH_INTERVAL", 0)

    def timeout(*a, **k):
        raise httpx.ReadTimeout("crt.sh nie odpowiada")

    monkeypatch.setattr(providers.httpx, "get", timeout)
    assert providers.LiveEnricher().crtsh("zysk-a.example") is None


@pytest.mark.django_db
def test_shared_certificate_becomes_evidence_between_domains():
    fakes.page("https://zysk-a.example/lp/1", LANDING_A)
    fakes.page("https://inwest-b.example/start", LANDING_A.replace("Zarabiaj 12 000 zł", "Odbierz 9 500 zł"))
    fakes.CERTS["zysk-a.example"] = RECORDED
    fakes.CERTS["inwest-b.example"] = [RECORDED[0]]
    first = analyze_url("https://zysk-a.example/lp/1")
    assert first.result["enrich"]["crtsh"] == {"certs": 3, "used": 2, "domains": ["inwest-b.example"]}
    assert not Marker.objects.filter(kind="tls_serial", value=CDN).exists()
    marker = AdMarker.objects.get(ad=first.ad, marker__value=SHARED)
    assert marker.detail["from"] == "crt.sh"

    analyze_url("https://inwest-b.example/start")
    assert Marker.objects.get(kind="tls_serial", value=SHARED).ad_count == 2
    edge = Edge.objects.get()
    cert = edge.evidence.get(kind="tls_serial")
    assert cert.value_a == SHARED and cert.weight_bits > 0


@pytest.mark.django_db
def test_crtsh_answer_is_cached():
    fakes.page("https://zysk-a.example/lp/1", LANDING_A)
    fakes.page("https://zysk-a.example/lp/2", LANDING_A)
    fakes.CERTS["zysk-a.example"] = RECORDED
    analyze_url("https://zysk-a.example/lp/1")
    analyze_url("https://zysk-a.example/lp/2")
    assert fakes.CERT_CALLS == ["zysk-a.example"]
    assert CertLookup.objects.get().domain == "zysk-a.example"


@pytest.mark.django_db
def test_no_answer_from_crtsh_does_not_stop_the_analysis():
    fakes.page("https://zysk-a.example/lp/1", LANDING_A)
    fakes.CERTS["zysk-a.example"] = None
    analysis = analyze_url("https://zysk-a.example/lp/1")
    assert analysis.status == Analysis.Status.DONE
    assert analysis.result["enrich"]["crtsh"] is None
    assert analysis.events.filter(stage="enrich", message__startswith="crt.sh nie odpowiedział").exists()
    assert not Marker.objects.filter(kind="tls_serial").exists()
    # brak odpowiedzi nie trafia do pamięci, następna analiza spyta jeszcze raz
    assert not CertLookup.objects.exists()
