"""Obserwacje stron i porównanie offline. Domeny, tokeny i treści zmyślone."""

import json

import pytest

from ads.models import Ad
from collectors import bundle
from collectors.observation import normalize_url, observation_info
from similarity.observations import compare
from tests.test_bundle import run
from tests.test_capture import entry

pytestmark = pytest.mark.django_db

OFFER = "<html><head><title>Oferta dnia</title></head><body>" + "".join(f"<p class='o'>Kup teraz suplement numer {i} z rabatem.</p>" for i in range(40)) + "</body></html>"
WHITE = "<html><head><title>Portal analiz</title></head><body>" + "".join(f"<div class='w'><span>Analiza rynku mediów, rozdział {i}.</span></div>" for i in range(40)) + "</body></html>"
URL = "https://dwie-twarze.example/?utm_id=AbCdEf123456&utm_visit=01a00000-aaaa-7bbb-8ccc-000000000009"


def har(url: str, html: str, when: str, browser: str = "Google Chrome", language: str = "pl-PL", cookie: str = "", extra_hosts=()) -> dict:
    doc = entry("GET", url, text=html)
    doc["startedDateTime"] = when
    doc["request"]["headers"] = [
        {"name": "sec-ch-ua", "value": f'"{browser}";v="155", "Chromium";v="155", "Not(A:Brand";v="24"'},
        {"name": "sec-ch-ua-mobile", "value": "?0"},
        {"name": "sec-ch-ua-platform", "value": '"Windows"'},
        {"name": "accept-language", "value": language},
        *([{"name": "cookie", "value": cookie}] if cookie else []),
    ]
    entries = [doc] + [entry("GET", f"https://{h}/x.js", mime="application/javascript") for h in extra_hosts]
    return {"log": {"pages": [{"startedDateTime": when, "title": url}], "entries": entries}}


def case_with(tmp_path, name: str, captures: list[tuple[str, dict]]):
    case = tmp_path / name
    case.mkdir()
    for filename, data in captures:
        (case / filename).write_text(json.dumps(data), encoding="utf-8")
    return case


def imported(tmp_path, name, captures):
    run(bundle.import_case(case_with(tmp_path, name, captures), bundle="t"))
    return list(Ad.objects.filter(labels__case=name).order_by("external_id"))


def test_identical_url_with_different_content_keeps_both_variants(tmp_path):
    a, b = imported(tmp_path, "61", [
        ("oferta.har", har(URL, OFFER, "2026-10-20T12:03:42Z", "Microsoft Edge", "pl,en;q=0.9", extra_hosts=["googleads.g.doubleclick.net"])),
        ("portal.har", har(URL, WHITE, "2026-10-20T12:06:23Z", "Google Chrome", "pl-PL,pl;q=0.9")),
    ])
    assert a.external_id != b.external_id  # dwa przechwycenia tej samej domeny w jednym katalogu to dwie strony
    result = compare(a, b)
    assert result["url_match"] == "exact"
    assert result["seconds_between"] == 161
    assert result["verdict"] == "different"
    assert any("jednorazowy token" in h for h in result["hypotheses"])
    assert any("kontekst przeglądarki" in d for d in result["differences"])
    assert result["hosts_only_a"] == ["googleads.g.doubleclick.net"] or result["hosts_only_b"] == ["googleads.g.doubleclick.net"]
    assert a.raw["observation"]["time_source"] == "har.entries"
    assert a.raw["observation"]["context"]["browser"] in ("Microsoft Edge", "Google Chrome")


def test_same_domain_with_other_path_and_params_is_only_domain_match(tmp_path):
    a, b = imported(tmp_path, "d", [
        ("a.har", har("https://dwie-twarze.example/oferta?x=1", OFFER, "2026-10-20T10:00:00Z")),
        ("b.har", har("https://dwie-twarze.example/inna?y=2", WHITE, "2026-10-21T10:00:00Z")),
    ])
    result = compare(a, b)
    assert result["url_match"] == "domain" and result["hypotheses"] == []
    assert any("innego adresu" in limit for limit in result["limitations"])
    assert result["seconds_between"] == 86400


def test_normalized_url_ignores_order_but_keeps_every_value():
    assert normalize_url("HTTPS://Dwie-Twarze.example:443/?b=2&a=1#x") == normalize_url("https://dwie-twarze.example/?a=1&b=2")
    assert normalize_url("https://dwie-twarze.example/?a=1&b=2") != normalize_url("https://dwie-twarze.example/?a=1&b=3")


def test_missing_metadata_is_unknown_not_absent(tmp_path):
    a, b = imported(tmp_path, "m", [("a.har", har(URL, OFFER, "2026-10-20T12:03:42Z")), ("b.har", har(URL, OFFER, ""))])
    assert b.raw["observation"]["time_source"] == "" and b.raw["observation"]["captured_at"] == ""
    a.raw.pop("observation")
    a.save()
    result = compare(a, b)
    assert result["url_match"] == "unknown" and result["seconds_between"] is None
    assert any("brak zapisu obserwacji" in limit for limit in result["limitations"])


def test_duplicate_capture_is_identical(tmp_path):
    a, b = imported(tmp_path, "dup", [("a.har", har(URL, OFFER, "2026-10-20T12:00:00Z")), ("b.har", har(URL, OFFER, "2026-10-20T12:00:30Z"))])
    result = compare(a, b)
    assert result["verdict"] == "identical" and result["hypotheses"] == []


def test_same_title_different_text_is_flagged_as_misleading(tmp_path):
    fake = WHITE.replace("Portal analiz", "Oferta dnia")
    a, b = imported(tmp_path, "t", [("a.har", har(URL, OFFER, "2026-10-20T12:00:00Z")), ("b.har", har(URL, fake, "2026-10-20T12:01:00Z"))])
    result = compare(a, b)
    assert result["verdict"] == "different"
    assert any("zgodny tytuł bywa mylący" in d for d in result["differences"])


def test_secrets_are_redacted_in_the_observation():
    info = observation_info("https://dwie-twarze.example/?access_token=EAATESTfake0000000000000000000000tokenZ&x=1", "", "", None)
    assert "EAATESTfake" not in json.dumps(info)
    assert "access_token=sha256-" in info["exact_url"] and info["time_source"] == ""


def test_local_file_har_is_ignored(tmp_path):
    local = har("https://www.googletagmanager.com/a?id=G-TEST", "", "2026-10-20T11:55:07Z")
    local["log"]["pages"][0]["title"] = "file:///C:/Users/kto/Downloads/strona.html"
    case = case_with(tmp_path, "1", [(".har", local)])
    assert bundle.discover(case).pages == []
