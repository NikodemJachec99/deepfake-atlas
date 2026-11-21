"""Pakiet dowodowy operatora i kampanii. Dane zmyślone, z importu spraw na wspólnym zapleczu."""

import hashlib
import io
import json
import subprocess
import sys
import zipfile
from datetime import UTC

import pytest
from PIL import Image
from rest_framework.test import APIClient

from ads.models import Ad
from collectors import bundle
from evidence import store
from evidence.models import Artifact, AuditLog
from similarity import package
from similarity.models import Campaign, Operator, OperatorMembership
from tests.test_bundle import ARTICLE_X, article_html, make_case, run

pytestmark = pytest.mark.django_db

TOKEN = "EAATESTfake00000000000000000000tokenB"
XSS = "<img src=x onerror=alert(1)>"


def png(color: str = "red") -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (64, 48), color).save(out, "PNG")
    return out.getvalue()


@pytest.fixture
def operator(tmp_path):
    """Dwie sprawy na wspólnym zapleczu plus trzecia z tokenem w adresie, wszystkie w jednym operatorze."""
    for name, domain in (("1", "civic.example"), ("2", "across.example")):
        run(bundle.import_case(make_case(tmp_path / "paczka", name, domain, "Zamach na biznesmena", ARTICLE_X), bundle="t"))
    leak = tmp_path / "paczka" / "36"
    leak.mkdir()
    url = f"https://summit.example/?access_token={TOKEN}&ad_id=120000000000000003"
    (leak / "Summit.html").write_text(article_html(url, "Szczyt", ARTICLE_X), encoding="utf-8")
    run(bundle.import_case(leak, bundle="t"))
    group = Operator.objects.first()
    ads = list(Ad.objects.order_by("id"))
    for ad in ads:
        OperatorMembership.objects.update_or_create(ad=ad, defaults={"operator": group})
    # Zrzuty reklam: prawdziwe obrazy w magazynie, podpięte do reklam tak jak robi to import.
    for ad, color in zip(ads, ("red", "blue", "green"), strict=True):
        artifact = store.put(png(color), kind="creative_image", source_url=f"zrzut-{color}.png")
        ad.raw = {**ad.raw, "creatives": [artifact.sha256]}
        ad.save(update_fields=["raw"])
    ads[0].title = XSS
    ads[0].save(update_fields=["title"])
    return group


def fetch(client, url, **params):
    response = client.get(url, params)
    assert response.status_code == 200, getattr(response, "content", b"")[:300]
    assert response["Content-Type"] == "application/zip"
    return b"".join(response.streaming_content), response


def unpack(content: bytes, target):
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        names = archive.namelist()
        archive.extractall(target)
    root = names[0].split("/")[0]
    assert all(n.startswith(root + "/") for n in names)
    return target / root, names


def verify(root, *args):
    return subprocess.run([sys.executable, "-I", str(root / "weryfikuj.py"), *args], capture_output=True, text=True, encoding="utf-8")


def test_zip_has_all_parts_and_verifies_with_the_shipped_script(operator, tmp_path):
    content, response = fetch(APIClient(), f"/api/operators/{operator.pk}/package")
    assert "attachment" in response["Content-Disposition"]
    assert f"scamdna-pakiet-{operator.key}-" in response["Content-Disposition"] and ".zip" in response["Content-Disposition"]
    root, names = unpack(content, tmp_path / "out")
    relative = {n.split("/", 1)[1] for n in names if not n.endswith("/")}
    assert {"raport.html", "manifest.json", "SHA256SUMS", "weryfikuj.py", "stix.json", "krawedzie.jsonl", "os-czasu.json"} <= relative
    assert any(r.startswith("dowody/obrazy/") for r in relative)
    assert any(r.startswith("dowody/surowe/") and r.endswith(".html.txt") for r in relative)
    assert any(r.startswith("dowody/surowe/") and r.endswith(".har") for r in relative)
    assert "dowody/surowe/OSTRZEZENIE.txt" in relative

    result = verify(root)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "ZGODNE" in result.stdout

    # SHA256SUMS w formacie sha256sum: suma, dwie spacje, ścieżka. Każdy plik poza nim jest wymieniony.
    sums = dict(line.split("  ", 1)[::-1] for line in (root / "SHA256SUMS").read_text(encoding="utf-8").splitlines())
    assert set(sums) == relative - {"SHA256SUMS"}
    for path, digest in sums.items():
        assert hashlib.sha256((root / path).read_bytes()).hexdigest() == digest


