"""Adapter Jev na symulowanym serwisie. Żadnego modelu, sieci ani danych organizatora."""

import json
from io import StringIO

import httpx
import pytest
from django.core.management import CommandError, call_command
from django.test import override_settings

from ads.models import Ad
from evidence.kinds import KINDS
from similarity import assist
from similarity.models import AssistSuggestion, Edge, EdgeEvidence

pytestmark = pytest.mark.django_db
LOCAL = "https://api.typesafe.ai"
SECRET_VALUE = "EAAB" + "z3" * 20


def make_edge(kinds=("kit_path", "url_param_keys", "funnel_id", "person_mention"), relation="same_operator") -> Edge:
    a = Ad.objects.create(source="capture", external_id=f"a/{Ad.objects.count()}", landing_url=f"https://x.example/?t={SECRET_VALUE}")
    b = Ad.objects.create(source="capture", external_id=f"b/{Ad.objects.count()}", text="Jan Testowy, tel. +48 600 100 200")
    edge = Edge.objects.create(ad_a=a, ad_b=b, relation=relation, bits=21.5, probability=0.97, model_version="fs-5")
    for kind in kinds:
        EdgeEvidence.objects.create(edge=edge, family=KINDS[kind].family, kind=kind, value_a=f"wartość-{kind}-{SECRET_VALUE}",
                                    value_b=f"wartość-{kind}", raw_bits=5, weight_bits=5)
    return edge


def config(**overrides) -> assist.Config:
    values = {"url": LOCAL, "mode": "shadow", "model": "jev-1.14.0", "revision": "", "variant": "", "api_key": "k1",
              "timeout": 2.0, "allow_case_data": True}
    return assist.Config(**{**values, **overrides})


def answer(choice="przeglad", probs=None, **extra) -> dict:
    probs = probs or {"przeglad": 0.8, "spojne": 0.2}
    return {"model": "jev-1.14.0", "answers": {"review": {"type": "choice", "choice": choice, "probabilities": probs,
                                                              "confidence": probs.get(choice), **extra}},
            "usage": {"input_tokens": 300, "output_tokens": 0}}


def service(handler):
    seen = []

    def wrapped(request: httpx.Request):
        seen.append(request)
        return handler(request)

    return httpx.MockTransport(wrapped), seen


def test_request_carries_only_structure_and_result_is_stored():
    edge = make_edge()
    before = (edge.relation, edge.bits, edge.updated_at, list(edge.evidence.values_list("pk", "weight_bits")))
    transport, seen = service(lambda r: httpx.Response(200, json=answer()))
    suggestion = assist.review_edge(edge, assist.JevClient(config(api_key="k1"), transport))

    [request] = seen
    assert request.url.path == "/v1/systemone" and request.headers["authorization"] == "Bearer k1"
    body = json.loads(request.content)
    assert set(body["questions"]) == {"review"} and body["questions"]["review"]["type"] == "choice"
    state = json.loads(body["state"])
    assert state["relacja"] == "same_operator" and state["tylko_silnik_lub_motywy"] is False
    assert {g["grupa"] for g in state["grupy_sladow"]} >= {"Ślady silnika lejka"}
    raw = request.content.decode()
    # bez wartości śladów, adresów, tekstów, tokenów i danych osobowych
    for leak in (SECRET_VALUE, "wartość-", "x.example", "Jan Testowy", "600 100 200"):
        assert leak not in raw

    assert (suggestion.status, suggestion.answer, suggestion.confidence) == ("ok", "przeglad", 0.8)
    assert suggestion.probabilities == {"przeglad": 0.8, "spojne": 0.2}
    assert (suggestion.model, suggestion.revision, suggestion.variant, suggestion.served_model) == (
        "jev-1.14.0", "", "", "jev-1.14.0")
    assert suggestion.question_version == assist.QUESTION_VERSION and len(suggestion.state_fingerprint) == 64
    assert suggestion.mode == "shadow" and suggestion.edge_version == edge.updated_at.isoformat()
    # brak skutków ubocznych dla krawędzi i dowodów
    edge.refresh_from_db()
    assert (edge.relation, edge.bits, edge.updated_at, list(edge.evidence.values_list("pk", "weight_bits"))) == before


def test_confidence_is_distinct_from_selected_probability():
    payload = answer()
    payload["answers"]["review"]["confidence"] = 0.42
    outcome = assist.parse_answer(payload)
    assert outcome.status == "ok" and outcome.confidence == 0.42
    assert outcome.probabilities["przeglad"] == 0.8


def test_missing_confidence_is_invalid():
    payload = answer()
    del payload["answers"]["review"]["confidence"]
    assert assist.parse_answer(payload).status == "error"


def test_only_engine_or_motifs_is_flagged_in_state():
    edge = make_edge(kinds=("kit_path", "person_mention"), relation="similar")
    state = assist.review_state(edge)
    assert state["tylko_silnik_lub_motywy"] is True and state["niezalezne_grupy"] == 0


