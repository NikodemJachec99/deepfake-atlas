"""Opcjonalny adapter usługi Jev (`POST /v1/systemone`). Dane trafiają poza infrastrukturę projektu.

Zadanie MVP: czy istniejąca krawędź wymaga przeglądu człowieka, na podstawie samej struktury przesłanek.
Do modelu idzie stan zbudowany z pól policzonych przez silnik dowodowy: relacja, bity, rodziny, grupy
śladów. Bez wartości śladów, adresów, tekstów stron i reklam, tokenów i danych osobowych.

Wynik jest doradczy i trafia do `AssistSuggestion`. Adapter nie zmienia krawędzi, wag, dowodów, grup
ani decyzji. Domyślnie wyłączony. Każdy błąd usługi to zapisany status, a nie wyjątek dla wywołującego.
Model nie generuje tekstu: czytamy tylko klucz odpowiedzi z listy, którą sami podaliśmy.
"""

import hashlib
import json
import math
import time
from dataclasses import dataclass, field

import httpx
from django.conf import settings

from evidence.kinds import CONCEPT_FAMILIES, KINDS
from similarity.models import AssistSuggestion, Edge
from similarity.weakest import group_label, group_of

TASK_REVIEW = "edge_review"
QUESTION_VERSION = "edge-review-v1"
MAX_STATE_CHARS = 6000
MAX_BODY_BYTES = 256 * 1024  # odpowiedź większa od tego to nie jest odpowiedź na nasze pytanie

REVIEW_QUESTION = {
    "type": "choice",
    "instructions": (
        "Stan opisuje powiązanie dwóch reklam wyliczone przez system dowodowy: relację, siłę w bitach i grupy śladów. "
        "Ślady silnika lejka i wspólne motywy (osoba, marka, tematyka) mogą pochodzić od różnych operatorów. "
        "Czy to powiązanie powinien sprawdzić człowiek?"
    ),
    "criteria": {
        "przeglad": "przesłanki są niepełne, sprzeczne albo pochodzą z jednej przyczyny, potrzebna ocena człowieka",
        "spojne": "przesłanki pochodzą z kilku niezależnych grup i są spójne z wyliczoną relacją",
    },
}
ANSWERS = tuple(REVIEW_QUESTION["criteria"])


class AssistDisabled(Exception):
    """Adapter wyłączony albo źle skonfigurowany. Nic nie jest wysyłane ani zapisywane."""


@dataclass
class Config:
    url: str
    mode: str
    model: str = ""
    revision: str = ""
    variant: str = ""
    api_key: str = ""
    timeout: float = 20.0
    max_error: float | None = None
    allow_case_data: bool = False

    @classmethod
    def from_settings(cls) -> "Config":
        return cls(
            url="https://api.typesafe.ai",
            mode=getattr(settings, "JEV_MODE", "off"),
            model=getattr(settings, "JEV_MODEL", ""),
            api_key=getattr(settings, "TYPESAFE_API_KEY", ""),
            timeout=float(getattr(settings, "JEV_TIMEOUT", 20.0)),
            allow_case_data=getattr(settings, "JEV_ALLOW_CASE_DATA", False),
        )

    def check(self) -> None:
        if self.mode not in ("shadow", "on"):
            raise AssistDisabled("Jev wyłączony (JEV_MODE=off)")
        if self.url != "https://api.typesafe.ai":
            raise AssistDisabled("Jev wymaga oficjalnego adresu HTTPS")
        if not self.model or self.model in ("jev-latest", "jev-preview"):
            raise AssistDisabled("JEV_MODEL musi wskazywać przypiętą wersję modelu")
        if not self.api_key:
            raise AssistDisabled("brak TYPESAFE_API_KEY")
        if not self.allow_case_data:
            raise AssistDisabled("wysyłanie danych spraw wyłączone; konieczne potwierdzenie uprawnienia do przekazania dostawcy")



def review_state(edge: Edge) -> dict:
    """Struktura przesłanek krawędzi bez wartości śladów."""
    groups: dict[str, dict] = {}
    for row in edge.evidence.all():
        if row.weight_bits <= 0:
            continue
        group = group_of(row.kind)
        entry = groups.setdefault(group, {"grupa": group_label(group), "slady": 0, "bity": 0.0, "rozstrzygajacy": False})
        entry["slady"] += 1
        entry["bity"] += row.weight_bits
        entry["rozstrzygajacy"] = entry["rozstrzygajacy"] or row.decisive
    independent = [g for g in groups if g not in ("kit", "motif")]
    backend = [g for g in independent if not _concept(g)]
    return {
        "relacja": edge.relation,
        "bity": round(edge.bits, 1),
        "pewnosc": round(edge.probability, 4),
        "rozstrzygajacy_slad": edge.decisive,
        "duplikat": edge.duplicate,
        "grupy_sladow": [
            {**v, "bity": round(v["bity"], 1)} for _, v in sorted(groups.items(), key=lambda kv: (-kv[1]["bity"], kv[0]))
        ],
        "niezalezne_grupy": len(independent),
        "niezalezne_grupy_zaplecza": len(backend),
        "tylko_silnik_lub_motywy": bool(groups) and not independent,
    }


