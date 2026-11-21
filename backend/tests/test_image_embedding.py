"""Podobne ujęcie z wektora obrazu. Model podstawiony atrapą (wektor z pierwszego bajtu pliku), obrazy zmyślone."""

import io
import math

import pytest
from PIL import Image

from ads.models import Ad
from evidence import store
from extractors import image_embedding
from similarity import service
from similarity.fusion import Soft, score_pair
from similarity.models import Edge

pytestmark = pytest.mark.django_db


def unit(angle_deg: float) -> list[float]:
    v = [0.0] * image_embedding.DIM
    v[0], v[1] = math.cos(math.radians(angle_deg)), math.sin(math.radians(angle_deg))
    return v


def picture(seed: int) -> bytes:
    """Szum 200x200 w PNG: dość duży, żeby przejść progi rozmiaru. Pierwszy piksel niesie numer ujęcia dla atrapy."""
    import random

    rng = random.Random(seed)
    image = Image.new("RGB", (200, 200))
    image.putdata([(rng.randrange(256),) * 3 for _ in range(200 * 200)])
    out = io.BytesIO()
    image.save(out, "PNG")
    return out.getvalue()


@pytest.fixture
def fake_model(monkeypatch, tmp_path, settings):
    """Atrapa CLIP: kąt wektora z numeru ujęcia, który test zapisuje w nazwie źródła artefaktu."""
    settings.ARTIFACT_BACKEND = "local"
    settings.ARTIFACT_DIR = tmp_path / "artifacts"
    angles: dict[bytes, float] = {}
    monkeypatch.setattr(image_embedding, "available", lambda: True)
    monkeypatch.setattr(image_embedding, "_encode", lambda data: unit(angles[data]))
    return angles


def ad_with_creative(name: str, data: bytes) -> Ad:
    artifact = store.put(data, kind="creative_image", source_url=name)
    return Ad.objects.create(external_id=f"t/{name}", raw={"creatives": [artifact.sha256]})


def test_same_shot_links_as_story_not_as_source(fake_model):
    one, two, other = picture(1), picture(2), picture(3)
    fake_model.update({one: 0, two: 12, other: 80})  # kosinus 0,98 dla jednego ujęcia, 0,17 dla innego
    a, b, c = (ad_with_creative(n, d) for n, d in (("a", one), ("b", two), ("c", other)))
    for ad in (a, b, c):
        ad.image_embedding = image_embedding.ad_vector(ad)
        ad.save()
    service.link_ad(a)
    edge = Edge.objects.get(ad_a=a, ad_b=b)
    kinds = {e.kind: e for e in edge.evidence.all()}
    assert edge.relation == "similar"
    assert kinds["image_embedding"].similarity == pytest.approx(math.cos(math.radians(12)), abs=0.001)
    assert not Edge.objects.filter(ad_b=c).exists()


def test_image_alone_never_proves_a_common_source():
    result = score_pair([], [Soft("image_embedding", 0.99)], 1000)
    assert result.relation == "similar" and result.families["crea"] <= 5
    assert result.checks["same_source"] is False
    # Poniżej progu z danych (zrzuty tego samego interfejsu Facebooka do 0,80) marker nic nie wnosi.
    assert score_pair([], [Soft("image_embedding", 0.80)], 1000).relation is None


def test_vector_falls_back_to_video_poster_then_page_screenshot(fake_model):
    poster, shot = picture(4), picture(5)
    fake_model.update({poster: 10, shot: 50})
    poster_sha = store.put(poster, kind="video_frame").sha256
    shot_sha = store.put(shot, kind="page_screenshot").sha256
    ad = Ad.objects.create(external_id="t/v", raw={"videos": [{"poster": {"artifact": poster_sha}}]})
    assert image_embedding.ad_vector(ad) == pytest.approx(unit(10))
    bare = Ad.objects.create(external_id="t/p")
    assert image_embedding.ad_vector(bare, {"screenshot_sha": shot_sha}) == pytest.approx(unit(50))
    assert image_embedding.ad_vector(bare) is None


def test_no_model_and_tiny_images_give_no_vector(settings, tmp_path):
    settings.MODELS_DIR = tmp_path / "brak"
    assert image_embedding.available() is False
    assert image_embedding.embed(picture(6)) is None
    assert image_embedding._pixels(b"x" * 2000) is None


def test_embed_images_command_fills_missing(fake_model):
    from django.core.management import call_command

    data = picture(7)
    fake_model[data] = 30
    ad = ad_with_creative("k", data)
    call_command("embed_images")
    ad.refresh_from_db()
    assert list(ad.image_embedding) == pytest.approx(unit(30), abs=1e-6)
