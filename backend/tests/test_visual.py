"""Warstwa wizualna, słowa kluczowe, duplikaty i ocena nowego materiału."""

import io
import random

import pytest
from PIL import Image, ImageDraw

from ads.models import Ad, Analysis
from collectors import bundle
from extractors import images, ocr
from extractors.keywords import keywords, topics
from similarity.fusion import Shared, Soft, score_pair
from similarity.models import Edge
from tests.test_bundle import ARTICLE_X, ARTICLE_Y, article_html, make_case, run
from tests.test_capture import PAGE


def picture(seed: int, size=(480, 320), fmt="PNG", quality=90) -> bytes:
    """Deterministyczny obraz o wyraźnej strukturze, różny dla każdego ziarna."""
    rng = random.Random(seed)
    image = Image.new("RGB", (480, 320), (rng.randrange(256), rng.randrange(256), rng.randrange(256)))
    draw = ImageDraw.Draw(image)
    for _ in range(60):
        x, y = rng.randrange(480), rng.randrange(320)
        draw.rectangle([x, y, x + rng.randrange(20, 160), y + rng.randrange(20, 120)], fill=(rng.randrange(256), rng.randrange(256), rng.randrange(256)))
    buffer = io.BytesIO()
    image.resize(size).save(buffer, fmt, **({"quality": quality} if fmt == "JPEG" else {}))
    return buffer.getvalue()


def test_dhash_survives_resize_and_recompression_but_separates_other_images():
    original = images.dhash(picture(1))
    assert original is not None
    assert images.distance(original, images.dhash(picture(1, size=(960, 640)))) <= 4
    assert images.distance(original, images.dhash(picture(1, fmt="JPEG", quality=40))) <= images.MAX_DISTANCE
    assert images.distance(original, images.dhash(picture(2))) > 12


def test_dhash_ignores_icons_and_non_images():
    assert images.dhash(picture(1, size=(64, 64))) is None
    assert images.dhash(b"to nie jest obraz" * 400) is None
    assert images.dhash(b"") is None


def test_image_set_similarity_needs_more_than_one_stock_picture():
    a = images.hash_set([picture(i) for i in (1, 2, 3, 4)])
    same = images.hash_set([picture(i, fmt="JPEG", quality=60) for i in (1, 2, 3, 4)])
    one_shared = images.hash_set([picture(i) for i in (1, 11, 12, 13)])
    assert len(a) == 4
    assert images.set_similarity(a, same) == 1.0
    assert images.set_similarity(a, one_shared) < 0.2
    assert images.set_similarity(images.hash_set([picture(1)]), images.hash_set([picture(1)])) < 0.5
    assert images.set_similarity(a, []) == 0.0
    # obrazy różniące się o kilka bitów dzielą klucz wyszukiwania
    assert set(images.bands(a)) & set(images.bands(same))


def test_keywords_and_topics():
    text = (
        "Platforma inwestycyjna gwarantuje zysk. Polacy zarabiają na platformie tysiące, a zysk rośnie co tydzień. "
        "Wystarczy mały depozyt, żeby inwestycje przynosiły dochód. Platforma działa bez przerwy."
    )
    assert keywords(text)[:2] == ["platforma", "zysk"]
    assert "oraz" not in keywords(text)
    assert topics(text) == ["inwestycje"]
    assert topics("Kapsułki na stawy poleca lekarz. Suplement usuwa ból stawów, a terapia trwa miesiąc.") == ["zdrowie"]
    assert topics("Dzień dobry, zapraszamy na spotkanie autorskie.") == []


def test_duplicate_is_flagged_only_for_the_same_page():
    same_page = score_pair(
        shared=[Shared("dom_hash", "9f3a", df=2), Shared("ga4", "G-ABCDEFGH12", df=2)],
        soft=[Soft("page_text_minhash", 1.0)],
        corpus_n=1000,
    )
    assert same_page.duplicate is True and same_page.relation == "same_campaign"
    variant = score_pair(
        shared=[Shared("ga4", "G-ABCDEFGH12", df=2)], soft=[Soft("page_text_minhash", 0.8), Soft("dom_minhash", 0.95)], corpus_n=1000
    )
    assert variant.duplicate is False and variant.relation == "same_campaign"


