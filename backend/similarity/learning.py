"""Etap 2 modelu: wagi z danych zamiast eksperckich. EM Fellegi-Sunter bez etykiet i kalibracja na decyzjach.

Dla każdej pary kandydatów (te same pary, które ocenia `service.link_ad`) liczymy wektor zgodności:
dla każdego typu markera 1, jeśli para dzieli wartość (marker miękki: podobieństwo co najmniej `hi`).
Klasa ukryta to "ta sama grupa" albo "różne grupy". EM szacuje dla każdego typu:
  m  P(zgodność | ta sama grupa),
  u  P(zgodność | różne grupy),
oraz udział par pasujących. Start z wag eksperckich (`m` i `f0` z kinds.py).

Dwa zastrzeżenia metody, oba widać w raporcie:
- Typy są liczone jako niezależne przy danej klasie, a w rodzinach to nieprawda (ta sama domena to
  zwykle ten sam IP). Dlatego `fusion.score_pair` zostawia rabat w rodzinie, grupy niezależności
  i limit, a EM zmienia tylko m, u i limity wkładu.
- Kandydatów wybiera zgodność na markerze, więc w zbiorze kandydatów zgodność jest zawyżona.
  Dla typów, po których szukamy kandydatów, `u` liczymy względem wszystkich N(N-1)/2 par, nie tylko
  kandydatów. Dla pozostałych typów `u` jest warunkowe (pole `u_basis`).

Moduł nie zapisuje do bazy.
"""

import json
import math
import random
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from evidence.kinds import BAND_OF, CONCEPT_FAMILIES, FAMILIES, KINDS

from . import fusion

MIN_AGREE = 5  # typ ze zgodnością w mniejszej liczbie par zostaje przy wagach eksperckich
PRIOR_M = 2.0  # pseudo-pary wygładzające m ku wartości eksperckiej
PRIOR_U = 2.0  # to samo dla u warunkowego
PRIOR_U_POP = 100.0  # pseudo-pary wygładzające u populacyjne ku częstości bazowej f0
U_MIN = 1e-7
SOFT_M0 = 0.5  # typy miękkie nie mają m ani f0 w kinds.py
SOFT_U0 = 0.005
PI_RANGE = (1e-4, 0.9)
MAX_ITER = 500
TOLERANCE = 1e-7
BORDERLINE = (0.5, 0.99)  # pewność pary, w której relacja jest jeszcze krucha
CORE_KINDS = ("funnel_id", "meta_pixel")  # ślady konta operatora A (docs/dane-organizatora.md)
UNSTABLE_STD_BITS = 3.0
UNSTABLE_SHARE = 0.25
CALIBRATION_MIN = 20  # tyle decyzji (i co najmniej 5 z każdej klasy), żeby w ogóle dopasować regresję


def learnable_kinds() -> list[str]:
    return [code for code, k in KINDS.items() if k.cap > 0]


def kind_groups() -> dict[str, list[str]]:
    """Dwie oddzielne klasy ukryte. Zaplecze (infrastruktura, tracking, szablon, zachowanie) dowodzi wspólnego
    źródła, a treść, kreacja i osoby (rodziny koncepcyjne) tej samej opowieści. Jedna klasa na wszystko myli je ze sobą:
    operator z różnymi kampaniami wyglądałby jak para niepasująca, bo jego strony różnią się treścią."""
    out = {"source": [], "story": []}
    for code in learnable_kinds():
        out["story" if KINDS[code].family in CONCEPT_FAMILIES else "source"].append(code)
    return out


def is_blocking(code: str) -> bool:
    """Po tym typie szukamy kandydatów, więc zgodność w zbiorze kandydatów jest zawyżona."""
    return KINDS[code].candidate or code in BAND_OF or code in ("text_embedding", "image_embedding")


def prior_params(code: str) -> tuple[float, float]:
    k = KINDS[code]
    return (SOFT_M0, SOFT_U0) if k.soft else (k.m, k.f0)


def expert_bits(code: str) -> float:
    k = KINDS[code]
    if k.soft:
        return float(k.cap)
    return max(0.0, min(float(k.cap), math.log2(k.m / k.f0)))


