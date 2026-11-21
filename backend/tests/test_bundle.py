"""Import przechwyceń w formacie paczki organizatora. Dane w testach są zmyślone, format jest prawdziwy."""

import io
import json
import zipfile

import pytest
from rest_framework.test import APIClient

from ads.models import Ad, Analysis
from collectors import bundle
from evidence.models import Marker
from extractors import ocr
from people.models import Person
from similarity.models import Campaign, Edge, Operator
from tests.test_capture import PAGE, funnel_har
from workflows import pipeline

pytestmark = pytest.mark.django_db

ARTICLE_X = "Znany biznesmen został zaatakowany wieczorem w centrum miasta, a świadkowie mówią o strzałach."
ARTICLE_Y = "Dziennikarza wyprowadzono ze studia w kajdankach zaraz po emisji programu o wielkich pieniądzach."


def article_html(url: str, title: str, sentence: str) -> str:
    body = "".join(f"<p class='akapit'>{sentence} Akapit {i}.</p>" for i in range(30))
    return f"<!DOCTYPE html>\n<!-- saved from url=({len(url):04d}){url} -->\n<html><head><title>{title}</title></head><body>{body}</body></html>"


def make_case(root, name, domain, title, sentence, *, ip="203.0.113.7", screenshot=False):
    case = root / name
    case.mkdir(parents=True)
    url = PAGE.replace("zysk-a.example", domain)
    (case / f"{title}.html").write_text(article_html(url, title, sentence), encoding="utf-8")
    files = case / f"{title}_files"
    files.mkdir()
    (files / "saved_resource.html").write_text("<html><body>ramka</body></html>", encoding="utf-8")
    (files / "manifest.json").write_text('{"name": "PWA"}', encoding="utf-8")
    (case / f"{domain}.har").write_text(json.dumps(funnel_har(domain, ip)), encoding="utf-8")
    if screenshot:
        (case / "Zrzut ekranu 2026-10-09.png").write_bytes(b"\x89PNG\r\n" + name.encode())
    return case


def run(analyses):
    for analysis in analyses:
        pipeline.run_all(str(analysis.pk))
        analysis.refresh_from_db()
        assert analysis.status == Analysis.Status.DONE, analysis.error
    return analyses


def test_discover_pairs_saved_page_with_its_har_and_ignores_resources(tmp_path):
    case = make_case(tmp_path, "1", "civic.example", "Zamach na biznesmena — Gazeta.pl", ARTICLE_X, screenshot=True)
    found = bundle.discover(case)
    assert found.case == "1"
    assert len(found.pages) == 1
    page = found.pages[0]
    assert page.slug == "civic.example"
    assert page.url.startswith("https://civic.example/?utm_id=")
    assert page.har is not None and b"Zamach na biznesmena" in page.html
    assert [p.name for p in found.creatives] == ["Zrzut ekranu 2026-10-09.png"]


def test_two_hars_in_one_case_are_two_pages(tmp_path):
    case = make_case(tmp_path, "2", "across.example", "Zamach na biznesmena — Gazeta.pl", ARTICLE_X)
    (case / "healthlink.example.har").write_text(json.dumps(funnel_har("healthlink.example")), encoding="utf-8")
    assert sorted(p.slug for p in bundle.discover(case).pages) == ["across.example", "healthlink.example"]


def test_subdirectories_with_pages_and_page_capture_format(tmp_path):
    case = tmp_path / "61"
    make_case(case, "strona_1", "glow.example", "Portal analiz", ARTICLE_Y)
    capture = case / "strona_2" / "wewnatrz"
    capture.mkdir(parents=True)
    (capture / "manifest.json").write_text(json.dumps({"tool": "page-capture 0.1.0", "page_url": "https://inept.example/?pxl=1000000000000002", "captured_at": "2026-10-12T09:48:17+00:00"}))
    (capture / "page.har").write_text(json.dumps(funnel_har("inept.example")), encoding="utf-8")
    (capture / "dom.html").write_text(article_html("https://inept.example/", "Suplement", ARTICLE_X), encoding="utf-8")
    (case / "reklama_1.png").write_bytes(b"\x89PNG\r\nreklama")
    found = bundle.discover(case)
    assert sorted(p.slug for p in found.pages) == ["inept.example", "strona-1-glow.example"]
    assert len(found.creatives) == 1
    captured = next(p for p in found.pages if p.slug == "inept.example")
    assert captured.har is not None and b"Suplement" in captured.html and captured.captured_at.startswith("2026-10-12")