@pytest.mark.django_db
def test_same_pictures_on_unrelated_pages_give_a_visual_link(tmp_path, monkeypatch):
    monkeypatch.setattr(ocr, "read_image", lambda path: [])

    def page_with_pictures(name, domain, title, sentence, seeds, layout):
        case = tmp_path / name
        case.mkdir()
        url = f"https://{domain}/oferta"
        html = article_html(url, title, sentence).replace("<p class='akapit'>", f"<{layout} class='blok-{name}'>").replace("</p>", f"</{layout}>")
        (case / f"{title}.html").write_text(html, encoding="utf-8")
        files = case / f"{title}_files"
        files.mkdir()
        for seed in seeds:
            (files / f"foto-{seed}.jpg").write_bytes(picture(seed, fmt="JPEG"))
        (files / "ikona.png").write_bytes(picture(99, size=(48, 48)))
        return case

    first = page_with_pictures("a", "kuracja-a.example", "Nowa kuracja na stawy od ręki", ARTICLE_X, (1, 2, 3, 4), "p")
    second = page_with_pictures("b", "zdrowie-b.example", "Lekarze nie chcą, żebyś to wiedział", ARTICLE_Y, (1, 2, 3, 5), "div")
    third = page_with_pictures("c", "inne-c.example", "Zupełnie inna strona z innymi zdjęciami", ARTICLE_Y + " Inna treść.", (21, 22, 23, 24), "section")
    for case in (first, second, third):
        run(bundle.import_case(case, bundle="t"))

    a, b, c = (Ad.objects.get(external_id=f"t/{name}/{domain}") for name, domain in (("a", "kuracja-a.example"), ("b", "zdrowie-b.example"), ("c", "inne-c.example")))
    edge = Edge.objects.get(ad_a=a, ad_b=b)
    evidence = {e.kind: e for e in edge.evidence.all()}
    assert evidence["image_set"].family == "crea" and evidence["image_set"].similarity == pytest.approx(0.6)
    assert edge.relation == Edge.Relation.SIMILAR  # te same zdjęcia, brak dowodu wspólnego zaplecza
    assert not Edge.objects.filter(ad_a=a, ad_b=c).exists()  # inne zdjęcia, inna treść: brak powiązania
    for other in Edge.objects.filter(ad_b=c):  # strony b i c dzielą treść, ale nie obrazy
        assert "image_set" not in {e.kind for e in other.evidence.all()}


@pytest.mark.django_db
def test_assessment_tells_duplicate_known_campaign_known_operator_and_new_pattern(tmp_path, monkeypatch):
    monkeypatch.setattr(ocr, "read_image", lambda path: [])

    def assess(case):
        analysis = run(bundle.import_case(case, bundle="t"))[0]
        return analysis.result["cluster"]["assessment"]

    title = "Zamach na biznesmena — Gazeta.pl"
    assert assess(make_case(tmp_path, "1", "civic.example", title, ARTICLE_X)) == "new_pattern"
    assert assess(make_case(tmp_path, "2", "across.example", title, ARTICLE_X.replace("wieczorem", "nocą"), ip="198.51.100.9")) == "known_campaign"
    assert assess(make_case(tmp_path, "3", "novum.example", "Po programie zatrzymano prowadzącego", ARTICLE_Y, ip="192.0.2.44")) == "known_operator"

    # To samo przechwycenie wrzucone drugi raz pod innym numerem sprawy.
    twin = tmp_path / "4"
    twin.mkdir()
    for path in (tmp_path / "1").iterdir():
        if path.is_file():
            (twin / path.name).write_bytes(path.read_bytes())
    assert assess(twin) == "duplicate"
    duplicate = Edge.objects.get(duplicate=True)
    assert {duplicate.ad_a.labels["case"], duplicate.ad_b.labels["case"]} == {"1", "4"}

    lonely = tmp_path / "5"
    lonely.mkdir()
    url = PAGE.replace("zysk-a.example", "sklep-z-butami.example").replace("utm_visit", "ref")
    (lonely / "Sklep.html").write_text(
        article_html(url, "Buty zimowe w dobrej cenie", "Nowa kolekcja butów na zimę z darmową dostawą.").replace("akapit", "produkt"), encoding="utf-8"
    )
    result = run(bundle.import_case(lonely, bundle="t"))[0].result
    assert result["cluster"]["assessment"] == "new_pattern"
    assert result["fuse"]["edges"] == 0
    assert Analysis.objects.count() == 5


@pytest.mark.django_db
def test_keywords_and_topic_are_stored_with_the_ad(tmp_path, monkeypatch):
    monkeypatch.setattr(ocr, "read_image", lambda path: [])
    sentence = "Platforma inwestycyjna daje zysk, a inwestycje w akcje przynoszą dochód każdemu, kto wpłaci depozyt."
    case = make_case(tmp_path, "1", "civic.example", "Jak zarabiać na giełdzie bez ryzyka", sentence)
    analysis = run(bundle.import_case(case, bundle="t"))[0]
    ad = Ad.objects.get()
    assert ad.labels["topics"] == ["inwestycje"]
    assert "platforma" in ad.labels["keywords"]
    assert analysis.result["extract"]["topics"] == ["inwestycje"]

