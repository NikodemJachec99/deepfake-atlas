"""Zapis markerów reklamy. Jedyna droga, którą markery trafiają do bazy, więc liczniki zawsze się zgadzają."""

from collections.abc import Iterable

from django.db import transaction
from django.db.models import F

from extractors import Observation, minhash

from .kinds import BAND_OF, KINDS
from .models import AdMarker, AdSignature, Artifact, Marker


@transaction.atomic
def attach(ad, observations: Iterable[Observation], artifact: Artifact | None = None) -> int:
    """Dopina markery do reklamy. Zwraca liczbę nowych. Powtórne wywołanie niczego nie dubluje."""
    added = 0
    for obs in dict.fromkeys(observations):
        if obs.kind not in KINDS:
            raise KeyError(f"Nieznany typ markera: {obs.kind}")
        if not obs.value:
            continue
        marker, _ = Marker.objects.get_or_create(
            kind=obs.kind, value_hash=Marker.hash_value(obs.value), defaults={"value": obs.value}
        )
        _, created = AdMarker.objects.get_or_create(
            ad=ad, marker=marker, defaults={"artifact": artifact, "detail": obs.detail}
        )
        if created:
            Marker.objects.filter(pk=marker.pk).update(ad_count=F("ad_count") + 1)
            added += 1
    return added


def set_signature(ad, soft_kind: str, values: list[int]) -> int:
    """Zapisuje sygnaturę markera miękkiego i jej pasma LSH jako markery do wyszukiwania kandydatów."""
    if not values:
        return 0
    AdSignature.objects.update_or_create(ad=ad, kind=soft_kind, defaults={"values": values})
    band_kind = BAND_OF[soft_kind]
    return attach(ad, [Observation(band_kind, band) for band in minhash.bands(values)])
