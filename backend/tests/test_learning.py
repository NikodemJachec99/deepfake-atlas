import json
import random

import pytest
from django.core.management import call_command
from rest_framework.test import APIClient

from similarity import fusion, learning
from similarity.fusion import Shared, Soft, WeightsError, score_pair

N_ADS = 60


@pytest.fixture
def client():
    return APIClient()


def make_pair(a, b, kinds, soft=()):
    shared = [Shared(k, f"v{a}-{b}", df=2) for k in kinds]
    soft = [Soft(k, 0.95) for k in soft]
    return learning.Pair(a, b, shared, soft, 1000, learning.agreement(shared, soft))


def synthetic_pairs(seed=1):
    """10 grup po 6 reklam. W grupie: telefon 90%, ASN 50%. Poza grupą (kandydaci): ASN 30%, telefon nigdy, CDN w obu."""
    rng = random.Random(seed)
    pairs = []
    for g in range(10):
        ids = range(g * 6, g * 6 + 6)
        for a in ids:
            for b in ids:
                if a < b:
                    kinds = []
                    if rng.random() < 0.9:
                        kinds.append("phone")
                    if rng.random() < 0.5:
                        kinds.append("asn")
                    if rng.random() < 0.9:
                        kinds.append("cdn")
                    pairs.append(make_pair(a, b, kinds or ["cdn"]))
    for _ in range(250):
        a, b = sorted(rng.sample(range(N_ADS), 2))
        if a // 6 == b // 6:
            continue
        kinds = ["topic"]
        if rng.random() < 0.3:
            kinds.append("asn")
        if rng.random() < 0.9:
            kinds.append("cdn")
        pairs.append(make_pair(a, b, kinds))
    return pairs


def test_em_gives_higher_m_to_marker_shared_within_groups():
    pairs = synthetic_pairs()
    fit = learning.fit_em([p.agree for p in pairs], N_ADS, ["phone", "asn", "cdn", "topic"])
    assert fit.converged and fit.iterations < learning.MAX_ITER
    assert fit.m["phone"] > 0.7 > fit.m["asn"]
    assert fit.u["phone"] < 0.05
    bits = {c: learning.kind_bits(c, fit.m[c], fit.u[c]) for c in ("phone", "asn", "cdn")}
    assert bits["phone"] > 5
    assert bits["asn"] < 2  # zgodny prawie tak samo często poza grupą
    assert bits["cdn"] < 1  # CDN zgadza się wszędzie: nic nie wnosi


def test_build_weights_marks_rare_kinds_as_expert_and_is_serialisable():
    data = learning.build_weights(synthetic_pairs(), N_ADS, bootstrap=5, seed=3)
    json.dumps(data)
    assert data["kinds"]["phone"]["source"] == "em"
    assert data["kinds"]["iban"]["source"] == "expert"  # żadnej zgodności w parach
    assert data["kinds"]["iban"]["bits"] == data["kinds"]["iban"]["expert_bits"]
    assert data["meta"]["pairs"] == len(synthetic_pairs())
    assert data["meta"]["model_version"] == "fs-6"
    assert data["meta"]["converged"] is True
    assert all(v["u"] > 0 for v in data["kinds"].values())  # wygładzanie: u nigdy nie jest zerem
    assert all(0 <= v["bits"] <= fusion.KINDS[c].cap for c, v in data["kinds"].items())


@pytest.fixture
def learned_file(tmp_path):
    data = learning.build_weights(synthetic_pairs(), N_ADS, bootstrap=0)
    data["kinds"]["phone"].update(m=0.5, u=1e-3, bits=9.0, source="em")  # wyraźnie inne niż ekspercka waga 18
    path = tmp_path / "wagi.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_learned_switch_changes_version_and_bits(settings, learned_file):
    shared = [Shared("phone", "+48 000 000 000", df=2)]
    expert = score_pair(shared, [], 100_000)
    assert fusion.MODEL_VERSION == "fs-5.1"
    settings.MODEL_WEIGHTS = "learned"
    settings.MODEL_WEIGHTS_PATH = learned_file
    learned = score_pair(shared, [], 100_000)
    assert fusion.MODEL_VERSION == "fs-6"
    assert learned.bits < expert.bits


