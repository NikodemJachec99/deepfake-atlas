"""Mowa z nagrań: transkrypcja atrapą (testy nie pobierają modelu), tekst reklamy, osoby, polecenie przeliczenia."""

import io
import subprocess
import sys
import wave
from types import SimpleNamespace

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from rest_framework.test import APIClient

from ads.models import Ad, Analysis
from collectors import bundle
from evidence import store
from extractors import ocr, speech
from people import faces
from people.models import Person
from tests.test_bundle import run
from tests.test_video_content import video_case, write_video

pytestmark = pytest.mark.django_db
pytest.importorskip("cv2")

SPEECH = "Pan Jan Testowy poleca platformę, wpłać dwieście złotych i odbierz zwrot na https://oferta.example/?access_token=EAATESTfake0000000000000000000000tokenV dziś."


def fake_transcript(text: str = SPEECH, truncated: bool = False) -> speech.Transcript:
    return speech.Transcript(speech.redact(text), "pl", "small", 12.0, 3.5, truncated)


def silent_wav(path, seconds: float = 2.0) -> None:
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(speech.SAMPLE_RATE)
        out.writeframes(b"\x00\x00" * int(speech.SAMPLE_RATE * seconds))


@pytest.fixture
def quiet_frames(monkeypatch):
    monkeypatch.setattr(ocr, "read_bytes", lambda data: [])
    monkeypatch.setattr(faces, "match_faces", lambda data, refs=None: [])


def test_speech_goes_to_ad_text_raw_and_person_mention(tmp_path, monkeypatch, quiet_frames):
    Person.objects.create(name="Jan Testowy")
    monkeypatch.setattr(speech, "transcribe", lambda path: fake_transcript())
    run(bundle.import_case(video_case(tmp_path, "5", seed=3), bundle="t"))
    ad = Ad.objects.get(labels__case="5")
    assert "Jan Testowy" in ad.text and "EAATESTfake" not in ad.text
    [video] = ad.raw["videos"]
    assert video["speech"]["source"] == "mowa z nagrania" and video["speech"]["model"] == "small"
    assert "EAATESTfake" not in video["speech"]["text"]
    assert ad.ad_markers.filter(marker__kind="person_mention").exists()
    [api_video] = APIClient().get(f"/api/ads/{ad.pk}").json()["videos"]
    assert api_video["speech"]["text"] == video["speech"]["text"] and api_video["speech"]["truncated"] is False


def test_disabled_or_missing_library_does_not_break_anything(tmp_path, monkeypatch, settings, quiet_frames):
    assert speech.transcribe(str(tmp_path / "brak.mp4")) is None  # TRANSCRIBE=off z conftestu
    settings.TRANSCRIBE = "on"
    monkeypatch.setitem(sys.modules, "faster_whisper", None)  # import daje ImportError, jak bez biblioteki
    assert not speech.installed() and not speech.enabled()
    assert speech.transcribe(str(tmp_path / "brak.mp4")) is None
    run(bundle.import_case(video_case(tmp_path, "6", seed=4), bundle="t"))
    [video] = Ad.objects.get(labels__case="6").raw["videos"]
    assert "speech" not in video


def test_urls_in_transcript_are_redacted():
    out = speech.redact("wejdź na https://x.example/p?access_token=EAATESTfake0000000000000000000000tokenV albo na www.x.example")
    assert "EAATESTfake" not in out and "www.x.example" in out


class FakeModel:
    def __init__(self, segments):
        self.segments = segments
        self.calls = []

    def transcribe(self, wav, **kwargs):
        self.calls.append(kwargs)
        return iter(self.segments), SimpleNamespace(language="pl")


def seg(text, no_speech=0.0):
    return SimpleNamespace(text=f" {text} ", no_speech_prob=no_speech)


def enable(monkeypatch, settings, model, wav_seconds=2.0):
    def extract(video, wav, max_s):
        silent_wav(wav, wav_seconds)
        return True

    settings.TRANSCRIBE = "on"
    monkeypatch.setattr(speech, "installed", lambda: True)
    monkeypatch.setattr(speech, "_model", lambda name, download: model)
    monkeypatch.setattr(speech, "extract_audio", extract)


def test_transcribe_skips_noise_and_repeats(tmp_path, monkeypatch, settings):
    model = FakeModel([seg("Dzień dobry"), seg("Dzień dobry"), seg("muzyka", no_speech=0.9), seg("Jan Testowy zaprasza")])
    enable(monkeypatch, settings, model)
    result = speech.transcribe(str(tmp_path / "v.mp4"))
    assert result.text == "Dzień dobry Jan Testowy zaprasza"
    assert result.audio_s == 2.0 and not result.truncated and result.language == "pl"
    assert model.calls[0]["language"] == "pl" and model.calls[0]["vad_filter"] is True


def test_transcribe_marks_truncated_by_length_and_time(tmp_path, monkeypatch, settings):
    settings.TRANSCRIBE_MAX_S = 2
    enable(monkeypatch, settings, FakeModel([seg("Początek nagrania")]), wav_seconds=2.0)
    assert speech.transcribe(str(tmp_path / "v.mp4")).truncated is True
    settings.TRANSCRIBE_MAX_S = 120
    settings.TRANSCRIBE_TIMEOUT_S = -1  # limit czasu minął przed pierwszym segmentem
    enable(monkeypatch, settings, FakeModel([seg("Pierwszy"), seg("Drugi")]))
    result = speech.transcribe(str(tmp_path / "v.mp4"))
    assert result.text == "Pierwszy" and result.truncated is True