@dataclass
class Pair:
    a: int
    b: int
    shared: list
    soft: list
    corpus_n: int
    agree: frozenset = frozenset()


def agreement(shared: list, soft: list) -> frozenset:
    out = set()
    for s in shared:
        k = KINDS.get(s.kind)
        if k and k.cap > 0 and not k.soft:
            out.add(s.kind)
    for s in soft:
        k = KINDS.get(s.kind)
        if k and k.cap > 0 and k.soft and s.similarity >= k.hi:
            out.add(s.kind)
    return frozenset(out)


def collect_pairs(source: str | None = None) -> tuple[list[Pair], int]:
    """Pary kandydatów między reklamami z jednego źródła, tak jak je widzi `link_ad`. Tylko odczyt."""
    from ads.models import Ad

    from . import service

    ads = Ad.objects.order_by("id")
    if source:
        ads = ads.filter(source=source)
    ids = set(ads.values_list("pk", flat=True))
    corpus_n = service.corpus_size()
    pairs: dict[tuple[int, int], Pair] = {}
    for ad in ads.iterator():
        for item in service.pair_inputs(ad, corpus_n):
            if item.other_id not in ids:
                continue
            key = tuple(sorted((ad.pk, item.other_id)))
            if key not in pairs:
                pairs[key] = Pair(key[0], key[1], item.shared, item.soft, corpus_n, agreement(item.shared, item.soft))
    return list(pairs.values()), len(ids)


@dataclass
class EMResult:
    m: dict[str, float]
    u_cond: dict[str, float]
    u: dict[str, float]
    pi: float
    iterations: int
    converged: bool
    loglik: float
    resp: list[float] = field(default_factory=list)
    n_agree: dict[str, int] = field(default_factory=dict)
    agree_match: dict[str, float] = field(default_factory=dict)
    agree_nonmatch: dict[str, float] = field(default_factory=dict)


def _logit(p: float) -> float:
    return math.log(p / (1 - p))


def _sigmoid(x: float) -> float:
    if x >= 0:
        return 1 / (1 + math.exp(-x))
    e = math.exp(x)
    return e / (1 + e)


