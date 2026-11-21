"""GET /api/edges/{id}/assist: stan adaptera Jev i zapisana sugestia. Bez sieci, dane zmyślone."""

from unittest import mock

import httpx
import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from ads.models import Ad
from evidence.kinds import KINDS
from similarity import assist, decisions
from similarity.models import AssistSuggestion, Edge, EdgeEvidence

pytestmark = pytest.mark.django_db
SECRET = "EAAB" + "k4" * 20
ON = {"JEV_MODE": "on", "JEV_MODEL": "jev-1.14.0"}


def make_edge() -> Edge:
    a = Ad.objects.create(source="capture", external_id=f"a/{Ad.objects.count()}", landing_url=f"https://x.example/?t={SECRET}")
    b = Ad.objects.create(source="capture", external_id=f"b/{Ad.objects.count()}")
    edge = Edge.objects.create(ad_a=a, ad_b=b, relation="same_operator", bits=30, probability=0.99, model_version="fs-5")
    for kind in ("funnel_id", "domain", "kit_path"):
        EdgeEvidence.objects.create(edge=edge, family=KINDS[kind].family, kind=kind, value_a=f"v-{SECRET}", value_b="v", raw_bits=5, weight_bits=5)
    return edge


def store(edge: Edge, status="ok", answer="przeglad", confidence=0.9, **extra) -> AssistSuggestion:
    body = assist.request_body(assist.review_state(edge), "jev-1.14.0")
    fields = {"edge": edge, "ad_a": edge.ad_a, "ad_b": edge.ad_b, "task": assist.TASK_REVIEW, "mode": "on", "status": status,
              "answer": answer if status == "ok" else "", "probabilities": {"przeglad": 0.8, "spojne": 0.2}, "confidence": confidence,
              "model": "jev-1.14.0", "served_model": "jev-1.14.0", "question_version": assist.QUESTION_VERSION,
              "state_fingerprint": assist.fingerprint(body), "edge_version": edge.updated_at.isoformat(), **extra}
    return AssistSuggestion.objects.create(**fields)


def get(edge: Edge) -> dict:
    return APIClient().get(f"/api/edges/{edge.pk}/assist").json()


def test_off_by_default_shows_nothing_even_if_stored():
    edge = make_edge()
    store(edge)
    body = get(edge)
    assert (body["mode"], body["status"], body["visible"], body["suggestion"]) == ("off", "disabled", False, None)
    assert body["premises"]["relacja"] == "same_operator" and body["precedent_ranking"] == "not_validated"


@override_settings(JEV_MODE="shadow", JEV_MODEL="jev-1.14.0")
def test_shadow_records_but_does_not_reveal_answer():
    edge = make_edge()
    store(edge)
    body = get(edge)
    assert body["status"] == "shadow" and body["visible"] is False and body["suggestion"] is None
    assert body["shadow"]["status"] == "ok" and "przeglad" not in str(body["shadow"])


@override_settings(**ON)
def test_on_shows_answer_with_uncertainty_and_metadata():
    edge = make_edge()
    store(edge, confidence=0.55)
    body = get(edge)
    s = body["suggestion"]
    assert body["visible"] is True and body["status"] == "ok"
    assert (s["answer"], s["label"], s["uncertain"], s["stale"]) == ("przeglad", "Do przeglądu przez człowieka", True, False)
    assert (s["model"], s["served_model"], s["question_version"]) == ("jev-1.14.0", "jev-1.14.0", "edge-review-v1")
    assert body["question"].endswith("Czy to powiązanie powinien sprawdzić człowiek?")
    assert body["notice"].startswith("Sugestia modelu, nie dowód")


@override_settings(**ON)
@pytest.mark.parametrize("status", ["unavailable", "timeout", "error", "unauthorized", "payment", "rate_limited"])
def test_failures_are_reported_not_shown_as_results(status):
    edge = make_edge()
    store(edge, status=status, confidence=None, error="HTTP 503")
    body = get(edge)
    assert body["status"] == status and body["visible"] is False
    assert body["suggestion"]["answer"] is None and body["suggestion"]["label"] is None


@override_settings(**ON)
def test_abstain_is_visible_as_uncertain():
    edge = make_edge()
    store(edge, status="abstain", confidence=None)
    s = get(edge)["suggestion"]
    assert s["status"] == "abstain" and s["uncertain"] is True and s["answer"] is None


@override_settings(**ON)
def test_suggestion_becomes_stale_when_premises_change():
    edge = make_edge()
    store(edge)
    EdgeEvidence.objects.filter(edge=edge, kind="domain").delete()  # inna struktura przesłanek
    assert get(edge)["suggestion"]["stale"] is True


@override_settings(**ON)
def test_no_evidence_values_and_no_side_effects():
    edge = make_edge()
    store(edge)
    decisions.decide(edge.pk, "rejected", "shared_tool")
    edge.refresh_from_db()
    before = (edge.relation, edge.bits, edge.verdict, edge.updated_at, AssistSuggestion.objects.count(), EdgeEvidence.objects.count())
    with mock.patch.object(httpx.Client, "send", side_effect=AssertionError("GET /assist nie może wołać Jev")):
        body = get(edge)
    assert SECRET not in str(body) and "x.example" not in str(body)
    assert body["analyst"]["verdict"] == "rejected" and body["analyst"]["reason"] == "shared_tool"
    edge.refresh_from_db()
    assert (edge.relation, edge.bits, edge.verdict, edge.updated_at, AssistSuggestion.objects.count(), EdgeEvidence.objects.count()) == before


def test_missing_edge_is_404():
    assert APIClient().get("/api/edges/999999/assist").status_code == 404

