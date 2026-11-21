"""Twarze osób z bazy referencyjnej na zrzutach reklam.

Wykrywanie: YuNet, wektor twarzy: SFace (oba z OpenCV Zoo, ONNX, liczone lokalnie na CPU).
Porównujemy tylko z małą bazą osób publicznych (`face_refs.json`), zbudowaną ze zdjęć na wolnej
licencji ze źródłem przy każdym. Wektorów twarzy spoza bazy nie zapisujemy: zostaje wyłącznie
marker "na zrzucie jest twarz osoby X" z wynikiem podobieństwa.

Brak modelu, brak OpenCV albo nieczytelny obraz dają pustą listę. Analiza idzie dalej bez twarzy.
"""

import json
import logging
import urllib.request
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from django.conf import settings

log = logging.getLogger(__name__)

MODELS = {
    "detector": (
        "face_detection_yunet_2023mar.onnx",
        "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
    ),
    "recognizer": (
        "face_recognition_sface_2021dec.onnx",
        "https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx",
    ),
}
REFS_PATH = Path(__file__).with_name("face_refs.json")
# Próg podobieństwa kosinusowego zalecany przez autorów SFace dla tej samej osoby.
MATCH_THRESHOLD = 0.363
MIN_FACE_PX = 40  # mniejsza twarz to miniatura w tle, nie wizerunek, na którym opiera się reklama
DETECTION_SCORE = 0.8


@dataclass(frozen=True)
class FaceMatch:
    name: str
    score: float
    box: tuple[int, int, int, int]


def model_path(role: str) -> Path:
    return Path(settings.MODELS_DIR) / MODELS[role][0]


def ensure_models(download: bool | None = None) -> bool:
    """Sprawdza modele i w razie potrzeby pobiera je raz do `MODELS_DIR`."""
    download = settings.FACE_MODELS_DOWNLOAD if download is None else download
    for role, (_name, url) in MODELS.items():
        path = model_path(role)
        if path.exists() and path.stat().st_size > 0:
            continue
        if not download:
            return False
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            partial = path.with_suffix(".part")
            with urllib.request.urlopen(url, timeout=120) as response, partial.open("wb") as out:
                while chunk := response.read(1 << 20):
                    out.write(chunk)
            partial.replace(path)
        except OSError as exc:
            log.warning("Nie udało się pobrać modelu twarzy %s: %s", url, exc)
            return False
    return True


@lru_cache(maxsize=1)
def _models():
    import cv2

    detector = cv2.FaceDetectorYN.create(str(model_path("detector")), "", (320, 320), DETECTION_SCORE, 0.3, 5000)
    recognizer = cv2.FaceRecognizerSF.create(str(model_path("recognizer")), "")
    return detector, recognizer


def available() -> bool:
    try:
        import cv2

        return hasattr(cv2, "FaceDetectorYN") and ensure_models()
    except ImportError:
        return False


def embeddings(image_bytes: bytes) -> list[tuple[tuple[int, int, int, int], list[float]]]:
    """Twarze na obrazie: ramka i znormalizowany wektor SFace (128 liczb)."""
    if not available():
        return []
    try:
        import cv2
        import numpy as np

        image = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            return []
        detector, recognizer = _models()
        height, width = image.shape[:2]
        detector.setInputSize((width, height))
        _, faces = detector.detect(image)
        found = []
        for face in faces if faces is not None else []:
            x, y, w, h = (int(v) for v in face[:4])
            if min(w, h) < MIN_FACE_PX:
                continue
            aligned = recognizer.alignCrop(image, face)
            vector = recognizer.feature(aligned).flatten()
            vector = vector / (np.linalg.norm(vector) or 1.0)
            found.append(((x, y, w, h), [float(v) for v in vector]))
        return found
    except Exception as exc:  # noqa: BLE001
        log.warning("Analiza twarzy nie powiodła się: %s", exc)
        return []


@lru_cache(maxsize=1)
def references() -> list[dict]:
    if not REFS_PATH.exists():
        return []
    return [ref for ref in json.loads(REFS_PATH.read_text(encoding="utf-8")) if ref.get("embedding")]


def best_match(vector: list[float], refs: list[dict]) -> tuple[str, float] | None:
    best = None
    for ref in refs:
        score = sum(a * b for a, b in zip(vector, ref["embedding"], strict=True))
        if best is None or score > best[1]:
            best = (ref["name"], score)
    return best if best and best[1] >= MATCH_THRESHOLD else None


def match_faces(image_bytes: bytes, refs: list[dict] | None = None) -> list[FaceMatch]:
    """Osoby z bazy referencyjnej rozpoznane na obrazie, każda raz, z najlepszym wynikiem."""
    refs = references() if refs is None else refs
    if not refs:
        return []
    best: dict[str, FaceMatch] = {}
    for box, vector in embeddings(image_bytes):
        hit = best_match(vector, refs)
        if hit and (hit[0] not in best or hit[1] > best[hit[0]].score):
            best[hit[0]] = FaceMatch(hit[0], round(hit[1], 3), box)
    return list(best.values())
