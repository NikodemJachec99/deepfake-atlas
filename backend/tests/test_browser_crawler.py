"""Crawler z przeglądarką: odpowiedź usługi crawler, powrót do HTTP i HAR z przeglądarki w potoku."""

import base64

import httpx
import pytest

from ads.models import Analysis
from crawler import browser
from crawler.fetch import FetchResult, Hop
from evidence.models import Artifact, Marker
from tests.test_extractors import LANDING_A
from workflows import pipeline

pytestmark = pytest.mark.django_db

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64
FUNNEL = "3f2c9a1e-7b4d-4c2a-9e8f-0a1b2c3d4e5f"


def entry(url: str, status: int = 200, mime: str = "text/html", method: str = "GET", text: str = "", post: str = "") -> dict:
    request = {"method": method, "url": url, "headers": []}
    if post:
        request["postData"] = {"mimeType": "application/x-www-form-urlencoded", "text": post}
    return {
        "startedDateTime": "2026-11-21T20:00:00.000Z",
        "request": request,
        "response": {"status": status, "headers": [], "content": {"mimeType": mime, "text": text}},
        "serverIPAddress": "203.0.113.7",
    }


def har_with_js_redirect() -> dict:
    return {
        "log": {
            "entries": [
                entry("https://hop.example/r", text="<script>location='https://lp.example/start'</script>"),
                entry("https://lp.example/start", text=LANDING_A),
                entry("https://lp.example/api/lead/submit", method="POST", mime="application/json", text="{}", post=f"offer_uuid={FUNNEL}&name=x"),
            ]
        }
    }


def payload(**extra) -> dict:
    return {
        "profile": "victim",
        "engine": "browser",
        "chain": [{"url": "https://hop.example/r", "status": 200, "via": "http"}, {"url": "https://lp.example/start", "status": 200, "via": "js"}],
        "final_url": "https://lp.example/start",
        "status": 200,
        "content_type": "text/html; charset=utf-8",
        "html": LANDING_A,
        "har": har_with_js_redirect(),
        "screenshot": base64.b64encode(PNG).decode(),
        "console": ["log: ok"],
        "blocked": ["127.0.0.1:8000 prowadzi do sieci niepublicznej"],
        "error": "",
        **extra,
    }


def test_payload_becomes_fetch_result_with_har_focused_on_final_document():
    result = browser.BrowserFetcher.from_payload(payload(), "victim")
    assert result.engine == "browser" and result.status == 200
    assert [h.via for h in result.chain] == ["http", "js"]
    assert result.screenshot == PNG and b"<html>" in result.body
    urls = [e["request"]["url"] for e in result.har["log"]["entries"]]
    assert urls[0] == "https://lp.example/start"  # strona pośrednia odcięta, ekstraktor HAR widzi właściwy dokument
    assert result.notes == ["zablokowane: 127.0.0.1:8000 prowadzi do sieci niepublicznej"]


def test_not_png_screenshot_and_error_page_are_dropped():
    result = browser.BrowserFetcher.from_payload(
        payload(screenshot=base64.b64encode(b"<svg/>").decode(), final_url="chrome-error://chromewebdata/", har=None), "victim"
    )
    assert result.screenshot == b"" and result.body == b""


def test_service_down_falls_back_to_http(monkeypatch, settings):
    settings.CRAWLER_BROWSER_URL = "http://crawler:8000"
    monkeypatch.setattr(browser, "resolve_public", lambda url: "203.0.113.7")

    def down(*args, **kwargs):
        raise httpx.ConnectError("brak usługi")

    monkeypatch.setattr(browser.httpx, "post", down)
    monkeypatch.setattr(browser.HttpFetcher, "fetch", lambda self, url, profile="victim": FetchResult(profile=profile, final_url=url, status=200, body=b"<html></html>"))
    result = browser.BrowserFetcher().fetch("https://lp.example/start")
    assert result.engine == "http" and result.status == 200
    assert "przeglądarka niedostępna" in result.notes[0]


def test_private_address_is_refused_before_calling_the_service(monkeypatch):
    called = []
    monkeypatch.setattr(browser.httpx, "post", lambda *a, **k: called.append(a))
    result = browser.BrowserFetcher().fetch("http://127.0.0.1:5432/")
    assert result.error.startswith("BlockedUrl") and not called


class FakeBrowserFetcher:
    def fetch(self, url: str, profile: str = "victim") -> FetchResult:
        if profile == "bot":
            return FetchResult(profile="bot", chain=[Hop(url, 200)], final_url=url, status=200, body=LANDING_A.encode(), engine="browser")
        return browser.BrowserFetcher.from_payload(payload(), profile)

    def fetch_bytes(self, url: str, profile: str = "victim") -> bytes:
        return b""


def test_pipeline_uses_browser_har_and_stores_screenshot(settings):
    settings.CRAWLER_FETCHER = "tests.test_browser_crawler.FakeBrowserFetcher"
    analysis = Analysis.objects.create(input_kind=Analysis.Kind.URL, input_value="https://hop.example/r")
    pipeline.run_all(str(analysis.pk))
    analysis.refresh_from_db()

    victim = analysis.state["pages"]["victim"]
    assert victim["engine"] == "browser" and victim["chain"][-1]["via"] == "js"
    assert Artifact.objects.get(pk=victim["screenshot_sha"]).kind == "page_screenshot"
    assert Artifact.objects.get(pk=analysis.state["capture"]["har"]).kind == "har"
    kinds = set(Marker.objects.filter(ad_markers__ad=analysis.ad).values_list("kind", flat=True))
    assert {"funnel_id", "kit_path", "redirect_domain"} <= kinds
    event = analysis.events.filter(stage="crawl", payload__profile="victim").first()
    assert event.payload["engine"] == "browser" and event.payload["screenshot"] == victim["screenshot_sha"]

    # Ponowne uruchomienie nie dubluje śladów z HAR.
    count = len(analysis.state["capture"]["observations"])
    pipeline.stage_crawl(analysis)
    assert len(analysis.state["capture"]["observations"]) == count

    from similarity.observations import artifacts

    assert artifacts(analysis.ad)["page_screenshot"]["sha256"] == victim["screenshot_sha"]