def test_transcribe_returns_none_without_model_audio_or_speech(tmp_path, monkeypatch, settings):
    enable(monkeypatch, settings, FakeModel([seg("cisza", no_speech=0.95)]))
    assert speech.transcribe(str(tmp_path / "v.mp4")) is None  # tylko szum
    monkeypatch.setattr(speech, "extract_audio", lambda video, wav, max_s: False)
    assert speech.transcribe(str(tmp_path / "v.mp4")) is None  # brak ścieżki dźwięku

    def broken(name, download):
        raise OSError("brak modelu")

    monkeypatch.setattr(speech, "_model", broken)
    assert speech.transcribe(str(tmp_path / "v.mp4")) is None  # model niedostępny


@pytest.mark.skipif(speech.ffmpeg_exe() is None, reason="brak ffmpeg")
def test_extract_audio_real_ffmpeg(tmp_path):
    silent = tmp_path / "bez.mp4"
    write_video(silent, seed=1, frames=30)
    assert speech.extract_audio(str(silent), str(tmp_path / "a.wav"), 10) is False  # nagranie bez dźwięku
    tone = tmp_path / "z.mp4"
    done = subprocess.run([speech.ffmpeg_exe(), "-y", "-loglevel", "error", "-i", str(silent), "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
                           "-c:v", "copy", "-c:a", "aac", "-shortest", str(tone)], capture_output=True)
    if done.returncode != 0:
        pytest.skip(f"ffmpeg nie złożył nagrania testowego: {done.stderr[:200]!r}")
    assert speech.extract_audio(str(tone), str(tmp_path / "b.wav"), 2) is True
    with wave.open(str(tmp_path / "b.wav")) as wav:
        assert wav.getframerate() == 16000 and wav.getnchannels() == 1 and wav.getnframes() <= 2 * 16000 + 2000


def stored_video_ad(tmp_path, name="Reklama [1].mp4") -> Ad:
    path = tmp_path / "v.mp4"
    write_video(path, seed=5, frames=30)
    data = path.read_bytes()
    artifact = store.put(data, kind="creative_video", source_url=name)
    ad = Ad.objects.create(source="capture", external_id="nask/5/reklama", text="Stary tekst z OCR.",
                           raw={"videos": [{"name": name, "size": len(data), "sha256": artifact.sha256, "stored": True}]})
    Analysis.objects.create(ad=ad, input_kind=Analysis.Kind.AD, input_value=ad.external_id, status=Analysis.Status.DONE,
                            state={"offline": True, "capture": {"observations": []}, "pages": {}})
    return ad


def test_transcribe_videos_command_updates_stored_videos(tmp_path, monkeypatch):
    Person.objects.create(name="Jan Testowy")
    ad = stored_video_ad(tmp_path)
    monkeypatch.setattr(speech, "enabled", lambda: True)
    calls = []
    monkeypatch.setattr(speech, "transcribe", lambda path: calls.append(path) or fake_transcript())
    out = io.StringIO()
    call_command("transcribe_videos", "--reanalyze", stdout=out)
    ad.refresh_from_db()
    assert ad.text.startswith("Stary tekst z OCR.") and "Jan Testowy" in ad.text and "EAATESTfake" not in ad.text
    assert ad.raw["videos"][0]["speech"]["source"] == "mowa z nagrania"
    assert ad.ad_markers.filter(marker__kind="person_mention").exists()
    assert Analysis.objects.filter(ad=ad).count() == 2
    call_command("transcribe_videos", stdout=out)  # drugi raz nie ma czego robić
    assert len(calls) == 1
    call_command("transcribe_videos", "--all", stdout=out)
    ad.refresh_from_db()
    assert len(calls) == 2 and ad.text.count("Jan Testowy") == 1  # transkrypt podmieniony, nie dopisany drugi raz


def test_transcribe_videos_remembers_silent_video_and_refuses_when_disabled(tmp_path, monkeypatch):
    ad = stored_video_ad(tmp_path)
    with pytest.raises(CommandError):
        call_command("transcribe_videos")  # TRANSCRIBE=off
    monkeypatch.setattr(speech, "enabled", lambda: True)
    monkeypatch.setattr(speech, "transcribe", lambda path: None)
    call_command("transcribe_videos", stdout=io.StringIO())
    ad.refresh_from_db()
    assert ad.raw["videos"][0]["speech"] is None and ad.text == "Stary tekst z OCR."
    [video] = APIClient().get(f"/api/ads/{ad.pk}").json()["videos"]
    assert video["speech"] is None


def test_probe_videos_all_keeps_speech(tmp_path):
    ad = stored_video_ad(tmp_path)
    ad.raw["videos"][0]["speech"] = speech.describe(fake_transcript("Jan Testowy mówi"))
    ad.raw["videos"][0]["duration_s"] = 1.0
    ad.save()
    call_command("probe_videos", "--all", stdout=io.StringIO())
    ad.refresh_from_db()
    assert ad.raw["videos"][0]["speech"]["text"] == "Jan Testowy mówi" and ad.raw["videos"][0]["duration_s"] == 3.0