def fit_em(agrees: list[frozenset], n_ads: int, kinds: list[str], pi0: float = 0.05, max_iter: int = MAX_ITER) -> EMResult:
    m0 = {c: prior_params(c)[0] for c in kinds}
    u0 = {c: prior_params(c)[1] for c in kinds}
    m = {c: min(max(m0[c], 0.01), 0.999) for c in kinds}
    u = {c: min(max(u0[c], U_MIN), 0.5) for c in kinds}
    pi = pi0
    n = len(agrees)
    resp = [0.0] * n
    iterations, converged = 0, False
    for step in range(1, max_iter + 1):
        iterations = step
        base = sum(math.log(1 - m[c]) - math.log(1 - u[c]) for c in kinds)
        delta = {c: _logit(m[c]) - _logit(u[c]) for c in kinds}
        for i, agree in enumerate(agrees):
            resp[i] = _sigmoid(_logit(pi) + base + sum(delta[c] for c in agree if c in delta))
        sr = sum(resp)
        sn = n - sr
        a_r = dict.fromkeys(kinds, 0.0)
        a_n = dict.fromkeys(kinds, 0.0)
        for agree, r in zip(agrees, resp, strict=True):
            for c in agree:
                if c in a_r:
                    a_r[c] += r
                    a_n[c] += 1 - r
        new_pi = min(max(sr / n, PI_RANGE[0]), PI_RANGE[1])
        new_m = {c: min(max((a_r[c] + PRIOR_M * m0[c]) / (sr + PRIOR_M), 1e-4), 0.999) for c in kinds}
        new_u = {c: min(max((a_n[c] + PRIOR_U * u0[c]) / (sn + PRIOR_U), U_MIN), 0.999) for c in kinds}
        change = max(abs(new_pi - pi), *(abs(new_m[c] - m[c]) for c in kinds), *(abs(new_u[c] - u[c]) for c in kinds))
        pi, m, u = new_pi, new_m, new_u
        if change < TOLERANCE:
            converged = True
            break

    lp, lq = math.log(pi), math.log(1 - pi)
    null_m = sum(math.log(1 - m[c]) for c in kinds)
    null_u = sum(math.log(1 - u[c]) for c in kinds)
    loglik = 0.0
    for agree in agrees:
        la = lp + null_m + sum(math.log(m[c]) - math.log(1 - m[c]) for c in agree if c in m)
        lb = lq + null_u + sum(math.log(u[c]) - math.log(1 - u[c]) for c in agree if c in u)
        top = max(la, lb)
        loglik += top + math.log(math.exp(la - top) + math.exp(lb - top))

    sr = sum(resp)
    sn = n - sr
    n_agree = dict.fromkeys(kinds, 0)
    a_r = dict.fromkeys(kinds, 0.0)
    a_n = dict.fromkeys(kinds, 0.0)
    for agree, r in zip(agrees, resp, strict=True):
        for c in agree:
            if c in a_r:
                n_agree[c] += 1
                a_r[c] += r
                a_n[c] += 1 - r
    total_pairs = max(n_ads * (n_ads - 1) // 2, n)
    nonmatch_total = max(total_pairs - sr, sn)
    u_pop = {}
    for c in kinds:
        if is_blocking(c):
            u_pop[c] = min(max((a_n[c] + PRIOR_U_POP * u0[c]) / (nonmatch_total + PRIOR_U_POP), U_MIN), 0.999)
        else:
            u_pop[c] = u[c]
    return EMResult(m, u, u_pop, pi, iterations, converged, loglik, resp, n_agree, a_r, a_n)


def kind_bits(code: str, m: float, u: float) -> float:
    return max(0.0, min(float(KINDS[code].cap), math.log2(m / u)))


def _bootstrap_ads(pairs: list[Pair], n_ads: int, rng: random.Random) -> list[frozenset]:
    """Próba z losowaniem reklam, nie par: pary jednej reklamy są zależne, więc losowanie par zaniżałoby rozrzut."""
    nodes = sorted({x for p in pairs for x in (p.a, p.b)})
    draws = [rng.randrange(n_ads) for _ in range(n_ads)]
    count: Counter = Counter(nodes[d] for d in draws if d < len(nodes))
    out: list[frozenset] = []
    for p in pairs:
        out.extend([p.agree] * (count[p.a] * count[p.b]))
    return out


def build_weights(pairs: list[Pair], n_ads: int, bootstrap: int = 30, seed: int = 7, source: str | None = None) -> dict:
    """Szacuje wagi i składa słownik do zapisu w JSON."""
    agrees = [p.agree for p in pairs]
    fits: dict[str, EMResult] = {}
    boots: dict[str, list[dict[str, float]]] = {}
    groups = kind_groups()
    rng = random.Random(seed)
    samples = [_bootstrap_ads(pairs, n_ads, rng) for _ in range(bootstrap)]
    for name, members in groups.items():
        keep = frozenset(members)
        fits[name] = fit_em([a & keep for a in agrees], n_ads, members)
        boots[name] = []
        for sample in samples:
            if len(sample) < 10:
                continue
            b = fit_em([a & keep for a in sample], n_ads, members)
            boots[name].append({c: kind_bits(c, b.m[c], b.u[c]) for c in members})

    kinds = {}
    for name, members in groups.items():
        fit = fits[name]
        for code in members:
            k = KINDS[code]
            learned = fit.n_agree[code] >= MIN_AGREE
            m0, u0 = prior_params(code)
            m, u = (fit.m[code], fit.u[code]) if learned else (m0, u0)
            bits = kind_bits(code, m, u) if learned else expert_bits(code)
            series = [b[code] for b in boots[name]]
            std = None
            if learned and len(series) > 1:
                mean = sum(series) / len(series)
                std = math.sqrt(sum((x - mean) ** 2 for x in series) / (len(series) - 1))
            kinds[code] = {
                "label": k.label,
                "family": k.family,
                "family_label": FAMILIES.get(k.family, k.family),
                "class": name,
                "soft": k.soft,
                "source": "em" if learned else "expert",
                "m": round(m, 6),
                "u": round(u, 9),
                "u_basis": "population" if is_blocking(code) else "candidates",
                "bits": round(bits, 3),
                "expert_bits": round(expert_bits(code), 3),
                "pairs_agree": fit.n_agree[code],
                "agree_in_match": round(fit.agree_match[code], 2),
                "agree_in_nonmatch": round(fit.agree_nonmatch[code], 2),
                "bits_std": None if std is None else round(std, 3),
            }

    stds = [v["bits_std"] for v in kinds.values() if v["bits_std"] is not None]
    unstable = sum(1 for s in stds if s > UNSTABLE_STD_BITS)
    unstable_share = (unstable / len(stds)) if stds else 1.0
    all_converged = all(f.converged for f in fits.values())
    meta = {
        "model_version": fusion.LEARNED_VERSION,
        "expert_version": fusion.EXPERT_VERSION,
        "created": datetime.now(UTC).isoformat(timespec="seconds"),
        "source": source or "all",
        "ads": n_ads,
        "pairs": len(pairs),
        "pairs_with_agreement": sum(1 for a in agrees if a),
        "classes": {
            name: {"iterations": f.iterations, "converged": f.converged, "loglik": round(f.loglik, 3),
                   "match_share": round(f.pi, 5), "expected_matches": round(sum(f.resp), 2)}
            for name, f in fits.items()
        },
        "iterations": max(f.iterations for f in fits.values()),
        "converged": all_converged,
        "learned_kinds": sum(1 for v in kinds.values() if v["source"] == "em"),
        "kinds": len(kinds),
        "bootstrap": bootstrap,
        "bootstrap_unit": "ads",
        "unstable_kinds": unstable,
        "unstable_share": round(unstable_share, 3),
        "stable": bool(all_converged and unstable_share <= UNSTABLE_SHARE),
        "min_pairs_per_kind": MIN_AGREE,
    }
    return {"meta": meta, "kinds": kinds, "calibration": None}


def weights_from(data: dict) -> fusion.Weights:
    return fusion.Weights(
        {c: fusion.KindWeight(v["m"], v["u"], v["bits"], v["source"]) for c, v in data["kinds"].items()}, data.get("meta", {})
    )


# --- porównanie wag eksperckich i uczonych ----------------------------------------------------------------

SAME_SOURCE = ("same_campaign", "same_operator")


def compare(pairs: list[Pair], data: dict, labeler=None) -> dict:
    """Ta sama lista par oceniona raz wagami eksperckimi i raz uczonymi."""
    weights = weights_from(data)
    label = labeler or (lambda pair: f"{pair.a}/{pair.b}")
    rows = []
    for pair in pairs:
        with fusion.use_weights(None):
            e = fusion.score_pair(pair.shared, pair.soft, pair.corpus_n)
        with fusion.use_weights(weights):
            n = fusion.score_pair(pair.shared, pair.soft, pair.corpus_n)
        rows.append((pair, e, n))

    changed = [(p, e, n) for p, e, n in rows if e.relation != n.relation]
    transitions = Counter(f"{e.relation}->{n.relation}" for _, e, n in changed)
    same_e = {(p.a, p.b) for p, e, _ in rows if e.relation in SAME_SOURCE}
    same_n = {(p.a, p.b) for p, _, n in rows if n.relation in SAME_SOURCE}

    def in_band(r):
        return r.relation is not None and BORDERLINE[0] <= r.probability < BORDERLINE[1]

    borderline = [(p, e, n) for p, e, n in rows if in_band(e) or in_band(n) or e.relation != n.relation]
    core = {(p.a, p.b) for p, e, _ in rows if e.relation in SAME_SOURCE and any(s.kind in CORE_KINDS for s in p.shared)}

    def components(keys):
        return [c for c in fusion.connected_components(sorted(keys)) if len(c) > 1]

    groups_e, groups_n = components(same_e), components(same_n)
    node_n = {node: i for i, g in enumerate(groups_n) for node in g}
    node_e = {node: i for i, g in enumerate(groups_e) for node in g}
    split = [sorted(g) for g in groups_e if len({node_n.get(x) for x in g}) > 1 or None in {node_n.get(x) for x in g}]
    merged = [sorted(g) for g in groups_n if len({node_e.get(x) for x in g}) > 1]

    differences = []
    for code, v in data["kinds"].items():
        differences.append(
            {"kind": code, "label": v["label"], "expert_bits": v["expert_bits"], "learned_bits": v["bits"], "diff": round(v["bits"] - v["expert_bits"], 2),
             "source": v["source"], "pairs_agree": v["pairs_agree"], "bits_std": v["bits_std"]}
        )
    differences.sort(key=lambda d: abs(d["diff"]), reverse=True)

    def row(p, e, n):
        return {
            "pair": label(p), "expert": e.relation, "learned": n.relation,
            "expert_probability": round(e.probability, 4), "learned_probability": round(n.probability, 4),
            "expert_bits": round(e.bits, 2), "learned_bits": round(n.bits, 2),
            "kinds": sorted({s.kind for s in p.shared} | {s.kind for s in p.soft if s.similarity >= KINDS[s.kind].lo}),
        }

    lost_core = sorted((p.a, p.b) for p, _, n in rows if (p.a, p.b) in core and n.relation not in SAME_SOURCE)
    return {
        "pairs": len(rows),
        "with_relation": {"expert": sum(1 for _, e, _ in rows if e.relation), "learned": sum(1 for _, _, n in rows if n.relation)},
        "same_source": {"expert": len(same_e), "learned": len(same_n), "lost": len(same_e - same_n), "gained": len(same_n - same_e)},
        "relation_changes": len(changed),
        "transitions": dict(transitions),
        "borderline": [row(*x) for x in sorted(borderline, key=lambda t: (t[1].relation == t[2].relation, -t[2].probability))],
        "gained_same_source": [row(p, e, n) for p, e, n in rows if (p.a, p.b) in same_n - same_e],
        "lost_same_source": [row(p, e, n) for p, e, n in rows if (p.a, p.b) in same_e - same_n],
        "kind_differences": differences,
        "core": {"pairs": len(core), "kept": len(core) - len(lost_core), "lost": [label(Pair(a, b, [], [], 0)) for a, b in lost_core]},
        "groups": {"expert": len(groups_e), "learned": len(groups_n), "expert_groups_split": len(split), "learned_groups_merging_expert": len(merged)},
    }


# --- kalibracja na decyzjach analityka --------------------------------------------------------------------

FAMILY_ORDER = sorted(FAMILIES)


def features(bits: float, families: dict[str, float]) -> list[float]:
    return [bits / 10.0, *(families.get(f, 0.0) / 10.0 for f in FAMILY_ORDER)]


def _solve(a: list[list[float]], b: list[float]) -> list[float]:
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(m[r][col]))
        m[col], m[piv] = m[piv], m[col]
        pv = m[col][col]
        if abs(pv) < 1e-12:
            raise ValueError("macierz osobliwa")
        for r in range(n):
            if r != col:
                f = m[r][col] / pv
                for c in range(col, n + 1):
                    m[r][c] -= f * m[col][c]
    return [m[i][n] / m[i][i] for i in range(n)]