def test_nask_archive_adds_certificate_without_overriding_the_live_capture(tmp_path):
    case = make_case(tmp_path, "p1", "dorq.example", "Zamach na biznesmena — Gazeta.pl", ARTICLE_X)
    archive = case / "archive_dorq.example_20261008_090940"
    (archive / "html").mkdir(parents=True)
    (archive / "archive_info.json").write_text(json.dumps({"url": "https://dorq.example/?utm_visit=1", "timestamp_utc": "2026-10-08T09:09:43"}))
    (archive / "html" / "rendered.html").write_text("<html><head><title>502: Bad gateway</title></head></html>")
    (archive / "network.har").write_text(json.dumps({"log": {"entries": []}}))
    (archive / "dns_ssl.json").write_text(
        json.dumps({"ip": "104.21.0.1", "all_addresses": ["104.21.0.1", "203.0.113.50"], "ssl": {"serialNumber": "0A1B2C3D4E5F6071", "notBefore": "Oct  7 18:53:02 2026 GMT"}})
    )
    (case / "archive_dorq.example_20261008_090940.zip").write_bytes(b"PK")
    found = bundle.discover(case)
    assert len(found.pages) == 1
    page = found.pages[0]
    assert b"Zamach na biznesmena" in page.html  # zapis z przeglądarki ma pierwszeństwo przed stroną błędu
    kinds = {(kind, value) for kind, value, _ in page.observations}
    assert ("tls_serial", "0a1b2c3d4e5f6071") in kinds
    assert ("cdn", "cloudflare") in kinds and ("ip", "203.0.113.50") in kinds


def test_same_engine_same_story_is_a_campaign_and_other_story_is_the_same_operator(tmp_path, monkeypatch):
    monkeypatch.setattr(ocr, "read_image", lambda path: ["Jasny Poranek Media", "Sponsorowane", "NA ŻYWO", "Historia, o której mówi cały kraj"])
    Person.objects.create(name="Jan Testowy")
    cases = [
        make_case(tmp_path, "1", "civic.example", "Zamach na biznesmena — Gazeta.pl", ARTICLE_X + " Jana Testowego nie było.", screenshot=True),
        make_case(tmp_path, "2", "across.example", "Zamach na biznesmena — Gazeta.pl", ARTICLE_X + " Jana Testowego nie było.", ip="198.51.100.9"),
        make_case(tmp_path, "48", "novum.example", "Po programie zatrzymano prowadzącego", ARTICLE_Y, ip="192.0.2.44"),
    ]
    analyses = []
    for case in cases:
        analyses += run(bundle.import_case(case, bundle="nask"))

    ads = {ad.labels["case"]: ad for ad in Ad.objects.all()}
    assert set(ads) == {"1", "2", "48"}
    assert ads["1"].source == "capture" and ads["1"].external_id == "nask/1/civic.example"
    assert ads["1"].title == "Zamach na biznesmena — Gazeta.pl"
    assert "mówi cały kraj" in ads["1"].text  # treść reklamy ze zrzutu
    assert analyses[0].result["crawl"] == {"pages": 1, "offline": True}
    assert analyses[0].result["extract"]["people"] == ["Jan Testowy"]

    def edge(a, b):
        x, y = sorted((ads[a].pk, ads[b].pk))
        return Edge.objects.get(ad_a_id=x, ad_b_id=y)

    same_story = edge("1", "2")
    assert same_story.relation == Edge.Relation.SAME_CAMPAIGN
    kinds = {e.kind for e in same_story.evidence.all()}
    assert {"kit_path", "funnel_id", "url_param_keys", "page_text_minhash", "page_title", "brand_impersonated", "person_mention"} <= kinds
    assert "domain" not in kinds and "ip" not in kinds

    other_story = edge("1", "48")
    assert other_story.relation == Edge.Relation.SAME_OPERATOR
    assert "page_text_minhash" not in {e.kind for e in other_story.evidence.all()}

    campaign = Campaign.objects.get()
    assert set(campaign.memberships.values_list("ad_id", flat=True)) == {ads["1"].pk, ads["2"].pk}
    operator = Operator.objects.get()
    assert operator.memberships.count() == 3
    assert analyses[-1].result["cluster"]["operator"] == operator.key
    assert analyses[-1].result["cluster"]["campaign"] is None

    # Ślady z ruchu sieciowego i ze zrzutu reklamy są markerami tej samej reklamy.
    values = set(Marker.objects.filter(ad_markers__ad=ads["1"]).values_list("kind", "value"))
    assert ("page_name", "jasnyporanekmedia") in values and ("page_name", "civic") in values
    assert ("ip", "203.0.113.7") in values and ("asset_host", "vz-0a1b2c3d-123.b-cdn.net") in values
    assert not Marker.objects.filter(kind__in=["nameserver", "tls_fp", "favicon_hash"]).exists()  # nic nie pobieraliśmy na żywo


