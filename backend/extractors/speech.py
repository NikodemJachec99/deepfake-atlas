"""Mowa z nagrań reklam: lokalna transkrypcja małym modelem Whisper (faster-whisper, CPU, język polski).

Dźwięk wyciągamy ffmpegiem (imageio-ffmpeg albo ffmpeg z PATH) do 16 kHz mono WAV w pliku tymczasowym.
Bierzemy najwyżej `TRANSCRIBE_MAX_S` sekund od początku i nie czekamy dłużej niż `TRANSCRIBE_TIMEOUT_S`:
po przekroczeniu zostaje to, co już rozpoznane. Model pobiera się raz do `MODELS_DIR/whisper`.

Brak biblioteki, brak modelu, nagranie bez dźwięku albo błąd dają None, a analiza idzie dalej bez tego śladu.
`TRANSCRIBE=off` wyłącza kanał, `on` włącza go zawsze, `auto` (domyślnie) tylko gdy biblioteka jest zainstalowana.
"""

import logging
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from django.conf import settings

from extractors.url import redact_url

log = logging.getLogger(__name__)

SOURCE_LABEL = "mowa z nagrania"
SAMPLE_RATE = 16000
WAV_HEADER = 44
MIN_AUDIO_BYTES = WAV_HEADER + SAMPLE_RATE * 2 // 2  # poniżej pół sekundy dźwięku nie ma czego rozpoznawać
NO_SPEECH_MAX = 0.6  # segment, który model uznał za brak mowy, to zwykle muzyka albo szum
MAX_TEXT_CHARS = 20000


@dataclass
class Transcript:
    text: str
    language: str
    model: str
    audio_s: float  # ile sekund dźwięku wzięliśmy do rozpoznania
    elapsed_s: float
    truncated: bool  # nagranie dłuższe niż limit albo przerwane limitem czasu


def installed() -> bool:
    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        return False
    return True


def enabled() -> bool:
    mode = str(getattr(settings, "TRANSCRIBE", "auto")).lower()
    if mode in ("off", "0", "false", "no"):
        return False
    return installed()


def ffmpeg_exe() -> str | None:
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:  # noqa: BLE001
        return shutil.which("ffmpeg")


def extract_audio(video: str, wav: str, max_s: float) -> bool:
    """16 kHz mono WAV z pierwszych `max_s` sekund. False, gdy nie ma ffmpeg, ścieżki dźwięku albo wyszła cisza zerowej długości."""
    exe = ffmpeg_exe()
    if not exe:
        return False
    command = [exe, "-nostdin", "-y", "-loglevel", "error", "-i", video, "-t", str(max_s), "-vn", "-map", "0:a:0", "-ac", "1", "-ar", str(SAMPLE_RATE), "-f", "wav", wav]
    try:
        done = subprocess.run(command, capture_output=True, timeout=max(30, int(settings.TRANSCRIBE_TIMEOUT_S)), check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        log.warning("ffmpeg nie wyciągnął dźwięku z %s: %s", Path(video).name, exc)
        return False
    return done.returncode == 0 and Path(wav).exists() and Path(wav).stat().st_size >= MIN_AUDIO_BYTES


@lru_cache(maxsize=2)
def _model(name: str, download: bool):
    from faster_whisper import WhisperModel

    root = Path(settings.MODELS_DIR) / "whisper"
    root.mkdir(parents=True, exist_ok=True)
    return WhisperModel(name, device="cpu", compute_type="int8", download_root=str(root), local_files_only=not download)


def read_wav(wav: str):
    """Próbki WAV 16 kHz mono jako float32. Model dostaje tablicę, więc nie zależy od dekodera `av` z faster-whisper."""
    import wave

    import numpy as np

    with wave.open(wav, "rb") as handle:
        raw = handle.readframes(handle.getnframes())
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


def redact(text: str) -> str:
    """Adresy w transkrypcie, jak w tekście z OCR: sekrety z parametrów zamieniamy na skróty."""
    return " ".join(redact_url(word) if word.lower().startswith(("http://", "https://")) else word for word in text.split())


def transcribe(video: str) -> Transcript | None:
    """Transkrypt mowy z nagrania albo None (kanał wyłączony, brak modelu, brak dźwięku, błąd)."""
    if not enabled():
        return None
    started = time.monotonic()
    max_s = float(settings.TRANSCRIBE_MAX_S)
    name = settings.TRANSCRIBE_MODEL
    try:
        model = _model(name, bool(settings.TRANSCRIBE_DOWNLOAD))
    except Exception as exc:  # noqa: BLE001  (brak modelu przy wyłączonym pobieraniu, brak sieci, uszkodzony plik)
        log.warning("Model mowy %s niedostępny: %s", name, exc)
        return None
    with tempfile.TemporaryDirectory() as tmp:
        wav = str(Path(tmp) / "audio.wav")
        if not extract_audio(video, wav, max_s):
            return None
        audio_s = round((Path(wav).stat().st_size - WAV_HEADER) / (SAMPLE_RATE * 2), 2)
        parts: list[str] = []
        truncated = audio_s >= max_s - 0.5
        try:
            segments, info = model.transcribe(
                read_wav(wav), language=settings.TRANSCRIBE_LANGUAGE, beam_size=1, vad_filter=True, condition_on_previous_text=False,
            )
            for segment in segments:
                if getattr(segment, "no_speech_prob", 0.0) <= NO_SPEECH_MAX:
                    piece = segment.text.strip()
                    if piece and (not parts or piece != parts[-1]):
                        parts.append(piece)
                if time.monotonic() - started > float(settings.TRANSCRIBE_TIMEOUT_S):
                    truncated = True
                    break
        except Exception as exc:  # noqa: BLE001
            log.warning("Transkrypcja %s nie powiodła się: %s", Path(video).name, exc)
            return None
    text = redact(" ".join(parts))[:MAX_TEXT_CHARS]
    if not text:
        return None
    return Transcript(text, getattr(info, "language", settings.TRANSCRIBE_LANGUAGE), name, audio_s, round(time.monotonic() - started, 1), truncated)


def describe(transcript: Transcript) -> dict:
    """Wpis do `Ad.raw["videos"][i]["speech"]`: tekst z oznaczeniem źródła, do pokazania w interfejsie."""
    return {
        "source": SOURCE_LABEL,
        "text": transcript.text,
        "language": transcript.language,
        "model": transcript.model,
        "audio_s": transcript.audio_s,
        "truncated": transcript.truncated,
    }