def fit_logistic(x: list[list[float]], y: list[int], l2: float = 1.0, iterations: int = 50) -> list[float]:
    """Regresja logistyczna z regularyzacją L2 (bez wyrazu wolnego) metodą Newtona. Zwraca [wyraz wolny, wagi...]."""
    d = len(x[0]) + 1
    beta = [0.0] * d
    rows = [[1.0, *r] for r in x]
    for _ in range(iterations):
        grad = [0.0] * d
        hess = [[0.0] * d for _ in range(d)]
        for r, t in zip(rows, y, strict=True):
            p = _sigmoid(sum(bj * rj for bj, rj in zip(beta, r, strict=True)))
            w = p * (1 - p)
            for i in range(d):
                grad[i] += (p - t) * r[i]
                for j in range(d):
                    hess[i][j] += w * r[i] * r[j]
        for i in range(1, d):
            grad[i] += l2 * beta[i]
            hess[i][i] += l2
        for i in range(d):
            hess[i][i] += 1e-9
        step = _solve(hess, grad)
        beta = [bj - sj for bj, sj in zip(beta, step, strict=True)]
        if max(abs(s) for s in step) < 1e-8:
            break
    return beta


def calibrated_probability(coefficients: dict, bits: float, families: dict[str, float]) -> float:
    z = coefficients["intercept"] + sum(c * f for c, f in zip(coefficients["weights"], features(bits, families), strict=True))
    return _sigmoid(z)