def test_ad_screenshot_parsing():
    feed = ocr.parse_ad_screenshot(["Jasny Poranek Media", "Sponsorowane", "NA ŻYWO", "BUS", "ŚRODA, 19:30 — KRAKÓW", "Dowiedz się więcej", "PL Historia, o której mówi cały kraj"])
    assert feed.advertiser == "Jasny Poranek Media"
    assert feed.text == "NA ŻYWO ŚRODA, 19:30 — KRAKÓW PL Historia, o której mówi cały kraj"
    assert [(o.kind, o.value) for o in feed.observations] == [("page_name", "jasnyporanekmedia")]

    inline = ocr.parse_ad_screenshot(["Sekret znanych osób dla każdego", "Sponsorowane - Blaskpiksel"])
    assert inline.advertiser == "Blaskpiksel" and inline.text == "Sekret znanych osób dla każdego"

    library = ocr.parse_ad_screenshot(["Link do reklamy", "Aktywna", "Identyfikator biblioteki: 4400000000000001", "Wyświetlenia: <100", "Słodka Wygrana", "Sponsorowane", "Dywanik łazienkowy 30x20"])
    assert library.library_ids == ["4400000000000001"]
    assert library.advertiser == "Słodka Wygrana"
    assert ("meta_ad_ref", "4400000000000001") in [(o.kind, o.value) for o in library.observations]
    assert library.text == "Dywanik łazienkowy 30x20"

    assert ocr.parse_ad_screenshot([]).observations == []


def test_case_with_only_an_ad_video_becomes_an_ad(tmp_path):
    case = tmp_path / "5"
    case.mkdir()
    (case / "Reklama [1900000000000002_3].mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42 wideo")
    (case / "Reklama [1900000000000002_3].info.json").write_text(
        json.dumps({"id": "1900000000000002_3", "playlist_id": "1900000000000002", "title": "Reklama wideo", "webpage_url": "https://www.facebook.com/ads/library/?id=1900000000000002"}),
        encoding="utf-8",
    )
    run(bundle.import_case(case, bundle="nask"))
    ad = Ad.objects.get()
    assert ad.external_id == "nask/5/reklama" and ad.title == "Reklama wideo" and ad.landing_url == ""
    assert ad.raw["library_url"].endswith("1900000000000002")
    assert Marker.objects.filter(kind="meta_ad_ref", value="1900000000000002").exists()
    assert Marker.objects.filter(kind="creative_sha256").count() == 1


def test_access_token_from_capture_is_redacted_everywhere(tmp_path):
    case = tmp_path / "36"
    case.mkdir()
    url = "https://summit.example/?fbpx=1500000000000003&access_token=EAATESTfake00000000000000000000tokenB&ad_id=120000000000000003"
    (case / "Summit.html").write_text(article_html(url, "Szczyt Inwestycyjny 2026", ARTICLE_Y), encoding="utf-8")
    analysis = run(bundle.import_case(case, bundle="nask"))[0]
    ad = Ad.objects.get()
    assert "EAATESTfake00000000" not in ad.landing_url and "access_token=sha256-" in ad.landing_url
    assert "EAATESTfake00000000" not in json.dumps(analysis.state)
    kinds = dict(Marker.objects.values_list("kind", "value"))
    assert kinds["capi_token"].startswith("sha256-") and kinds["meta_pixel"] == "1500000000000003"
    assert kinds["meta_ad_ref"] == "120000000000000003"


def test_case_dirs_handles_nested_bundle_and_single_case(tmp_path):
    root = tmp_path / "paczka" / "do_udostępnienia"
    for name in ("10", "2", "p3"):
        make_case(root, name, f"d{name}.example", "Tytuł strony testowej", ARTICLE_X)
    assert [p.name for p in bundle.case_dirs(tmp_path / "paczka")] == ["2", "10", "p3"]
    assert bundle.case_dirs(root / "2") == [root / "2"]


def zip_case(case_dir) -> io.BytesIO:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for path in case_dir.rglob("*"):
            if path.is_file():
                archive.write(path, path.relative_to(case_dir.parent))
    buffer.seek(0)
    buffer.name = "sprawa.zip"
    return buffer