def test_learned_without_file_is_a_clear_error(settings, tmp_path):
    settings.MODEL_WEIGHTS = "learned"
    settings.MODEL_WEIGHTS_PATH = tmp_path / "nie-ma.json"
    with pytest.raises(WeightsError, match="estimate_weights"):
        score_pair([Shared("phone", "x", df=2)], [], 1000)


def test_use_weights_overrides_settings(settings, learned_file):
    settings.MODEL_WEIGHTS = "learned"
    settings.MODEL_WEIGHTS_PATH = learned_file
    shared = [Shared("phone", "x", df=2)]
    with fusion.use_weights(None):
        assert fusion.model_version() == "fs-5.1"
        expert_bits = score_pair(shared, [], 1000).bits
    assert fusion.model_version() == "fs-6"
    assert score_pair(shared, [], 1000).bits < expert_bits


def test_compare_counts_changes_between_weight_sets(learned_file):
    data = json.loads(learned_file.read_text(encoding="utf-8"))
    pairs = synthetic_pairs()
    # Pary z samym telefonem: ekspercko jeden marker rozstrzygający, uczone wagi go osłabiają.
    pairs.append(make_pair(100, 101, ["phone"]))
    report = learning.compare(pairs, data)
    assert report["pairs"] == len(pairs)
    assert report["same_source"]["expert"] >= report["same_source"]["learned"]
    assert report["kind_differences"][0]["diff"] != 0
    assert report["core"]["pairs"] == 0


def test_calibration_without_decisions_says_so():
    result = learning.calibrate([])
    assert result["fitted"] is False
    assert result["note"] == "brak kalibracji: 0 decyzji"


def test_calibration_fits_logistic_on_decisions():
    rng = random.Random(5)
    samples = []
    for _ in range(80):
        bits = rng.uniform(0, 30)
        label = 1 if bits + rng.gauss(0, 3) > 15 else 0
        samples.append((bits, {"infra": bits / 2, "track": bits / 2}, label))
    result = learning.calibrate(samples)
    assert result["fitted"] is True and result["decisions"] == 80
    c = result["coefficients"]
    low = learning.calibrated_probability(c, 3, {"infra": 1.5, "track": 1.5})
    high = learning.calibrated_probability(c, 28, {"infra": 14, "track": 14})
    assert low < 0.2 < 0.8 < high


@pytest.mark.django_db
def test_command_writes_loadable_file_and_reports_no_calibration(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(learning, "collect_pairs", lambda source: (synthetic_pairs(), N_ADS))
    out = tmp_path / "modele" / "wagi.json"
    call_command("estimate_weights", "--out", str(out), "--bootstrap", "3")
    text = capsys.readouterr().out
    assert "brak kalibracji: 0 decyzji" in text
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["calibration"]["fitted"] is False
    assert data["comparison"]["pairs"] == len(synthetic_pairs())
    weights = fusion.load_weights(out)
    assert weights.kinds["phone"].source == "em"


def test_weights_api_without_file_returns_expert_only(client, settings, tmp_path):
    settings.MODEL_WEIGHTS_PATH = tmp_path / "nie-ma.json"
    body = client.get("/api/weights").json()
    assert body["active"] == "expert" and body["model_version"] == "fs-5.1"
    assert body["learned_available"] is False and body["calibration"] is None
    phone = next(k for k in body["kinds"] if k["code"] == "phone")
    assert phone["learned"] is None and phone["expert"]["m"] == 0.9 and phone["family"] == "narr"
    assert all(k["cap"] > 0 for k in body["kinds"])


def test_weights_api_with_file_shows_both(client, settings, learned_file):
    settings.MODEL_WEIGHTS_PATH = learned_file
    body = client.get("/api/weights").json()
    assert body["learned_available"] is True and body["active"] == "expert"
    phone = next(k for k in body["kinds"] if k["code"] == "phone")
    assert phone["learned"]["bits"] == 9.0 and phone["expert"]["bits"] == 18.0
    assert body["meta"]["model_version"] == "fs-6"


def test_weights_api_learned_without_file_reports_error(client, settings, tmp_path):
    settings.MODEL_WEIGHTS = "learned"
    settings.MODEL_WEIGHTS_PATH = tmp_path / "nie-ma.json"
    body = client.get("/api/weights").json()
    assert body["active"] == "expert" and "estimate_weights" in body["learned_error"]