def _concept(group: str) -> bool:
    if group in ("content", "creative", "motif"):
        return True
    kind = KINDS.get(group.partition(":")[2])
    return bool(kind and kind.family in CONCEPT_FAMILIES)


def request_body(state: dict, model: str) -> dict:
    question = dict(REVIEW_QUESTION)
    text = json.dumps(state, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if len(text) > MAX_STATE_CHARS:
        raise ValueError(f"stan ma {len(text)} znaków, limit {MAX_STATE_CHARS}")
    return {"model": model, "state": text, "questions": {"review": question}}


def fingerprint(body: dict) -> str:
    return hashlib.sha256(json.dumps(body, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


@dataclass
class Outcome:
    status: str
    answer: str = ""
    probabilities: dict = field(default_factory=dict)
    confidence: float | None = None
    served_model: str = ""
    latency_ms: int | None = None
    error: str = ""


def parse_answer(payload) -> Outcome:
    """Sprawdza odpowiedź według schematu choice. Wszystko poza nim to błąd, nigdy zgadywana odpowiedź."""
    if not isinstance(payload, dict) or not isinstance(payload.get("answers"), dict):
        return Outcome("error", error="odpowiedź bez pola answers")
    answer = payload["answers"].get("review")
    if not isinstance(answer, dict) or answer.get("type") != "choice":
        return Outcome("error", error="brak odpowiedzi typu choice na pytanie review")
    probs = answer.get("probabilities")
    if not isinstance(probs, dict) or set(probs) != set(ANSWERS):
        return Outcome("error", error="rozkład spoza zadanych odpowiedzi")
    clean = {}
    for key, value in probs.items():
        if not isinstance(value, int | float) or isinstance(value, bool) or not math.isfinite(value) or not 0 <= value <= 1:
            return Outcome("error", error="prawdopodobieństwo poza zakresem 0..1")
        clean[key] = round(float(value), 6)
    if abs(sum(clean.values()) - 1) > 0.02:
        return Outcome("error", error="rozkład nie sumuje się do 1")
    model = str(payload.get("model", ""))[:128]
    if answer.get("abstain") is True:
        return Outcome("abstain", probabilities=clean, served_model=model)
    choice = answer.get("choice")
    if choice not in ANSWERS:
        return Outcome("error", error="wybrana odpowiedź spoza listy")
    return Outcome("ok", answer=choice, probabilities=clean, confidence=clean[choice], served_model=model)


class JevClient:
    def __init__(self, config: Config, transport: httpx.BaseTransport | None = None):
        config.check()
        self.config = config
        headers = {"Authorization": f"Bearer {config.api_key}"} if config.api_key else {}
        self.http = httpx.Client(base_url=config.url.rstrip("/"), timeout=config.timeout, headers=headers, transport=transport,
                                 follow_redirects=False, trust_env=False)

    def ask(self, body: dict) -> Outcome:
        started = time.monotonic()
        try:
            response = self.http.post("/v1/systemone", json=body)
        except httpx.TimeoutException:
            return Outcome("timeout", error=f"brak odpowiedzi w {self.config.timeout:.0f} s")
        except httpx.HTTPError as exc:
            return Outcome("unavailable", error=type(exc).__name__)
        latency = int((time.monotonic() - started) * 1000)
        if response.status_code in (502, 503):
            return Outcome("unavailable", latency_ms=latency, error=f"HTTP {response.status_code}")
        if response.status_code == 504:
            return Outcome("timeout", latency_ms=latency, error="HTTP 504")
        if response.status_code != 200:
            return Outcome("error", latency_ms=latency, error=f"HTTP {response.status_code}")
        if len(response.content) > MAX_BODY_BYTES:
            return Outcome("error", latency_ms=latency, error="odpowiedź za duża")
        try:
            payload = response.json()
        except ValueError:
            return Outcome("error", latency_ms=latency, error="odpowiedź nie jest JSON")
        outcome = parse_answer(payload)
        outcome.latency_ms = latency
        return outcome


def review_edge(edge: Edge, client: JevClient) -> AssistSuggestion:
    """Pyta model o jedną krawędź i zapisuje wynik. Krawędzi i dowodów nie zmienia."""
    config = client.config
    try:
        body = request_body(review_state(edge), config.model)
    except ValueError as exc:
        body, outcome = {"state": "", "questions": {}}, Outcome("error", error=str(exc))
    else:
        outcome = client.ask(body)
    return AssistSuggestion.objects.create(
        edge=edge, ad_a_id=edge.ad_a_id, ad_b_id=edge.ad_b_id, task=TASK_REVIEW, mode=config.mode,
        status=outcome.status, answer=outcome.answer, probabilities=outcome.probabilities, confidence=outcome.confidence,
        model=config.model, revision=config.revision, variant=config.variant, served_model=outcome.served_model,
        question_version=QUESTION_VERSION, state_fingerprint=fingerprint(body), edge_version=edge.updated_at.isoformat(),
        latency_ms=outcome.latency_ms, error=outcome.error[:300],
    )