def calibrate(samples: list[tuple[float, dict[str, float], int]]) -> dict:
    """Skalibrowana pewność z decyzji analityka. Próbki: (bity, bity rodzin, 1=potwierdzone, 0=odrzucone)."""
    positives = sum(y for *_, y in samples)
    negatives = len(samples) - positives
    base = {"decisions": len(samples), "confirmed": positives, "rejected": negatives}
    if len(samples) < CALIBRATION_MIN or positives < 5 or negatives < 5:
        return {**base, "fitted": False, "note": f"brak kalibracji: {len(samples)} decyzji"}
    x = [features(b, f) for b, f, _ in samples]
    y = [t for *_, t in samples]
    beta = fit_logistic(x, y)
    coefficients = {"intercept": beta[0], "weights": beta[1:], "features": ["bits", *FAMILY_ORDER], "scale": 10.0}
    probs = [calibrated_probability(coefficients, b, f) for b, f, _ in samples]
    brier = sum((p - t) ** 2 for p, t in zip(probs, y, strict=True)) / len(y)
    return {**base, "fitted": True, "coefficients": coefficients, "brier_train": round(brier, 4)}


def decision_samples(weights: fusion.Weights | None) -> tuple[list[tuple[float, dict[str, float], int]], Counter]:
    """Decyzje analityka o krawędziach (potwierdzone i odrzucone), z bitami policzonymi podanymi wagami."""
    from . import simulation
    from .models import Edge

    counts = Counter()
    samples = []
    for edge in Edge.objects.exclude(verdict="").prefetch_related("evidence"):
        counts[edge.verdict] += 1
        if edge.verdict not in (Edge.Verdict.CONFIRMED, Edge.Verdict.REJECTED):
            continue
        rows = list(edge.evidence.all())
        corpus_n = max((r.corpus_n for r in rows), default=0)
        with fusion.use_weights(weights):
            result = simulation.score(rows, corpus_n)
        samples.append((result.bits, result.families, 1 if edge.verdict == Edge.Verdict.CONFIRMED else 0))
    return samples, counts


