"""Metadane nagrania i klatka poglądowa. OpenCV (jest już zależnością OCR), bez wywołań zewnętrznych.

Pozycję klatki podajemy według dekodera: przewijanie skacze do najbliższej klatki kluczowej, więc żądana
sekunda i faktyczna mogą się różnić. Długość liczymy z liczby klatek i fps zapisanych w kontenerze.
"""

from dataclasses import dataclass

POSTER_AT_S = 1.0  # klatka poglądowa: pierwsza sekunda, a dla krótszych nagrań 10% długości
MAX_SIDE = 640
SIGNATURES = (
    (4, b"ftyp", "video/mp4"),  # MP4 i MOV (ISO BMFF): rozmiar pudełka, potem "ftyp"
    (0, b"\x1aE\xdf\xa3", "video/webm"),  # Matroska i WebM (EBML)
)


def content_type(head: bytes) -> str | None:
    """Typ nagrania po sygnaturze bajtów. Nie ufamy rozszerzeniu ani deklaracji."""
    for offset, magic, mime in SIGNATURES:
        if head[offset : offset + len(magic)] == magic:
            return mime
    return None


@dataclass
class Probe:
    duration_s: float | None
    fps: float | None
    frames: int | None
    width: int | None
    height: int | None
    poster_jpeg: bytes = b""
    poster_at_s: float | None = None


def probe(path: str) -> Probe | None:
    """Metadane pliku nagrania. None, gdy OpenCV go nie otworzy."""
    try:
        import cv2
    except ImportError:
        return None
    capture = cv2.VideoCapture(str(path))
    try:
        if not capture.isOpened():
            return None
        frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0) or None
        fps = float(capture.get(cv2.CAP_PROP_FPS) or 0) or None
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0) or None
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0) or None
        duration = round(frames / fps, 2) if frames and fps else None
        result = Probe(duration, round(fps, 3) if fps else None, frames, width, height)
        target = min(POSTER_AT_S, duration * 0.1) if duration else 0.0
        capture.set(cv2.CAP_PROP_POS_MSEC, target * 1000)
        ok, frame = capture.read()
        if ok and frame is not None:
            index = int(capture.get(cv2.CAP_PROP_POS_FRAMES) or 1) - 1
            result.poster_at_s = round(index / fps, 3) if fps else None
            scale = MAX_SIDE / max(frame.shape[0], frame.shape[1])
            if scale < 1:
                frame = cv2.resize(frame, (int(frame.shape[1] * scale), int(frame.shape[0] * scale)), interpolation=cv2.INTER_AREA)
            encoded, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            if encoded:
                result.poster_jpeg = buffer.tobytes()
        return result
    except cv2.error:
        return None
    finally:
        capture.release()


def describe(entry: dict, probed: Probe | None, poster_sha: str | None, original_duration_s: float | None) -> dict:
    """Wpis nagrania do `Ad.raw["videos"]`. Pola, których nie da się ustalić, są None z powodem."""
    out = dict(entry)
    if probed is None:
        out.update(duration_s=None, fps=None, frames=None, width=None, height=None, poster=None,
                   missing=["nie udało się odczytać pliku nagrania"])
        out["original"] = {"duration_s": original_duration_s, "clip": None}
        return out
    missing = []
    out.update(duration_s=probed.duration_s, fps=probed.fps, frames=probed.frames, width=probed.width, height=probed.height)
    if poster_sha and probed.poster_at_s is not None:
        position = round(probed.poster_at_s / probed.duration_s, 4) if probed.duration_s else None
        out["poster"] = {"artifact": poster_sha, "at_s": probed.poster_at_s, "position": position}
    else:
        out["poster"] = None
        missing.append("brak klatki poglądowej")
    clip = None
    if original_duration_s and probed.duration_s:
        clip = probed.duration_s < original_duration_s - 0.5
    elif not original_duration_s:
        missing.append("metadane nie podają długości oryginału, więc nie wiadomo, czy plik jest wycinkiem")
    out["original"] = {"duration_s": original_duration_s, "clip": clip}
    if missing:
        out["missing"] = missing
    return out
