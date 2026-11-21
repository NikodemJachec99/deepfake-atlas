"""Treść nagrań reklam: klatki, OCR, twarze, hasze. Nagrania generowane w teście, treść zmyślona."""

import pytest

from ads.models import Ad
from collectors import bundle
from evidence.models import AdSignature
from extractors import ocr
from extractors import video as video_meta
from people import faces
from similarity.models import Edge
from tests.test_bundle import run

pytestmark = pytest.mark.django_db
cv2 = pytest.importorskip("cv2")
np = pytest.importorskip("numpy")


def scene(i: int, seed: int) -> "np.ndarray":
    rng = np.random.default_rng(seed * 100 + i // 10)  # nowa scena co 10 klatek
    frame = rng.integers(0, 255, (24, 32, 3), dtype=np.uint8)
    return cv2.resize(frame, (320, 240), interpolation=cv2.INTER_NEAREST)


def write_video(path, seed: int, frames: int = 80, black_every: int = 0, scale: float = 1.0) -> None:
    size = (int(320 * scale), int(240 * scale))
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 10, size)
    for i in range(frames):
        frame = np.zeros((240, 320, 3), dtype=np.uint8) if black_every and i % black_every == 0 else scene(i, seed)
        writer.write(cv2.resize(frame, size))
    writer.release()


def video_case(tmp_path, name: str, seed: int, scale: float = 1.0):
    case = tmp_path / name
    case.mkdir()
    write_video(case / "reklama.mp4", seed, scale=scale)
    return case


def test_sampling_skips_uniform_frames(tmp_path):
    path = tmp_path / "v.mp4"
    write_video(path, seed=1, black_every=2)
    frames = video_meta.sample_frames(str(path))
    assert frames and all(f.jpeg.startswith(b"\xff\xd8") for f in frames)
    assert len(frames) <= video_meta.FRAME_COUNT
    assert video_meta.sample_frames(str(tmp_path / "brak.mp4")) == []


def test_same_footage_reencoded_links_by_frames_other_footage_does_not(tmp_path, monkeypatch):
    monkeypatch.setattr(ocr, "read_bytes", lambda data: [])
    first = video_case(tmp_path, "1", seed=7)
    second = video_case(tmp_path, "2", seed=7, scale=0.75)  # ten sam materiał, inna rozdzielczość, inne bajty
    other = video_case(tmp_path, "3", seed=99)
    for case in (first, second, other):
        run(bundle.import_case(case, bundle="t"))
    a, b, c = (Ad.objects.get(labels__case=n) for n in ("1", "2", "3"))
    assert AdSignature.objects.filter(ad=a, kind="video_frames").exists()
    edge = Edge.objects.get(ad_a=min(a.pk, b.pk), ad_b=max(a.pk, b.pk))
    shared = {e.kind: e for e in edge.evidence.all()}
    assert "video_frames" in shared and shared["video_frames"].similarity >= 0.6
    assert "creative_sha256" not in shared  # pliki różne, łączy dopiero treść
    for e in Edge.objects.filter(ad_b=c) | Edge.objects.filter(ad_a=c):
        assert "video_frames" not in {x.kind for x in e.evidence.all()}


def test_text_and_faces_from_frames(tmp_path, monkeypatch):
    monkeypatch.setattr(ocr, "read_bytes", lambda data: ["Zarabiaj codziennie", "https://oferta.example/?access_token=EAATESTfake0000000000000000000000tokenV"])
    monkeypatch.setattr(faces, "match_faces", lambda data, refs=None: [faces.FaceMatch("Jan Testowy", 0.6, (1, 2, 50, 60))])
    case = video_case(tmp_path, "5", seed=3)
    run(bundle.import_case(case, bundle="t"))
    ad = Ad.objects.get(labels__case="5")
    assert "Zarabiaj codziennie" in ad.text and "EAATESTfake" not in ad.text
    face = ad.ad_markers.select_related("marker").get(marker__kind="face_match")
    assert face.detail["name"] == "Jan Testowy" and "at_s" in face.detail


def test_unreadable_video_does_not_break_import(tmp_path):
    case = tmp_path / "x"
    case.mkdir()
    (case / "zepsute.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 100)
    run(bundle.import_case(case, bundle="t"))
    assert not AdSignature.objects.filter(kind="video_frames").exists()
