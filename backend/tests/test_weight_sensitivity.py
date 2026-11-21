import json

import pytest
from django.core.management import call_command

from ads.models import Ad
from similarity.fusion import Shared, score_pair
from similarity.service import _store_edge
from tests.test_simulation import ENGINE

pytestmark = pytest.mark.django_db
FUNNEL = Shared("funnel_id", "11111111-2222-4333-8444-555555555555", df=2)
ASSET = Shared("asset_host", "zasoby-operatora.example", df=2)


def edge(a, b, shared):
    return _store_edge(a.pk, b.pk, score_pair(shared, [], 1000), {})


def test_sensitivity_reports_fragile_and_robust_edges(capsys):
    ads = [Ad.objects.create(source="capture", external_id=f"t/{i}", labels={"bundle": "t", "case": str(i)}) for i in range(4)]
    edge(ads[0], ads[1], [*ENGINE, FUNNEL])  # odporna: rzadki marker rozstrzygający
    edge(ads[2], ads[3], [*ENGINE, ASSET])   # krucha: dwa potwierdzenia na granicy
    call_command("weight_sensitivity", "--json")
    report = json.loads(capsys.readouterr().out)
    assert report["edges"] == 2 and report["same_source"] == 2
    scenarios = {s["scenario"]: s for s in report["scenarios"]}
    assert scenarios["szansa wstępna 1e-05"]["changed"] == 0
    half = scenarios["wszystkie typy ×0.5"]
    assert all("t/0" not in change for change in half["same_source_changes"])  # odporna krawędź się nie zmienia
    assert Ad.objects.count() == 4  # nic nie zapisuje poza odczytem