# --- widok wag dla API ------------------------------------------------------------------------------------

def weights_overview() -> dict:
    """Wagi eksperckie i uczone (jeśli jest plik) obok siebie, do widoku w interfejsie. Czyta plik, niczego nie zmienia."""
    from django.conf import settings

    path = Path(settings.MODEL_WEIGHTS_PATH)
    learned, error = None, None
    try:
        learned = json.loads(path.read_text(encoding="utf-8"))
        learned["kinds"]
    except FileNotFoundError:
        pass
    except (OSError, ValueError, KeyError, TypeError) as exc:
        learned, error = None, f"Plik z wagami jest nieczytelny: {exc!r}"
    try:
        active = fusion.active_weights()
    except fusion.WeightsError as exc:
        active, error = None, error or str(exc)
    items = []
    for code, k in KINDS.items():
        if k.cap <= 0:
            continue
        row = learned["kinds"].get(code) if learned else None
        items.append(
            {
                "code": code,
                "label": k.label,
                "family": k.family,
                "family_label": FAMILIES.get(k.family, k.family),
                "soft": k.soft,
                "decisive": k.decisive,
                "cap": float(k.cap),
                "expert": {"m": None if k.soft else k.m, "f0": None if k.soft else k.f0, "bits": round(expert_bits(code), 3)},
                "learned": None
                if row is None
                else {key: row[key] for key in ("source", "m", "u", "u_basis", "bits", "pairs_agree", "bits_std")},
            }
        )
    return {
        "active": "learned" if active is not None else "expert",
        "model_version": fusion.model_version() if error is None else fusion.EXPERT_VERSION,
        "learned_available": learned is not None,
        "learned_error": error,
        "meta": None if learned is None else learned.get("meta"),
        "calibration": None if learned is None else learned.get("calibration"),
        "kinds": items,
    }
