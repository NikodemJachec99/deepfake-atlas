"""Nagrania: metadane, klatka poglądowa z pozycją, odtwarzanie z zakresem bajtów. Nagrania syntetyczne."""

import json
from io import StringIO

import pytest
from django.core.management import call_command
from rest_framework.test import APIClient

from ads.models import Ad
from collectors import bundle
from evidence import store
from extractors import video
from tests.test_bundle import run

cv2 = pytest.importorskip("cv2")
np = pytest.importorskip("numpy")


def synthetic_mp4(path, seconds: float = 3.0, fps: int = 10) -> bytes:
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (64, 48))
    for i in range(int(seconds * fps)):
        frame = np.full((48, 64, 3), (i * 7) % 255, dtype=np.uint8)
        writer.write(frame)
    writer.release()
    return path.read_bytes()


def test_signatures():
    assert video.content_type(b"\x00\x00\x00\x18ftypisom") == "video/mp4"
    assert video.content_type(b"\x1aE\xdf\xa3\x01\x00") == "video/webm"
    assert video.content_type(b"<html><script>") is None


def test_probe_reads_duration_and_poster_position(tmp_path):
    synthetic_mp4(tmp_path / "a.mp4", seconds=3.0, fps=10)
    p = video.probe(str(tmp_path / "a.mp4"))
    assert p is not None and p.frames == 30 and p.fps == 10.0 and p.duration_s == 3.0 and (p.width, p.height) == (64, 48)
    assert p.poster_jpeg.startswith(b"\xff\xd8") and 0 <= p.poster_at_s <= 1.0
    assert video.probe(str(tmp_path / "brak.mp4")) is None


def test_describe_clip_and_missing_reasons(tmp_path):
    synthetic_mp4(tmp_path / "a.mp4", seconds=3.0)
    p = video.probe(str(tmp_path / "a.mp4"))
    clip = video.describe({"name": "a.mp4"}, p, "f" * 64, original_duration_s=30.0)
    assert clip["original"] == {"duration_s": 30.0, "clip": True} and clip["poster"]["position"] == round(p.poster_at_s / 3.0, 4)
    whole = video.describe({"name": "a.mp4"}, p, "f" * 64, original_duration_s=3.0)
    assert whole["original"]["clip"] is False and "missing" not in whole
    unknown = video.describe({"name": "a.mp4"}, p, "f" * 64, original_duration_s=None)
    assert unknown["original"] == {"duration_s": None, "clip": None} and "długości oryginału" in unknown["missing"][0]
    broken = video.describe({"name": "x.mp4"}, None, None, None)
    assert broken["duration_s"] is None and broken["poster"] is None and broken["missing"]


@pytest.mark.django_db
def test_imported_video_is_described_and_playable_with_ranges(tmp_path):
    case = tmp_path / "5"
    case.mkdir()
    data = synthetic_mp4(case / "Reklama [1900000000000002_3].mp4", seconds=3.0)
    (case / "Reklama [1900000000000002_3].info.json").write_text(json.dumps({"id": "1900000000000002_3", "duration": 12}), encoding="utf-8")
    run(bundle.import_case(case, bundle="nask"))
    client = APIClient()
    [v] = client.get(f"/api/ads/{Ad.objects.get().pk}").json()["videos"]
    assert v["playable"] is True and v["url"] == f"/api/artifacts/{v['sha256']}/video"
    assert (v["duration_s"], v["frames"], v["width"], v["height"]) == (3.0, 30, 64, 48)
    assert v["original"] == {"duration_s": 12.0, "clip": True} and v["missing"] == []
    poster = client.get(v["poster"]["url"])
    assert poster.status_code == 200 and poster["Content-Type"] == "image/jpeg"
    assert 0 <= v["poster"]["position"] <= 1

    full = client.get(v["url"])
    assert full.status_code == 200 and full["Content-Type"] == "video/mp4" and full.content == data
    assert full["Accept-Ranges"] == "bytes" and full["X-Content-Type-Options"] == "nosniff"
    part = client.get(v["url"], HTTP_RANGE="bytes=10-19")
    assert part.status_code == 206 and part.content == data[10:20] and part["Content-Range"] == f"bytes 10-19/{len(data)}"
    tail = client.get(v["url"], HTTP_RANGE="bytes=-5")
    assert tail.status_code == 206 and tail.content == data[-5:]
    assert client.get(v["url"], HTTP_RANGE=f"bytes={len(data) + 5}-").status_code == 416
    # klatka nie jest nagraniem, a nagranie nie jest obrazem
    assert client.get(f"/api/artifacts/{v['poster']['artifact']}/video").status_code == 404
    assert client.get(f"/api/artifacts/{v['sha256']}/image").status_code == 404


@pytest.mark.django_db
def test_fake_video_bytes_are_not_served():
    fake = store.put(b"<html><script>alert(1)</script></html>", kind="creative_video")
    assert APIClient().get(f"/api/artifacts/{fake.sha256}/video").status_code == 404


@pytest.mark.django_db
def test_too_large_video_is_described_but_not_playable(tmp_path, monkeypatch):
    monkeypatch.setattr(bundle, "MAX_UPLOAD_ARTIFACT", 10)
    case = tmp_path / "14"
    case.mkdir()
    synthetic_mp4(case / "ScreenRecording.mp4", seconds=2.0)
    run(bundle.import_case(case, bundle="nask"))
    [v] = APIClient().get(f"/api/ads/{Ad.objects.get().pk}").json()["videos"]
    assert v["playable"] is False and v["url"] is None and v["duration_s"] == 2.0
    assert v["poster"] is not None and any("limit magazynu" in m for m in v["missing"])


@pytest.mark.django_db
def test_backfill_for_videos_imported_without_metadata(tmp_path):
    data = synthetic_mp4(tmp_path / "old.mp4", seconds=3.0)
    sha = store.put(data, kind="creative_video").sha256
    ad = Ad.objects.create(source="capture", external_id="nask/47/x", raw={"videos": [{"name": "old.mp4", "size": len(data), "sha256": sha}]})
    big = synthetic_mp4(tmp_path / "duzy.mp4", seconds=2.0)
    big_sha = bundle._file_sha256(tmp_path / "duzy.mp4")
    other = Ad.objects.create(source="capture", external_id="nask/14/x", raw={"videos": [{"name": "duzy.mp4", "size": len(big), "sha256": big_sha}]})
    before = APIClient().get(f"/api/ads/{ad.pk}").json()["videos"][0]
    assert before["duration_s"] is None and "przed odczytem metadanych" in before["missing"][0]
    out = StringIO()
    call_command("probe_videos", "--root", str(tmp_path), stdout=out)
    assert "Zaktualizowane reklamy: 2" in out.getvalue()
    ad.refresh_from_db()
    other.refresh_from_db()
    assert ad.raw["videos"][0]["duration_s"] == 3.0 and ad.raw["videos"][0]["stored"] is True
    assert other.raw["videos"][0]["duration_s"] == 2.0 and other.raw["videos"][0]["stored"] is False
    call_command("probe_videos", stdout=out)  # drugi raz nie ma czego uzupełniać
    assert out.getvalue().strip().endswith("Zaktualizowane reklamy: 0. Nagrania bez pliku: 0.")