def test_verify_script_detects_changed_missing_and_extra_files(operator, tmp_path):
    content, _ = fetch(APIClient(), f"/api/operators/{operator.pk}/package")
    root, names = unpack(content, tmp_path / "out")
    image = next(root.glob("dowody/obrazy/*"))
    image.write_bytes(image.read_bytes() + b"x")
    (root / "dodatkowy.txt").write_text("obcy plik", encoding="utf-8")
    (root / "stix.json").unlink()
    result = verify(root)
    assert result.returncode == 1
    assert "ZŁA SUMA" in result.stdout and "PLIK SPOZA LISTY: dodatkowy.txt" in result.stdout and "BRAK PLIKU: stix.json" in result.stdout


def test_verify_script_rejects_paths_outside_the_package(operator, tmp_path):
    content, _ = fetch(APIClient(), f"/api/operators/{operator.pk}/package")
    root, _ = unpack(content, tmp_path / "out")
    outside = tmp_path / "poza.txt"
    outside.write_text("x", encoding="utf-8")
    sums = (root / "SHA256SUMS").read_text(encoding="utf-8")
    (root / "SHA256SUMS").write_text(sums + f"{hashlib.sha256(b'x').hexdigest()}  ../../poza.txt\n", encoding="utf-8")
    result = verify(root)
    assert result.returncode == 1 and "niedozwolona ścieżka" in result.stdout


