import csv
import json

import pytest
from django.core.management import call_command

from ads.models import Ad
from collectors import bundle
from tests.test_bundle import ARTICLE_X, article_html, make_case, run

pytestmark = pytest.mark.django_db


def test_export_writes_ads_edges_groups_without_secrets(tmp_path):
    for name, domain in (("1", "civic.example"), ("2", "across.example")):
        run(bundle.import_case(make_case(tmp_path / "paczka", name, domain, "Zamach na biznesmena", ARTICLE_X), bundle="t"))
    leak = tmp_path / "paczka" / "36"
    leak.mkdir()
    url = "https://summit.example/?access_token=EAATESTfake00000000000000000000tokenB&ad_id=120000000000000003"
    (leak / "Summit.html").write_text(article_html(url, "Szczyt", ARTICLE_X), encoding="utf-8")
    run(bundle.import_case(leak, bundle="t"))

    out = tmp_path / "eksport"
    call_command("export_corpus", str(out))

    ads = [json.loads(line) for line in (out / "reklamy.jsonl").read_text(encoding="utf-8").splitlines()]
    edges = [json.loads(line) for line in (out / "krawedzie.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(ads) == Ad.objects.count() == 3
    first = next(a for a in ads if a["external_id"] == "t/1/civic.example")
    assert first["case"] == "1" and first["campaign"] and first["operator"]
    kinds = {m["kind"] for m in first["markers"]}
    assert {"domain", "funnel_id", "kit_path"} <= kinds
    assert not kinds & {"dom_band", "text_band", "page_text_band", "image_band"}

    pair = next(e for e in edges if {e["ad_a_external_id"], e["ad_b_external_id"]} == {"t/1/civic.example", "t/2/across.example"})
    assert pair["relation"] == "same_campaign"
    assert pair["evidence"] and all({"kind", "weight_bits", "df"} <= set(ev) for ev in pair["evidence"])

    with (out / "grupy.csv").open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert {r["external_id"] for r in rows} == {a["external_id"] for a in ads}

    everything = "".join(p.read_text(encoding="utf-8") for p in out.iterdir())
    assert "EAATESTfake00000000" not in everything
    summary = json.loads((out / "opis.json").read_text(encoding="utf-8"))
    assert summary["reklamy"] == 3 and summary["krawedzie"]["same_campaign"] >= 1


def test_export_endpoint_returns_zip_and_filters_by_source(tmp_path):
    import io
    import zipfile

    from rest_framework.test import APIClient

    run(bundle.import_case(make_case(tmp_path / "p", "1", "civic.example", "Zamach", ARTICLE_X), bundle="t"))
    Ad.objects.create(source="microsoft", external_id="ms-1", title="Legalna reklama")
    client = APIClient()
    response = client.get("/api/export?source=capture")
    assert response.status_code == 200 and response["Content-Type"] == "application/zip"
    assert "attachment" in response["Content-Disposition"]
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        names = set(archive.namelist())
        ads = archive.read("korpus/reklamy.jsonl").decode("utf-8").splitlines()
    assert {"korpus/reklamy.jsonl", "korpus/krawedzie.jsonl", "korpus/grupy.csv", "korpus/opis.json"} <= names
    assert len(ads) == 1 and "ms-1" not in ads[0]
    with zipfile.ZipFile(io.BytesIO(client.get("/api/export").content)) as archive:
        assert len(archive.read("korpus/reklamy.jsonl").decode("utf-8").splitlines()) == 2
    assert client.get("/api/export?source=nie-ma").status_code == 400
