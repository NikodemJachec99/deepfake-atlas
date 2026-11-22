"""Czytelne streszczenie HAR: żądania, przekierowania, ślady. Bez treści i bez tokenów w adresach."""

import json

import pytest
from rest_framework.test import APIClient

from evidence import store

pytestmark = pytest.mark.django_db


def entry(url, method="GET", status=200, mime="text/html", **extra):
    return {
        "startedDateTime": "2026-10-20T12:03:42.174Z", "time": 41.6, "serverIPAddress": extra.pop("ip", ""),
        "request": {"method": method, "url": url, **extra.pop("request", {})},
        "response": {"status": status, "bodySize": 1200, "content": {"mimeType": mime, "text": "<html>TAJNA TRESC</html>"}, **extra},
    }


HAR = {"log": {"entries": [
    entry("http://go.example/r?ref=1", status=302, redirectURL="https://shop.example/"),
    entry("https://shop.example/?access_token=EAAB1234567890abcdef"),
    entry("https://shop.example/api/panel/save", method="POST", mime="application/json",
          request={"postData": {"text": "page_uuid=11111111-2222-4333-8444-555555555555"}}),
    entry("https://www.facebook.com/tr/?id=1234567890123456&ev=PageView", mime="image/gif"),
    entry("https://cdn.obce.example/app.js", mime="application/javascript"),
]}}


def put(data):
    return store.put(json.dumps(data).encode(), kind="har", content_type="application/json", source_url="https://shop.example/").sha256


def test_har_overview_lists_requests_chain_and_traces_without_tokens():
    body = APIClient().get(f"/api/artifacts/{put(HAR)}/har").json()
    assert body["total"] == 5 and body["with_traces"] == 4
    assert [hop["status"] for hop in body["chain"]] == [302, 200]
    first, page, post, pixel, script = body["entries"]
    assert first["traces"] == ["redirect_domain"] and first["status"] == 302 and first["redirect_to"] == "https://shop.example/"
    assert page["main"] and page["type"] == "dokument" and page["size"] == 1200 and page["ms"] == 42
    assert "EAAB1234567890abcdef" not in json.dumps(body) and "sha256-" in page["url"]
    assert post["traces"] == ["kit_path", "funnel_id"] and post["type"] == "dane"
    assert pixel["traces"] == ["meta_pixel"] and script["traces"] == ["asset_host"]
    assert body["trace_labels"]["meta_pixel"] == "Meta Pixel"
    assert "TAJNA TRESC" not in json.dumps(body)


def test_har_overview_rejects_non_har_and_broken_files():
    client = APIClient()
    html = store.put(b"<html></html>", kind="html", content_type="text/html", source_url="https://shop.example/").sha256
    assert client.get(f"/api/artifacts/{html}/har").status_code == 404
    broken = store.put(b"nie json", kind="har", content_type="application/json", source_url="https://shop.example/").sha256
    assert client.get(f"/api/artifacts/{broken}/har").status_code == 422
    empty = put({"log": {"entries": []}})
    assert client.get(f"/api/artifacts/{empty}/har").json()["total"] == 0