def test_manifest_describes_every_evidence_file(operator, tmp_path):
    content, _ = fetch(APIClient(), f"/api/operators/{operator.pk}/package")
    root, _ = unpack(content, tmp_path / "out")
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["grupa"] == {"typ": "operator", "klucz": operator.key, "id": operator.pk, "reklam": 3}
    assert manifest["model"] and manifest["format"] == 1 and manifest["pominiete"] == []
    assert {a["external_id"] for a in manifest["reklamy"]} == set(Ad.objects.values_list("external_id", flat=True))
    kinds = set()
    for item in manifest["pliki"]:
        artifact = Artifact.objects.get(pk=item["sha256"])
        data = (root / item["sciezka"]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == item["sha256"] and len(data) == item["rozmiar"] == artifact.size
        assert item["sciezka"].split("/")[-1].split(".")[0] == item["sha256"]
        assert item["czas_pozyskania"] == artifact.created_at.astimezone(UTC).isoformat(timespec="seconds")
        assert item["rodzaj"] == artifact.kind and item["reklamy"]
        kinds.add(item["rodzaj"])
    assert {"creative_image", "har"} <= kinds and any(k.startswith("html") for k in kinds)
    html = next(i for i in manifest["pliki"] if i["rodzaj"].startswith("html"))
    assert html["zrodlo"].startswith("https://") and TOKEN not in html["zrodlo"]
    assert {p["sciezka"] for p in manifest["pliki_pakietu"]} >= {"raport.html", "stix.json", "krawedzie.jsonl", "os-czasu.json", "weryfikuj.py"}


def test_generated_files_have_no_tokens_but_raw_files_stay_byte_exact(operator, tmp_path):
    content, _ = fetch(APIClient(), f"/api/operators/{operator.pk}/package")
    root, _ = unpack(content, tmp_path / "out")
    generated = [p for p in root.rglob("*") if p.is_file() and "dowody" not in p.relative_to(root).parts[:1]]
    assert generated
    for path in generated:
        assert TOKEN.encode() not in path.read_bytes(), path.name
    # Surowy zapis strony nie jest redagowany, bo redakcja zmieniłaby jego sumę i zerwała łańcuch dowodu.
    raw = [p for p in (root / "dowody" / "surowe").glob("*.html.txt") if TOKEN.encode() in p.read_bytes()]
    assert raw
    warning = (root / "dowody" / "surowe" / "OSTRZEZENIE.txt").read_text(encoding="utf-8")
    assert "nie otwieraj" in warning.lower() and "tokeny" in warning


def test_report_is_self_contained_escaped_and_never_renders_page_html(operator, tmp_path):
    content, _ = fetch(APIClient(), f"/api/operators/{operator.pk}/package")
    root, _ = unpack(content, tmp_path / "out")
    report = (root / "raport.html").read_text(encoding="utf-8")
    # Treść strony oszusta istnieje tylko jako plik w dowody/surowe.
    assert "Znany biznesmen został zaatakowany" not in report and "Akapit 1" not in report and "saved from url" not in report
    assert any("Znany biznesmen" in p.read_text(encoding="utf-8") for p in (root / "dowody" / "surowe").glob("*.html.txt"))
    # Dane z reklam są wyłączone z interpretacji jako HTML.
    assert XSS not in report and "&lt;img src=x onerror=alert(1)&gt;" in report
    # Bez zewnętrznych zasobów i skryptów, obrazy osadzone.
    assert "<script" not in report and 'src="http' not in report and 'href="http' not in report and "url(http" not in report
    assert "data:image/jpeg;base64," in report
    for heading in ("Streszczenie", "najmocniejsze dowody", "Najsłabszy punkt", "Oś czasu", "Reklamy", "Zrzuty", "weryfikacja", "Metoda", "Ograniczenia"):
        assert heading in report, heading
    assert operator.key in report and "civic.example" in report and "across.example" in report
    assert "python weryfikuj.py" in report


def test_report_shows_strongest_evidence_with_bits_and_artifact_files(operator, tmp_path):
    content, _ = fetch(APIClient(), f"/api/operators/{operator.pk}/package")
    root, _ = unpack(content, tmp_path / "out")
    report = (root / "raport.html").read_text(encoding="utf-8")
    edges = [json.loads(line) for line in (root / "krawedzie.jsonl").read_text(encoding="utf-8").splitlines()]
    assert edges
    best = max((ev for e in edges for ev in e["evidence"]), key=lambda ev: ev["weight_bits"])
    assert f"{best['weight_bits']:.1f}".replace(".", ",") in report
    for edge in edges:
        assert {"relation", "probability", "bits", "model_version", "verdict"} <= set(edge)
        for ev in edge["evidence"]:
            assert {"artifact_a", "artifact_b", "raw_bits", "weight_bits", "df", "corpus_n"} <= set(ev)
    assert "Najmocniejsze pary reklam" in report


def test_stix_is_narrowed_to_the_group(operator, tmp_path):
    other = Operator.objects.create()
    ad = Ad.objects.create(source="capture", external_id="inny")
    OperatorMembership.objects.create(ad=ad, operator=other)
    content, _ = fetch(APIClient(), f"/api/operators/{operator.pk}/package")
    root, _ = unpack(content, tmp_path / "out")
    data = json.loads((root / "stix.json").read_text(encoding="utf-8"))
    assert data["type"] == "bundle"
    sets = [o for o in data["objects"] if o["type"] == "intrusion-set"]
    assert [s["x_scamdna_key"] for s in sets] == [operator.key]
    assert any(o["type"] == "indicator" for o in data["objects"])


def test_campaign_package(operator, tmp_path):
    campaign = Campaign.objects.first()
    content, response = fetch(APIClient(), f"/api/campaigns/{campaign.pk}/package")
    assert f"scamdna-pakiet-{campaign.key}-" in response["Content-Disposition"]
    root, _ = unpack(content, tmp_path / "out")
    assert verify(root).returncode == 0
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["grupa"]["typ"] == "campaign" and manifest["grupa"]["klucz"] == campaign.key
    assert "kampanii" in (root / "raport.html").read_text(encoding="utf-8")


def test_raw_files_can_be_left_out(operator, tmp_path):
    content, _ = fetch(APIClient(), f"/api/operators/{operator.pk}/package", surowe="0")
    root, names = unpack(content, tmp_path / "out")
    assert not (root / "dowody" / "surowe").exists()
    assert (root / "dowody" / "obrazy").exists()
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["pominiete"] and all("surowe=0" in p["powod"] for p in manifest["pominiete"])
    assert "pominięcia plików surowych" in (root / "raport.html").read_text(encoding="utf-8")
    assert verify(root).returncode == 0


def test_oversized_and_corrupted_files_are_listed_as_skipped(operator, tmp_path, monkeypatch):
    shas = list(Artifact.objects.filter(kind="creative_image").order_by("pk").values_list("pk", flat=True))
    big, bad = shas[0], shas[1]
    Artifact.objects.filter(pk=big).update(size=package.MAX_FILE_BYTES + 1)
    real_get = store.get
    monkeypatch.setattr(store, "get", lambda sha: b"podmieniona tresc" if sha == bad else real_get(sha))
    content, _ = fetch(APIClient(), f"/api/operators/{operator.pk}/package")
    root, _ = unpack(content, tmp_path / "out")
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    skipped = {p["sha256"]: p["powod"] for p in manifest["pominiete"]}
    assert "limit pakietu" in skipped[big] and "uszkodzony" in skipped[bad]
    assert big not in {p["sha256"] for p in manifest["pliki"]} and bad not in {p["sha256"] for p in manifest["pliki"]}
    assert not list(root.glob(f"dowody/obrazy/{big}*")) and not list(root.glob(f"dowody/obrazy/{bad}*"))
    report = (root / "raport.html").read_text(encoding="utf-8")
    assert "Pliki pominięte" in report and big in report
    assert verify(root).returncode == 0


def test_unreadable_images_do_not_break_the_report(operator, tmp_path):
    fake = store.put(b"\x89PNG\r\nto nie jest obraz", kind="creative_image", source_url="zepsuty.png")
    ad = Ad.objects.order_by("id").first()
    ad.raw = {**ad.raw, "creatives": [*ad.raw["creatives"], fake.sha256]}
    ad.save(update_fields=["raw"])
    content, _ = fetch(APIClient(), f"/api/operators/{operator.pk}/package")
    root, _ = unpack(content, tmp_path / "out")
    assert (root / "dowody" / "obrazy" / f"{fake.sha256}.png").exists()
    assert verify(root).returncode == 0


def test_unknown_empty_and_bad_requests(operator):
    client = APIClient()
    assert client.get("/api/operators/999999/package").status_code == 404
    assert client.get("/api/campaigns/999999/package").status_code == 404
    empty = Operator.objects.create()
    response = client.get(f"/api/operators/{empty.pk}/package")
    assert response.status_code == 404 and "nie ma żadnej reklamy" in response.json()["detail"]
    assert client.get(f"/api/operators/{operator.pk}/package?surowe=tak").status_code == 400


def test_download_is_written_to_the_audit_log(operator):
    fetch(APIClient(), f"/api/operators/{operator.pk}/package")
    row = AuditLog.objects.get(action="package")
    assert row.object_type == "operator" and row.object_id == operator.key
    assert row.payload["files"] > 5 and row.payload["raw"] is True


def favicon_on_edge(operator):
    """Dowód krawędzi z faviconami, których nie ma w polach reklam (tylko w EdgeEvidence)."""
    from similarity.models import Edge, EdgeEvidence

    edge = Edge.objects.filter(ad_a__operator_membership__operator=operator, ad_b__operator_membership__operator=operator).first()
    assert edge is not None
    ico = b"\x00\x00\x01\x00" + b"ikona-a" * 4
    icon_a = store.put(ico, kind="favicon", source_url="https://civic.example/favicon.ico")
    icon_b = store.put(ico + b"b", kind="favicon", source_url="https://across.example/favicon.ico")
    EdgeEvidence.objects.create(
        edge=edge, family="infra", kind="favicon_hash", value_a="aa", value_b="aa",
        raw_bits=7.0, weight_bits=3.0, artifact_a=icon_a, artifact_b=icon_b,
    )
    return icon_a, icon_b, edge


def test_edge_evidence_artifacts_such_as_favicons_are_packaged(operator, tmp_path):
    icon_a, icon_b, edge = favicon_on_edge(operator)
    content, _ = fetch(APIClient(), f"/api/operators/{operator.pk}/package")
    root, _ = unpack(content, tmp_path / "out")
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    stored = {p["sha256"]: p for p in manifest["pliki"]}
    for icon, ad in ((icon_a, edge.ad_a_id), (icon_b, edge.ad_b_id)):
        assert icon.sha256 in stored and stored[icon.sha256]["rodzaj"] == "favicon"
        assert (root / stored[icon.sha256]["sciezka"]).read_bytes() == store.get(icon.sha256)
        assert ad in [r["id"] for r in stored[icon.sha256]["reklamy"]]
    rows = [json.loads(line) for line in (root / "krawedzie.jsonl").read_text(encoding="utf-8").splitlines()]
    fav = [e for row in rows for e in row["evidence"] if e["artifact_a"] == icon_a.sha256]
    assert fav and fav[0]["artifact_a_file"] == stored[icon_a.sha256]["sciezka"]
    result = verify(root)
    assert result.returncode == 0, result.stdout
    assert "zgodna z chwilą utworzenia pakietu" in result.stdout and "X-Package-SHA256" in result.stdout


def test_verify_script_fails_when_edge_evidence_points_outside_the_package(operator, tmp_path):
    icon_a, _, _ = favicon_on_edge(operator)
    content, _ = fetch(APIClient(), f"/api/operators/{operator.pk}/package")
    root, _ = unpack(content, tmp_path / "out")
    assert verify(root).returncode == 0
    # Dowód wskazuje artefakt, którego nie ma ani w pliku, ani w pominiętych.
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["pliki"] = [p for p in manifest["pliki"] if p["sha256"] != icon_a.sha256]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    result = verify(root)
    assert result.returncode == 1 and icon_a.sha256 in result.stdout and "nie ma go" not in result.stdout.split("NIEZGODNOŚCI")[0]
    # Z powodem na liście pominięć to już nie błąd tego rodzaju.
    manifest["pominiete"].append({"sha256": icon_a.sha256, "rodzaj": "favicon", "rozmiar": 1, "powod": "test"})
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    assert "dowód wskazuje artefakt" not in verify(root).stdout


def test_whole_zip_sha256_is_in_the_header_and_audit_log(operator):
    content, response = fetch(APIClient(), f"/api/operators/{operator.pk}/package")
    assert response["X-Package-SHA256"] == hashlib.sha256(content).hexdigest()
    assert AuditLog.objects.filter(action="package").latest("pk").payload["sha256"] == response["X-Package-SHA256"]
