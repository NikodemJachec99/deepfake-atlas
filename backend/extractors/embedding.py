"""Wektor znaczenia tekstu: wielojęzyczny model zdaniowy (paraphrase-multilingual-MiniLM-L12-v2, ONNX, int8).

Liczony lokalnie na CPU. Model i tokenizer pobierają się raz do `MODELS_DIR`. Tekst dłuższy niż okno modelu
dzielimy na fragmenty po 128 tokenów i uśredniamy ich wektory (najwyżej 8 fragmentów od początku treści).
Brak modelu albo biblioteki daje None, a analiza idzie dalej bez tego śladu.
"""

import logging
import urllib.request
from functools import lru_cache
from pathlib import Path

from django.conf import settings

log = logging.getLogger(__name__)

DIM = 384
WINDOW = 128
MAX_WINDOWS = 8
MIN_CHARS = 200  # krótszy tekst (sam tytuł, kilka słów z OCR) daje wektor, który nic nie mówi o opowieści
BASE = "https://huggingface.co/Xenova/paraphrase-multilingual-MiniLM-L12-v2/resolve/main/"
FILES = {"model": ("minilm/model_quantized.onnx", BASE + "onnx/model_quantized.onnx"), "tokenizer": ("minilm/tokenizer.json", BASE + "tokenizer.json")}


def path(role: str) -> Path:
    return Path(settings.MODELS_DIR) / FILES[role][0]


def ensure_model(download: bool | None = None) -> bool:
    download = settings.EMBEDDINGS_DOWNLOAD if download is None else download
    for role, (_name, url) in FILES.items():
        target = path(role)
        if target.exists() and target.stat().st_size > 0:
            continue
        if not download:
            return False
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            partial = target.with_suffix(".part")
            with urllib.request.urlopen(url, timeout=300) as response, partial.open("wb") as out:
                while chunk := response.read(1 << 20):
                    out.write(chunk)
            partial.replace(target)
        except OSError as exc:
            log.warning("Nie udało się pobrać modelu tekstu %s: %s", url, exc)
            return False
    return True


@lru_cache(maxsize=1)
def _model():
    import onnxruntime as ort
    import tokenizers

    tokenizer = tokenizers.Tokenizer.from_file(str(path("tokenizer")))
    session = ort.InferenceSession(str(path("model")), providers=["CPUExecutionProvider"])
    return tokenizer, session


def available() -> bool:
    try:
        import onnxruntime  # noqa: F401
        import tokenizers  # noqa: F401
    except ImportError:
        return False
    return ensure_model()


def embed(text: str) -> list[float] | None:
    """Znormalizowany wektor 384 liczb albo None (za krótki tekst, brak modelu, błąd)."""
    text = " ".join((text or "").split())
    if len(text) < MIN_CHARS or not available():
        return None
    try:
        import numpy as np

        tokenizer, session = _model()
        ids = tokenizer.encode(text, add_special_tokens=False).ids
        cls_id, sep_id = tokenizer.token_to_id("<s>"), tokenizer.token_to_id("</s>")
        windows = [ids[i : i + WINDOW - 2] for i in range(0, len(ids), WINDOW - 2)][:MAX_WINDOWS]
        vectors = []
        for window in windows:
            tokens = np.array([[cls_id, *window, sep_id]], dtype=np.int64)
            mask = np.ones_like(tokens)
            hidden = session.run(None, {"input_ids": tokens, "attention_mask": mask, "token_type_ids": np.zeros_like(tokens)})[0][0]
            vectors.append(hidden.mean(axis=0))  # uśrednianie po tokenach, jak w modelu zdaniowym
        vector = np.mean(vectors, axis=0)
        vector = vector / (np.linalg.norm(vector) or 1.0)
        return [float(v) for v in vector]
    except Exception as exc:  # noqa: BLE001
        log.warning("Wektor tekstu nie powiódł się: %s", exc)
        return None


def cosine(a, b) -> float:
    return float(sum(x * y for x, y in zip(a, b, strict=True)))
