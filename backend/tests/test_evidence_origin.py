"""Pochodzenie dowodu, nieaktualne krawędzie i kolejność kandydatów (audyt E3, E4, E5)."""

import pytest

from ads.models import Ad
from evidence import services as markers
from evidence.models import AdMarker, AdSignature, Artifact, Marker
from extractors import Observation, minhash
from similarity import service
from similarity.models import Campaign, CampaignMembership, Edge

pytestmark = pytest.mark.django_db


def artifact(name: str, kind: str = "html_victim") -> Artifact:
    return Artifact.objects.create(sha256=name.ljust(64, "0"), kind=kind, size=1, storage_key=f"k/{name}")


def make_ad(n: int) -> Ad:
    return Ad.objects.create(source="manual", external_id=f"t{n}")


def test_two_pixels_from_two_files_point_each_to_own_file():
    a, b = make_ad(1), make_ad(2)
    files = {n: artifact(n) for n in ("a1", "a2", "b1", "b2")}
    markers.attach(a, [Observation("meta_pixel", "111111111111111")], files["a1"])
    markers.attach(a, [Observation("meta_pixel", "222222222222222")], files["a2"])
    markers.attach(b, [Observation("meta_pixel", "111111111111111")], files["b1"])
    markers.attach(b, [Observation("meta_pixel", "222222222222222")], files["b2"])

    service.link_ad(b)
    edge = Edge.objects.get()
    by_value = {e.value_a: (e.artifact_a_id, e.artifact_b_id) for e in edge.evidence.filter(kind="meta_pixel")}
    assert by_value == {
        "111111111111111": (files["a1"].pk, files["b1"].pk),
        "222222222222222": (files["a2"].pk, files["b2"].pk),
    }


def test_creative_trace_points_to_creative_image_not_har():
    ad = make_ad(1)
    har, image = artifact("har1", "har"), artifact("img1", "creative_image")
    markers.attach(ad, [Observation("creative_phash", "ab" * 8)], har)
    markers.attach(ad, [Observation("creative_phash", "ab" * 8)], image)
    assert AdMarker.objects.get(ad=ad).artifact_id == image.pk
    # konkretnego pliku nie nadpisuje ogólny zapis
    markers.attach(ad, [Observation("creative_phash", "ab" * 8)], har)
    assert AdMarker.objects.get(ad=ad).artifact_id == image.pk


def test_stale_edge_disappears_after_shared_markers_are_gone():
    a, b = make_ad(1), make_ad(2)
    for ad in (a, b):
        markers.attach(ad, [Observation("ga4", "G-AAAAAAAAAA")])
    service.link_ad(b)
    assert Edge.objects.count() == 1
    AdMarker.objects.filter(ad=b).delete()
    markers.attach(b, [Observation("ga4", "G-BBBBBBBBBB")])
    service.link_ad(b)
    assert Edge.objects.count() == 0


def test_stale_edge_with_verdict_is_kept():
    a, b = make_ad(1), make_ad(2)
    for ad in (a, b):
        markers.attach(ad, [Observation("ga4", "G-AAAAAAAAAA")])
    service.link_ad(b)
    Edge.objects.update(verdict=Edge.Verdict.CONFIRMED)
    AdMarker.objects.filter(ad=b).delete()
    service.link_ad(b)
    edge = Edge.objects.get()
    assert edge.verdict == Edge.Verdict.CONFIRMED


def test_set_signature_drops_old_bands_and_empty_clears_them():
    ad = make_ad(1)
    first = minhash.signature(f"a{i}" for i in range(40))
    second = minhash.signature(f"b{i}" for i in range(40))
    markers.set_signature(ad, "dom_minhash", first)
    old = set(AdMarker.objects.filter(ad=ad, marker__kind="dom_band").values_list("marker_id", flat=True))
    assert old
    markers.set_signature(ad, "dom_minhash", second)
    new = set(AdMarker.objects.filter(ad=ad, marker__kind="dom_band").values_list("marker_id", flat=True))
    assert new and not (new & old)
    assert all(m.ad_count == 0 for m in Marker.objects.filter(pk__in=old))
    markers.set_signature(ad, "dom_minhash", [])
    assert not AdMarker.objects.filter(ad=ad, marker__kind="dom_band").exists()
    assert not AdSignature.objects.filter(ad=ad, kind="dom_minhash").exists()


def test_old_ad_with_rare_ga4_beats_501_newer_ads_with_shared_template():
    old = make_ad(0)
    target_marker = Observation("dom_hash", "d" * 40)
    markers.attach(old, [Observation("ga4", "G-RARE000001")])
    markers.attach(old, [target_marker])
    # 501 nowszych reklam jednej kampanii dzieli z reklamą tylko szablon
    campaign = Campaign.objects.create()
    newer = Ad.objects.bulk_create([Ad(source="manual", external_id=f"n{i}") for i in range(501)])
    dom, _ = Marker.objects.get_or_create(kind="dom_hash", value_hash=Marker.hash_value("d" * 40), defaults={"value": "d" * 40})
    AdMarker.objects.bulk_create([AdMarker(ad=ad, marker=dom) for ad in newer])
    CampaignMembership.objects.bulk_create([CampaignMembership(ad=ad, campaign=campaign) for ad in newer])
    Marker.objects.filter(pk=dom.pk).update(ad_count=502)

    ad = Ad.objects.create(source="manual", external_id="target")
    markers.attach(ad, [Observation("ga4", "G-RARE000001"), target_marker])
    ids = [p.other_id for p in service.pair_inputs(ad)]
    assert len(ids) == service.MAX_CANDIDATES
    assert old.pk in ids
    service.link_ad(ad)
    assert Edge.objects.filter(ad_a=old, ad_b=ad).exists()
