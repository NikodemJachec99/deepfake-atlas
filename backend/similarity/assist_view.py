"""Sugestia Jev dla krawędzi w API (#73). Tylko odczyt: nie wywołuje Jev i niczego nie zapisuje.

Sugestię liczy `jev_review` (docs/jev.md). Tutaj pokazujemy stan adaptera i ostatnią zapisaną sugestię:
w trybie `off` żadnej, w `shadow` tylko fakt jej istnienia, w `on` także odpowiedź. Obok są wyłącznie
rzeczywiste przesłanki (struktura, która trafia do modelu) i zapisane decyzje analityka. Rozumowania modelu
nie ma i nie udajemy go. Kolejności precedensów model nie ustala: ewaluacja #72 tego nie potwierdziła.
"""

from datetime import datetime

from django.conf import settings

from similarity import assist
from similarity.models import AssistSuggestion, Edge, EdgeDecision

UNCERTAIN_BELOW = 0.7  # confidence poniżej tego progu oznaczamy jako niepewną; próg do strojenia na walidacji
NOTICE = (
    "Sugestia modelu, nie dowód. Nie zmienia krawędzi, grup ani decyzji. W ewaluacji #72 model nie oceniał "
    "struktury przesłanek lepiej niż reguła, więc to wynik pomocniczy."
)
LABELS = {"przeglad": "Do przeglądu przez człowieka", "spojne": "Przesłanki niezależne i spójne"}


def build(edge: Edge) -> dict:
    mode = getattr(settings, "JEV_MODE", "off")
    mode = mode if mode in ("off", "shadow", "on") else "off"
    model = getattr(settings, "JEV_MODEL", "")
    version = getattr(settings, "JEV_QUESTION", "") or assist.QUESTION_VERSION
    state = assist.review_state(edge)
    body_now = assist.request_body(state, model, version) if version in assist.QUESTIONS else None
    latest = (AssistSuggestion.objects.filter(edge=edge, task=assist.TASK_REVIEW).order_by("-created_at", "-id").first()
              if mode != "off" else None)
    decision = EdgeDecision.objects.filter(edge=edge).order_by("-created_at", "-id").first()

    out = {
        "edge": edge.pk,
        "mode": mode,
        "model": model or None,
        "question_version": version,
        "question": assist.QUESTIONS[version].question["instructions"] if version in assist.QUESTIONS else None,
        "case_data_allowed": bool(getattr(settings, "JEV_ALLOW_CASE_DATA", False)),
        "visible": False,
        "status": "disabled" if mode == "off" else ("none" if latest is None else latest.status),
        "suggestion": None,
        "premises": state,
        "analyst": {
            "verdict": edge.verdict,
            "reason": edge.verdict_reason or None,
            "decided_at": decision.created_at.isoformat() if decision else None,
        },
        "precedent_ranking": "not_validated",
        "notice": NOTICE,
    }
    if latest is None:
        return out
    stale = not _same_instant(latest.edge_version, edge) or (body_now is not None and latest.state_fingerprint != assist.fingerprint(body_now))
    if mode == "shadow":
        out["status"] = "shadow"
        out["shadow"] = {"recorded_at": latest.created_at.isoformat(), "status": latest.status}
        return out
    uncertain = latest.status == "abstain" or (latest.confidence is not None and latest.confidence < UNCERTAIN_BELOW)
    out["visible"] = latest.status in ("ok", "abstain")
    out["suggestion"] = {
        "status": latest.status,
        "answer": latest.answer or None,
        "label": LABELS.get(latest.answer),
        "probabilities": latest.probabilities,
        "confidence": latest.confidence,
        "uncertain": uncertain,
        "model": latest.model,
        "served_model": latest.served_model or None,
        "question_version": latest.question_version,
        "created_at": latest.created_at.isoformat(),
        "stale": stale,
        "error": latest.error or None,
    }
    return out


def _same_instant(version: str, edge: Edge) -> bool:
    try:
        return datetime.fromisoformat(version) == edge.updated_at
    except ValueError:
        return False
