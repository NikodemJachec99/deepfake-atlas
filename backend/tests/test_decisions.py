"""Pamięć sprzeciwu: decyzje z powodem, migawka podstawy, historia. Dane zmyślone."""

import importlib
from unittest import mock

import pytest
from django.apps import apps
from rest_framework.test import APIClient

from evidence.models import AuditLog
from similarity import decisions
from similarity.models import Edge, EdgeDecision
from similarity.service import link_ad
from tests import fakes
from tests.test_extractors import LANDING_A
from tests.test_pipeline import analyze_url

pytestmark = pytest.mark.django_db
META_TOKEN = "EAAB" + "x7" * 20


@pytest.fixture
def edge():
    fakes.page("https://a.example/1", LANDING_A)
    fakes.page("https://b.example/2", LANDING_A)
    analyze_url("https://a.example/1")
    analyze_url("https://b.example/2")
    return Edge.objects.get()


def _decide(edge, **body):
    return APIClient().post(f"/api/edges/{edge.pk}/verdict", body, format="json")


def test_decision_with_reason_keeps_snapshot_and_history(edge):
    before = (edge.relation, edge.bits, edge.probability, edge.updated_at, list(edge.evidence.values_list("pk", flat=True)))
    response = _decide(edge, verdict="rejected", reason="shared_tool", note="ten sam silnik lejka")
    assert response.status_code == 200
    body = response.json()
    assert (body["verdict"], body["verdict_reason"], body["verdict_note"]) == ("rejected", "shared_tool", "ten sam silnik lejka")

    edge.refresh_from_db()
    # decyzja nie zmienia wag, relacji, dowodów ani wersji krawędzi
    assert (edge.relation, edge.bits, edge.probability, edge.updated_at, list(edge.evidence.values_list("pk", flat=True))) == before

    history = APIClient().get(f"/api/edges/{edge.pk}/decisions").json()
    assert history["current"] == "rejected"
    [decision] = history["decisions"]
    assert decision["reason_label"].startswith("Wspólne narzędzie")
    assert decision["previous_verdict"] == "" and decision["legacy"] is False and decision["has_snapshot"] is True
    snap = decision["snapshot"]
    assert snap["relation"] == edge.relation and snap["model_version"] == edge.model_version
    assert snap["edge_version"] == edge.updated_at.isoformat()
    assert {e["kind"] for e in snap["evidence"]} == set(edge.evidence.values_list("kind", flat=True))
    assert snap["groups"]["a"]["campaign"] and snap["groups"]["a"]["campaign"] == snap["groups"]["b"]["campaign"]
    assert AuditLog.objects.get(action="edge.verdict").payload["decision"] == decision["id"]


def test_changed_decision_is_a_new_entry(edge):
    _decide(edge, verdict="rejected", reason="shared_infrastructure")
    _decide(edge, verdict="confirmed", reason="confirmed_by_analyst", note="potwierdzone w panelu")
    rows = APIClient().get(f"/api/edges/{edge.pk}/decisions").json()["decisions"]
    assert [(r["verdict"], r["previous_verdict"], r["reason"]) for r in rows] == [
        ("confirmed", "rejected", "confirmed_by_analyst"),
        ("rejected", "", "shared_infrastructure"),
    ]
    edge.refresh_from_db()
    assert (edge.verdict, edge.verdict_reason) == ("confirmed", "confirmed_by_analyst")


def test_missing_reason_is_unknown_and_old_client_works(edge):
    response = _decide(edge, verdict="unsure", note="")
    assert response.status_code == 200 and response.json()["verdict_reason"] == "unknown"
    assert EdgeDecision.objects.get().reason == "unknown"
    assert _decide(edge, verdict="rejected", reason="unknown").status_code == 400  # "nieznany" nie jest powodem do wyboru
    assert _decide(edge, verdict="rejected", reason="cos_innego").status_code == 400


def test_snapshot_survives_recomputed_evidence(edge):
    _decide(edge, verdict="confirmed", reason="confirmed_by_analyst")
    stored = EdgeDecision.objects.get().snapshot
    old_ids = set(edge.evidence.values_list("pk", flat=True))
    link_ad(edge.ad_b)  # przeliczenie przebudowuje EdgeEvidence
    assert set(Edge.objects.get().evidence.values_list("pk", flat=True)).isdisjoint(old_ids)
    assert EdgeDecision.objects.get().snapshot == stored


def test_note_and_urls_are_redacted(edge):
    note = f"token z reklamy {META_TOKEN} i adres https://x.example/lp?access_token=abc123secret&utm=fb"
    _decide(edge, verdict="rejected", reason="other", note=note)
    saved = APIClient().get(f"/api/edges/{edge.pk}/decisions").json()["decisions"][0]["note"]
    assert META_TOKEN not in saved and "abc123secret" not in saved
    assert "sha256-" in saved and "utm=fb" in saved
    edge.refresh_from_db()
    assert META_TOKEN not in edge.verdict_note
    assert META_TOKEN not in str(AuditLog.objects.get().payload)


def test_decision_is_atomic(edge):
    with mock.patch.object(AuditLog.objects, "create", side_effect=RuntimeError("awaria zapisu")):
        with pytest.raises(RuntimeError):
            decisions.decide(edge.pk, "rejected", "shared_tool", "x")
    edge.refresh_from_db()
    assert edge.verdict == "" and edge.verdict_reason == ""
    assert not EdgeDecision.objects.exists()


def test_history_survives_deleted_edge(edge):
    _decide(edge, verdict="rejected", reason="shared_tool")
    ad_a, ad_b = edge.ad_a_id, edge.ad_b_id
    edge.delete()
    decision = EdgeDecision.objects.get()
    assert decision.edge_id is None and (decision.ad_a_id, decision.ad_b_id) == (ad_a, ad_b)
    assert decision.snapshot["relation"]


def test_legacy_decisions_are_migrated_as_unknown(edge):
    migration = importlib.import_module("similarity.migrations.0004_edge_decision")
    AuditLog.objects.create(action="edge.verdict", object_type="edge", object_id=str(edge.pk), payload={"verdict": "unsure", "note": "stara"})
    AuditLog.objects.create(action="edge.verdict", object_type="edge", object_id=str(edge.pk), payload={"verdict": "rejected", "note": "inny operator"})
    Edge.objects.filter(pk=edge.pk).update(verdict="rejected", verdict_note="inny operator")
    migration.legacy_decisions(apps, None)
    rows = list(EdgeDecision.objects.order_by("created_at", "id"))
    assert [(r.verdict, r.previous_verdict, r.reason, r.legacy, r.snapshot) for r in rows] == [
        ("unsure", "", "unknown", True, {}),
        ("rejected", "unsure", "unknown", True, {}),
    ]
    history = APIClient().get(f"/api/edges/{edge.pk}/decisions").json()["decisions"]
    assert history[0]["has_snapshot"] is False and history[0]["snapshot"] is None
    assert Edge.objects.get().verdict_reason == "unknown"


def test_reasons_are_listed_for_the_interface():
    reasons = APIClient().get("/api/kinds").json()["verdict_reasons"]
    assert {r["value"] for r in reasons} == {c for c, _ in EdgeDecision.Reason.choices} - {"unknown"}