@pytest.mark.parametrize(
    "payload, error",
    [
        ({"answers": {}}, "brak odpowiedzi typu choice"),
        (answer(choice="polacz_operatora", probs={"przeglad": 0.5, "spojne": 0.5}), "wybrana odpowiedź spoza listy"),
        (answer(probs={"przeglad": 0.9, "spojne": 0.1, "inne": 0.0}), "rozkład spoza zadanych"),
        (answer(probs={"przeglad": 1.7, "spojne": -0.7}), "poza zakresem"),
        (answer(probs={"przeglad": 0.9, "spojne": 0.9}), "nie sumuje się"),
        ({"answers": {"review": {"type": "choice", "choice": "przeglad", "probabilities": {"przeglad": "1", "spojne": 0}}}}, "poza zakresem"),
        (["nie", "obiekt"], "bez pola answers"),
    ],
)
def test_invalid_answers_are_errors_not_results(payload, error):
    transport, _ = service(lambda r: httpx.Response(200, json=payload))
    suggestion = assist.review_edge(make_edge(), assist.JevClient(config(), transport))
    assert suggestion.status == "error" and error in suggestion.error
    assert suggestion.answer == "" and suggestion.confidence is None


def test_abstain_is_kept_as_abstain():
    transport, seen = service(lambda r: httpx.Response(200, json=answer(abstain=True)))
    suggestion = assist.review_edge(make_edge(), assist.JevClient(config(), transport))
    assert json.loads(seen[0].content)["model"] == "jev-1.14.0"
    assert suggestion.status == "abstain" and suggestion.answer == ""


@pytest.mark.parametrize(
    "handler, status",
    [
        (lambda r: (_ for _ in ()).throw(httpx.ConnectError("odmowa połączenia")), "unavailable"),
        (lambda r: (_ for _ in ()).throw(httpx.ReadTimeout("za długo")), "timeout"),
        (lambda r: httpx.Response(503, json={"error": "warming up"}), "unavailable"),
        (lambda r: httpx.Response(504, json={"error": "timeout"}), "timeout"),
        (lambda r: httpx.Response(422, json={"error": "bad"}), "error"),
        (lambda r: httpx.Response(402), "error"),
        (lambda r: httpx.Response(429), "error"),
        (lambda r: httpx.Response(200, text="<html>"), "error"),
        (lambda r: httpx.Response(200, content=b"{" + b" " * (assist.MAX_BODY_BYTES + 10) + b"}"), "error"),
        (lambda r: httpx.Response(302, headers={"location": "https://zewnetrzny.example/"}), "error"),
    ],
)
def test_service_failures_become_statuses(handler, status):
    transport, _ = service(handler)
    suggestion = assist.review_edge(make_edge(), assist.JevClient(config(), transport))
    assert suggestion.status == status and suggestion.answer == ""


def test_state_over_limit_is_not_sent(monkeypatch):
    monkeypatch.setattr(assist, "MAX_STATE_CHARS", 50)
    transport, seen = service(lambda r: httpx.Response(200, json=answer()))
    suggestion = assist.review_edge(make_edge(), assist.JevClient(config(), transport))
    assert seen == [] and suggestion.status == "error" and "limit" in suggestion.error


@pytest.mark.parametrize(
    "overrides, message",
    [
        ({"mode": "off"}, "wyłączony"),
        ({"url": "http://api.typesafe.ai"}, "oficjalnego"),
        ({"url": "https://example.org"}, "oficjalnego"),
        ({"model": "jev-latest"}, "przypiętą"),
        ({"model": ""}, "przypiętą"),
        ({"api_key": ""}, "TYPESAFE_API_KEY"),
        ({"allow_case_data": False}, "potwierdzenie"),
    ],
)
def test_disabled_or_unsafe_config_sends_nothing(overrides, message):
    with pytest.raises(assist.AssistDisabled, match=message):
        assist.JevClient(config(**overrides))


def test_command_is_off_by_default_and_writes_nothing():
    make_edge()
    with pytest.raises(CommandError, match="wyłączony"):
        call_command("jev_review")
    assert not AssistSuggestion.objects.exists()


def test_command_stops_when_service_is_down(monkeypatch):
    for _ in range(5):
        make_edge()
    calls = []

    def down(request):
        calls.append(1)
        raise httpx.ConnectError("odmowa połączenia")

    original = assist.JevClient.__init__
    monkeypatch.setattr(assist.JevClient, "__init__", lambda self, cfg, transport=None: original(self, cfg, httpx.MockTransport(down)))
    out = StringIO()
    with override_settings(JEV_MODE="shadow", JEV_MODEL="jev-1.14.0", TYPESAFE_API_KEY="test", JEV_ALLOW_CASE_DATA=True):
        call_command("jev_review", stdout=out)
    assert len(calls) == 3 and "przerywam" in out.getvalue()
    assert set(AssistSuggestion.objects.values_list("status", flat=True)) == {"unavailable"}
    assert Edge.objects.filter(verdict="").count() == 5
