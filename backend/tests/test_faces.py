import pytest

from ads.models import Ad
from collectors import bundle
from evidence.models import AdMarker
from people import faces
from people.models import Person
from similarity.fusion import Shared, score_pair
from tests.test_bundle import ARTICLE_X, make_case, run

pytestmark = pytest.mark.django_db


def unit(*values):
    norm = sum(v * v for v in values) ** 0.5
    return [v / norm for v in values]


REFS = [{"name": "Jan Testowy", "embedding": unit(1, 0, 0)}, {"name": "Anna Przykładowa", "embedding": unit(0, 1, 0)}]


def test_face_matches_only_above_threshold(monkeypatch):
    monkeypatch.setattr(faces, "embeddings", lambda data: [((10, 10, 80, 80), unit(0.9, 0.1, 0)), ((200, 10, 80, 80), unit(0, 0, 1))])
    found = faces.match_faces(b"obraz", REFS)
    assert [(f.name, f.box) for f in found] == [("Jan Testowy", (10, 10, 80, 80))]
    assert found[0].score > faces.MATCH_THRESHOLD


def test_screenshot_with_a_known_face_gives_a_person_marker(tmp_path, monkeypatch):
    monkeypatch.setattr(faces, "references", lambda: REFS)
    monkeypatch.setattr(faces, "embeddings", lambda data: [((10, 10, 80, 80), unit(0, 1, 0.05))])
    case = make_case(tmp_path, "7", "twarz.example", "Artykuł z twarzą", ARTICLE_X, screenshot=True)
    run(bundle.import_case(case, bundle="t"))
    ad = Ad.objects.get()
    link = AdMarker.objects.select_related("marker").get(ad=ad, marker__kind="face_match")
    person = Person.objects.get(name="Anna Przykładowa")
    assert link.marker.value == person.marker_value and link.marker.family == "pers"
    assert link.detail["name"] == "Anna Przykładowa" and link.detail["score"] > 0.9


def test_missing_model_does_not_break_the_analysis(tmp_path, settings, monkeypatch):
    settings.MODELS_DIR = tmp_path / "brak-modeli"
    monkeypatch.setattr(faces, "references", lambda: REFS)
    assert faces.available() is False
    assert faces.match_faces(b"\x89PNG\r\n", REFS) == []
    case = make_case(tmp_path, "8", "bez-modelu.example", "Artykuł", ARTICLE_X, screenshot=True)
    run(bundle.import_case(case, bundle="t"))
    assert not AdMarker.objects.filter(marker__kind="face_match").exists()


def test_the_same_face_is_a_motif_not_proof_of_a_common_source():
    result = score_pair(shared=[Shared("face_match", "person:1", df=2), Shared("kit_path", "GET /sdk/main.js", df=2)], soft=[], corpus_n=1000)
    assert result.relation != "same_operator" and result.relation != "same_campaign"
