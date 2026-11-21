"""Pamięć sprzeciwu: decyzje analityka o krawędziach z powodem i migawką podstawy decyzji.

Decyzja zmienia tylko werdykt krawędzi. Wagi, relacja, dowody i grupy zostają takie, jakie policzył
silnik. Migawka zapisuje to, co analityk widział w chwili decyzji: relację, bity, pewność, wersję
modelu, wersję krawędzi, rodziny i dowody (wartości po redakcji) oraz grupy obu reklam.

API nie ma uwierzytelniania, więc notatka jest widoczna dla każdego, kto ma dostęp do API, tak jak
dotąd `verdict_note`. Przed zapisem zamieniamy w niej sekrety na skróty: parametry z tokenami
w adresach i tokeny dostępu Mety pod dowolną nazwą.
"""

import re

from django.db import transaction
from django.utils import timezone

from ads.models import Ad
from evidence.kinds import FAMILIES, KINDS
from evidence.models import AuditLog
from extractors.url import _META_TOKEN, redact_url, secret_hash

from .models import Edge, EdgeDecision

NOTE_MAX = 4000
VALUE_MAX = 300
_URL = re.compile(r"https?://\S+", re.I)
_WORD = re.compile(r"\S+")


def redact_note(note: str) -> str:
    """Notatka bez sekretów: adresy przez `redact_url`, samodzielne tokeny Mety jako skrót."""
    note = (note or "")[:NOTE_MAX]
    note = _URL.sub(lambda m: redact_url(m.group(0)), note)
    return _WORD.sub(lambda m: secret_hash(m.group(0)) if _META_TOKEN.match(m.group(0)) else m.group(0), note)


def _group_keys(ad: Ad | None) -> dict:
    if ad is None:
        return {"campaign": None, "operator": None}
    campaign = getattr(getattr(ad, "membership", None), "campaign", None)
    operator = getattr(getattr(ad, "operator_membership", None), "operator", None)
    return {"campaign": campaign.key if campaign else None, "operator": operator.key if operator else None}


def snapshot(edge: Edge) -> dict:
    """Stan krawędzi i jej dowodów w tej chwili. Wartości śladów są już zredagowane przy ekstrakcji."""
    ads = {ad.pk: ad for ad in Ad.objects.filter(pk__in=[edge.ad_a_id, edge.ad_b_id]).select_related(
        "membership__campaign", "operator_membership__operator")}
    evidence = []
    for row in edge.evidence.all().order_by("-weight_bits", "kind", "pk"):
        kind = KINDS.get(row.kind)
        evidence.append({
            "kind": row.kind,
            "label": kind.label if kind else row.kind,
            "family": row.family,
            "family_label": FAMILIES.get(row.family, row.family),
            "value_a": row.value_a[:VALUE_MAX],
            "value_b": row.value_b[:VALUE_MAX],
            "similarity": round(row.similarity, 4),
            "df": row.df,
            "corpus_n": row.corpus_n,
            "weight_bits": round(row.weight_bits, 3),
            "decisive": row.decisive,
            "kit": bool(kind and kind.kit),
            "motif": bool(kind and kind.motif),
        })
    return {
        "relation": edge.relation,
        "bits": round(edge.bits, 3),
        "probability": round(edge.probability, 6),
        "decisive": edge.decisive,
        "duplicate": edge.duplicate,
        "families": {f: round(b, 3) for f, b in (edge.families or {}).items()},
        "model_version": edge.model_version,
        "edge_version": edge.updated_at.isoformat() if edge.updated_at else None,
        "evidence": evidence,
        "groups": {"a": _group_keys(ads.get(edge.ad_a_id)), "b": _group_keys(ads.get(edge.ad_b_id))},
        "ads": {
            side: {"id": ad.pk, "source": ad.source, "case": ad.labels.get("case"), "landing_url": redact_url(ad.landing_url)}
            for side, ad in (("a", ads.get(edge.ad_a_id)), ("b", ads.get(edge.ad_b_id)))
            if ad is not None
        },
    }


@transaction.atomic
def decide(edge_id: int, verdict: str, reason: str = EdgeDecision.Reason.UNKNOWN, note: str = "", user=None) -> EdgeDecision:
    """Zapisuje decyzję atomowo: werdykt krawędzi, wpis historii z migawką i dziennik audytu."""
    edge = Edge.objects.select_for_update().get(pk=edge_id)
    note = redact_note(note)
    now = timezone.now()
    decision = EdgeDecision.objects.create(
        edge=edge, ad_a_id=edge.ad_a_id, ad_b_id=edge.ad_b_id, verdict=verdict, previous_verdict=edge.verdict,
        reason=reason, note=note, snapshot=snapshot(edge), user=user, created_at=now,
    )
    # update() zamiast save(): updated_at zostaje, bo to wersja dowodów, a nie decyzji
    Edge.objects.filter(pk=edge.pk).update(verdict=verdict, verdict_reason=reason, verdict_note=note, verdict_by=user, verdict_at=now)
    AuditLog.objects.create(
        user=user, action="edge.verdict", object_type="edge", object_id=str(edge.pk),
        payload={"verdict": verdict, "reason": reason, "note": note, "decision": decision.pk},
    )
    return decision


def serialize(decision: EdgeDecision, with_snapshot: bool = True) -> dict:
    out = {
        "id": decision.pk,
        "edge": decision.edge_id,
        "ad_a": decision.ad_a_id,
        "ad_b": decision.ad_b_id,
        "verdict": decision.verdict,
        "previous_verdict": decision.previous_verdict,
        "reason": decision.reason,
        "reason_label": EdgeDecision.Reason(decision.reason).label,
        "note": decision.note,
        "legacy": decision.legacy,
        "user": decision.user.get_username() if decision.user else None,
        "created_at": decision.created_at.isoformat(),
        "has_snapshot": bool(decision.snapshot),
    }
    if with_snapshot:
        out["snapshot"] = decision.snapshot or None
    return out


def reasons() -> list[dict]:
    return [{"value": value, "label": label} for value, label in EdgeDecision.Reason.choices if value != EdgeDecision.Reason.UNKNOWN]
