"""Podobieństwo znaczenia treści. Wektory podstawione w teście, treść zmyślona."""

import math

import pytest

from ads.models import Ad
from extractors import embedding
from similarity import service
from similarity.fusion import Soft, score_pair
from similarity.models import Edge

pytestmark = pytest.mark.django_db


def unit(angle_deg: float) -> list[float]:
    """Wektor 384 liczb na okręgu: kąt między wektorami daje zadany kosinus."""
    v = [0.0] * embedding.DIM
    v[0], v[1] = math.cos(math.radians(angle_deg)), math.sin(math.radians(angle_deg))
    return v


def ad_with(name: str, vector) -> Ad:
    return Ad.objects.create(external_id=f"t/{name}", text_embedding=vector)


def test_paraphrase_is_found_by_meaning_alone():
    a = ad_with("a", unit(0))
    b = ad_with("b", unit(20))   # kosinus ok. 0,94: ta sama opowieść innymi słowami
    c = ad_with("c", unit(80))   # kosinus ok. 0,17: o czym innym
    service.link_ad(a)
    edge = Edge.objects.get(ad_a=a, ad_b=b)
    evidence = {e.kind: e for e in edge.evidence.all()}
    assert edge.relation == "similar" and evidence["text_embedding"].similarity == pytest.approx(0.94, abs=0.01)
    assert not Edge.objects.filter(ad_b=c).exists()


def test_meaning_alone_never_proves_a_common_source():
    result = score_pair([], [Soft("text_embedding", 0.99)], 1000)
    assert result.relation == "similar" and result.families["narr"] <= 5


def test_short_text_and_missing_model_give_no_vector(settings, tmp_path):
    assert embedding.embed("za krótko") is None
    settings.MODELS_DIR = tmp_path / "brak"
    assert embedding.available() is False
    assert embedding.embed("Długi tekst artykułu o inwestycjach. " * 20) is None
