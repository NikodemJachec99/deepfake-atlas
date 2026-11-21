"""Ewaluacja Jev na stanach syntetycznych, z symulowanym serwisem. Bez sieci i bez danych spraw."""

import json
from io import StringIO

import httpx
import pytest
from django.core.management import call_command
from django.test import override_settings

from similarity import assist, evaluation
from similarity.models import AssistSuggestion

pytestmark = pytest.mark.django_db


def test_synthetic_cases_are_deterministic_balanced_and_split():
    a, b = evaluation.synthetic_cases(), evaluation.synthetic_cases()
    assert [c["id"] for c in a] == [c["id"] for c in b]
    labels = [c["label"] for c in a]
    assert labels.count("przeglad") == labels.count("spojne") == evaluation.SAMPLE // 2
    assert {c["split"] for c in a} == {"val", "test"}
    for case in a:
        state = case["state"]
        assert set(state) == {"relacja", "bity", "pewnosc", "rozstrzygajacy_slad", "duplikat", "grupy_sladow",
                              "niezalezne_grupy", "niezalezne_grupy_zaplecza", "tylko_silnik_lub_motywy"}


def test_rubric_and_baseline():
    rng = __import__("random").Random(0)
    strong = ["kind:funnel_id", "infra", "kit"]
    state = evaluation.make_state("same_operator", strong, rng)
    assert evaluation.rubric_label("same_operator", strong, state) == "spojne"
    assert evaluation.rubric_label("similar", strong, state) == "przeglad"
    weak = evaluation.make_state("same_campaign", ["kit", "motif"], rng)
    assert evaluation.rubric_label("same_campaign", ["kit", "motif"], weak) == "przeglad"
    assert evaluation.baseline_label(weak) == "przeglad" and evaluation.baseline_label(state) == "spojne"


def test_metrics_count_abstain_as_undecided():
    rows = [
        {"label": "przeglad", "m": "przeglad", "m_p": 0.9},
        {"label": "przeglad", "m": "abstain", "m_p": None},
        {"label": "spojne", "m": "przeglad", "m_p": 0.6},
        {"label": "spojne", "m": "spojne", "m_p": 0.2},
    ]
    m = evaluation.metrics(rows, "m")
    assert (m["n"], m["decided"], m["coverage"]) == (4, 3, 0.75)
    assert (m["recall_przeglad"], m["recall_spojne"], m["precision_przeglad"]) == (1.0, 0.5, 0.5)
    assert m["balanced_accuracy"] == 0.75


def simulated(request):
    """Symulowany Jev: w v3 odróżnia sam silnik i motywy, w pozostałych zawsze druga odpowiedź."""
    body = json.loads(request.content)
    question = body["questions"]["review"]
    keys = list(question["criteria"])
    state = json.loads(body["state"])
    if "operatora?" in question["instructions"]:
        choice = keys[0] if state["tylko_silnik_lub_motywy"] else keys[1]
    else:
        choice = keys[1]
    probs = {k: (0.8 if k == choice else 0.2) for k in keys}
    return httpx.Response(200, json={"model": "jev-1.14.0", "usage": {"input_tokens": 600},
                                     "answers": {"review": {"type": "choice", "choice": choice, "probabilities": probs, "confidence": 0.6}}})


def client(handler=simulated):
    cfg = assist.Config(url="https://api.typesafe.ai", mode="shadow", model="jev-1.14.0", api_key="k", allow_case_data=True)
    return assist.JevClient(cfg, httpx.MockTransport(handler))


def test_run_reports_versions_robustness_and_cost():
    cases = evaluation.synthetic_cases(20)
    report = evaluation.run(client(), list(assist.QUESTIONS), cases, budget_usd=1.0, price_per_mtok=0.042)
    assert report["labels"]["all"] == {"przeglad": 10, "spojne": 10}
    assert report["splits"]["all"]["edge-review-v1"]["recall_spojne"] == 1.0
    assert set(report["robustness"]) == {"sprzeczne", "brak_danych", "mocne", "wstrzykniecie"}
    assert report["robustness"]["sprzeczne"]["edge-review-v3"]["answer"] == "przeglad"
    assert report["input_tokens"] == 600 * (20 * 3 + 4 * 3) and report["stopped"] == ""
    assert not AssistSuggestion.objects.exists()


def test_run_stops_on_budget_and_on_auth():
    cases = evaluation.synthetic_cases(20)
    report = evaluation.run(client(), ["edge-review-v1"], cases, budget_usd=0.0001, price_per_mtok=0.042)
    assert report["stopped"] == "budżet" and report["input_tokens"] < 600 * 20
    calls = []

    def denied(request):
        calls.append(1)
        return httpx.Response(401)

    report = evaluation.run(client(denied), ["edge-review-v1"], cases, budget_usd=1.0, price_per_mtok=0.042)
    assert report["stopped"] == "unauthorized" and len(calls) == 1


def test_command_sends_only_synthetic_states_without_case_data_consent(monkeypatch, tmp_path):
    sent = []

    def handler(request):
        sent.append(json.loads(request.content))
        return simulated(request)

    original = assist.JevClient.__init__
    monkeypatch.setattr(assist.JevClient, "__init__", lambda self, cfg, transport=None: original(self, cfg, httpx.MockTransport(handler)))
    out = tmp_path / "raport.json"
    with override_settings(JEV_MODE="shadow", JEV_MODEL="jev-1.14.0", TYPESAFE_API_KEY="k", JEV_ALLOW_CASE_DATA=False):
        call_command("jev_eval", "--versions", "edge-review-v1", "--sample", "10", "--out", str(out), stdout=StringIO())
    ids = {c["id"] for c in evaluation.synthetic_cases(10)}
    assert len(sent) == 10 + 4 and len(ids) == 10
    assert json.loads(out.read_text(encoding="utf-8"))["model"] == "jev-1.14.0"
    assert not AssistSuggestion.objects.exists()
