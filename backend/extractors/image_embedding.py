"""Wektor obrazu: CLIP ViT-B/32 (Xenova/clip-vit-base-patch32, ONNX int8), licencja MIT (OpenAI CLIP).

Liczony lokalnie na CPU. Model (tylko część obrazowa, 89 MB) pobiera się raz do `MODELS_DIR/clip/`.
Wektor 512 liczb zrzutu reklamy, klatki nagrania albo zrzutu strony mówi o podobnym ujęciu, nie o tym samym pliku.
Dopasowanie zero-shot do opisu marki ("logo TVN24") sprawdziliśmy na danych organizatora i nie działa
(docs/metodyka.md), więc go tu nie ma. Brak modelu albo biblioteki daje None, a analiza idzie dalej bez tego śladu.
"""

import io
import logging
import urllib.request
from functools import lru_cache
from pathlib import Path

from django.conf import settings

log = logging.getLogger(__name__)

DIM = 512
SIZE = 224
MIN_SIDE = 160  # jak w hashu percepcyjnym: ikony i piksele śledzące nie mają ujęcia
MIN_BYTES = 1024
MEAN = (0.48145466, 0.4578275, 0.40821073)
STD = (0.26862954, 0.26130258, 0.27577711)
BASE = "https://huggingface.co/Xenova/clip-vit-base-patch32/resolve/main/"
FILES = {
    "vision": ("clip/vision_model_quantized.onnx", BASE + "onnx/vision_model_quantized.onnx"),
}

def path(role: str) -> Path:
    return Path(settings.MODELS_DIR) / FILES[role][0]


def ensure_model(download: bool | None = None) -> bool:
    download = settings.EMBEDDINGS_DOWNLOAD if download is None else download
    target = path("vision")
    if target.exists() and target.stat().st_size > 0:
        return True
    if not download:
        return False
    url = FILES["vision"][1]
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        partial = target.with_suffix(".part")
        with urllib.request.urlopen(url, timeout=300) as response, partial.open("wb") as out:
            while chunk := response.read(1 << 20):
                out.write(chunk)
        partial.replace(target)
    except OSError as exc:
        log.warning("Nie udało się pobrać modelu obrazu %s: %s", url, exc)
        return False
    return True


def _libraries() -> bool:
    try:
        import numpy  # noqa: F401
        import onnxruntime  # noqa: F401
        import PIL  # noqa: F401
    except ImportError:
        return False
    return True


def available() -> bool:
    return _libraries() and ensure_model()


@lru_cache(maxsize=1)
def _session():
    import onnxruntime as ort

    return ort.InferenceSession(str(path("vision")), providers=["CPUExecutionProvider"])


def _pixels(data: bytes):
    """Obraz jako tablica (1, 3, 224, 224) po normalizacji CLIP albo None, gdy to nie obraz albo jest za mały.

    Cały obraz ściskamy do kwadratu zamiast brać środkowy wycinek: wycinek gubiłby nazwę reklamodawcy u góry
    i przycisk u dołu zrzutu z telefonu.
    """
    if len(data) < MIN_BYTES:
        return None
    import numpy as np
    from PIL import Image

    try:
        with Image.open(io.BytesIO(data)) as image:
            if min(image.size) < MIN_SIDE:
                return None
            rgb = image.convert("RGB").resize((SIZE, SIZE), Image.Resampling.BICUBIC)
            array = np.asarray(rgb, dtype=np.float32) / 255.0
    except Exception:  # noqa: BLE001
        return None
    array = (array - np.array(MEAN, dtype=np.float32)) / np.array(STD, dtype=np.float32)
    return array.transpose(2, 0, 1)[None].astype(np.float32)


def _encode(data: bytes):
    """Surowy, jeszcze nieznormalizowany wynik modelu albo None. Jedyne miejsce, w którym wołamy model obrazu."""
    pixels = _pixels(data)
    if pixels is None:
        return None
    return _session().run(None, {"pixel_values": pixels})[0][0]


def _unit(vector):
    import numpy as np

    vector = np.asarray(vector, dtype=np.float64)
    return vector / (np.linalg.norm(vector) or 1.0)


def embed(data: bytes) -> list[float] | None:
    """Znormalizowany wektor 512 liczb albo None (to nie obraz, za mały, brak modelu, błąd)."""
    if len(data) < MIN_BYTES or not available():
        return None
    try:
        raw = _encode(data)
        return None if raw is None else [float(v) for v in _unit(raw)]
    except Exception as exc:  # noqa: BLE001
        log.warning("Wektor obrazu nie powiódł się: %s", exc)
        return None


def ad_vector(ad, victim: dict | None = None) -> list[float] | None:
    """Wektor reklamy z jednego obrazu: pierwszy zrzut reklamy, a bez niego klatka poglądowa nagrania,
    a bez niej zrzut strony z crawlera. Bajty z magazynu dowodów.

    Jeden obraz, nie średnia: średnia kilku zrzutów interfejsu Facebooka jest podobna do każdej innej
    takiej średniej (0,92 między niezwiązanymi sprawami, przy 0,80 dla pojedynczych obrazów).
    """
    from evidence import store

    raw = ad.raw if isinstance(ad.raw, dict) else {}
    shas = [*raw.get("creatives", [])]
    shas += [v["poster"]["artifact"] for v in raw.get("videos", []) if isinstance(v, dict) and isinstance(v.get("poster"), dict)]
    if (victim or {}).get("screenshot_sha"):
        shas.append(victim["screenshot_sha"])
    for sha in shas:
        try:
            vector = embed(store.get(sha))
        except Exception as exc:  # noqa: BLE001
            log.warning("Brak obrazu %s w magazynie: %s", sha, exc)
            continue
        if vector:
            return vector
    return None


def cosine(a, b) -> float:
    return float(sum(x * y for x, y in zip(a, b, strict=True)))