def test_upload_of_a_case_archive_runs_analysis_and_links_to_known_ads(tmp_path):
    client = APIClient()
    first = client.post("/api/analyses/upload", {"files": [zip_case(make_case(tmp_path / "a", "1", "civic.example", "Zamach na biznesmena — Gazeta.pl", ARTICLE_X))]}, format="multipart")
    assert first.status_code == 201, first.content
    assert len(first.json()) == 1 and first.json()[0]["status"] == "done"

    case = make_case(tmp_path / "b", "2", "across.example", "Zamach na biznesmena — Gazeta.pl", ARTICLE_X, ip="198.51.100.9")
    loose = [open(path, "rb") for path in case.iterdir() if path.is_file()]
    second = client.post("/api/analyses/upload", {"files": loose}, format="multipart")
    assert second.status_code == 201, second.content
    result = second.json()[0]["result"]
    assert result["fuse"]["same_campaign"] == 1
    assert result["cluster"]["campaign"].startswith("K-") and result["cluster"]["operator"].startswith("O-")

    ad = client.get(f"/api/ads/{second.json()[0]['ad']}").json()
    assert ad["source"] == "capture" and ad["operator"].startswith("O-") and ad["case"] == "1"
    operators = client.get("/api/operators").json()["results"]
    assert operators[0]["size"] == 2
    detail = client.get(f"/api/operators/{operators[0]['id']}").json()
    assert len(detail["ads"]) == 2 and any(m["kind"] == "kit_path" for m in detail["core_markers"])
    graph = client.get(f"/api/graph?operator={operators[0]['id']}").json()
    assert len(graph["nodes"]) == 2 and graph["nodes"][0]["operator"] == operators[0]["key"]
    stats = client.get("/api/stats").json()
    assert stats["ads"] == 2 and stats["operators"] == 1 and stats["edges"] == {"same_campaign": 1}


def test_upload_rejects_empty_and_unsafe_archives():
    client = APIClient()
    assert client.post("/api/analyses/upload", {}, format="multipart").status_code == 400
    evil = io.BytesIO()
    with zipfile.ZipFile(evil, "w") as archive:
        archive.writestr("../../poza.html", "<html></html>")
    evil.seek(0)
    evil.name = "zly.zip"
    response = client.post("/api/analyses/upload", {"files": [evil]}, format="multipart")
    assert response.status_code == 400
    notes = io.BytesIO(b"to nie jest material")
    notes.name = "notatki.txt"
    assert client.post("/api/analyses/upload", {"files": [notes]}, format="multipart").status_code == 400


def test_creative_image_is_served_only_when_it_is_an_image(tmp_path, monkeypatch):
    monkeypatch.setattr(ocr, "read_image", lambda path: [])
    case = make_case(tmp_path, "1", "civic.example", "Zamach na biznesmena — Gazeta.pl", ARTICLE_X, screenshot=True)
    run(bundle.import_case(case, bundle="nask"))
    client = APIClient()
    ad = client.get(f"/api/ads/{Ad.objects.get().pk}").json()
    assert len(ad["creatives"]) == 1
    image = client.get(f"/api/artifacts/{ad['creatives'][0]}/image")
    assert image.status_code == 200 and image["Content-Type"] == "image/png"
    html_sha = next(m["artifact"] for f in ad["genome"] for m in f["markers"] if m["kind"] == "page_title")
    assert client.get(f"/api/artifacts/{html_sha}/image").status_code == 404


def test_page_capture_with_other_url_on_same_domain_is_a_separate_page(tmp_path):
    case = tmp_path / "70"
    case.mkdir()
    (case / "a.html").write_text(article_html("https://same.example/article-a", "Artykul A", ARTICLE_X), encoding="utf-8")
    capture = case / "zapis-b"
    capture.mkdir()
    (capture / "manifest.json").write_text(json.dumps({"tool": "page-capture 0.1.0", "page_url": "https://same.example/article-b", "captured_at": "2026-10-12T09:48:17+00:00"}))
    (capture / "page.har").write_text(json.dumps(funnel_har("same.example", "198.51.100.9")), encoding="utf-8")
    (capture / "dom.html").write_text(article_html("https://same.example/article-b", "Artykul B", ARTICLE_Y), encoding="utf-8")
    found = bundle.discover(case)
    assert sorted(p.url for p in found.pages) == ["https://same.example/article-a", "https://same.example/article-b"]
    page_b = next(p for p in found.pages if p.url.endswith("article-b"))
    page_a = next(p for p in found.pages if p.url.endswith("article-a"))
    assert page_b.captured_at.startswith("2026-10-12") and b"Artykul B" in page_b.html
    assert not page_a.captured_at and page_a.har is None


def test_page_capture_with_same_url_but_other_query_still_completes_the_page(tmp_path):
    case = tmp_path / "71"
    case.mkdir()
    (case / "a.html").write_text(article_html("https://same.example/article-a?x=1", "Artykul A", ARTICLE_X), encoding="utf-8")
    capture = case / "zapis"
    capture.mkdir()
    (capture / "manifest.json").write_text(json.dumps({"tool": "page-capture 0.1.0", "page_url": "https://same.example/article-a?y=2#top", "captured_at": "2026-10-12T09:48:17+00:00"}))
    (capture / "page.har").write_text(json.dumps(funnel_har("same.example")), encoding="utf-8")
    found = bundle.discover(case)
    assert len(found.pages) == 1 and found.pages[0].har is not None
