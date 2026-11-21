"""Zapis markerów reklamy. Jedyna droga, którą markery trafiają do bazy, więc liczniki zawsze się zgadzają."""

from collections.abc import Iterable

from django.db import transaction
from django.db.models import F

from extractors import Observation, images, minhash

from .kinds import BAND_OF, KINDS
from .models import AdMarker, AdSignature, Artifact, Marker


def _generic(artifact: Artifact | None) -> bool:
    """Brak pliku albo ogólny zapis przechwycenia (HAR, HTML strony), a nie konkretny plik dowodu."""
    return artifact is None or artifact.kind == "har" or artifact.kind.startswith("html")


@transaction.atomic
def attach(ad, observations: Iterable[Observation], artifact: Artifact | None = None) -> int:
    """Dopina markery do reklamy. Zwraca liczbę nowych. Powtórne wywołanie niczego nie dubluje.

    Istniejący marker dostaje plik dowodu, gdy nie miał żadnego albo wskazywał ogólny HAR lub HTML,
    a przychodzi konkretny plik (np. zrzut kreacji).
    """
    added = 0
    for obs in dict.fromkeys(observations):
        if obs.kind not in KINDS:
            raise KeyError(f"Nieznany typ markera: {obs.kind}")
        if not obs.value:
            continue
        marker, _ = Marker.objects.get_or_create(
            kind=obs.kind, value_hash=Marker.hash_value(obs.value), defaults={"value": obs.value}
        )
        link, created = AdMarker.objects.select_related("artifact").get_or_create(
            ad=ad, marker=marker, defaults={"artifact": artifact, "detail": obs.detail}
        )
        if created:
            Marker.objects.filter(pk=marker.pk).update(ad_count=F("ad_count") + 1)
            added += 1
        elif artifact is not None and link.artifact_id != artifact.pk and _generic(link.artifact) and not _generic(artifact):
            link.artifact = artifact
            link.save(update_fields=["artifact"])
        elif artifact is not None and link.artifact_id is None:
            link.artifact = artifact
            link.save(update_fields=["artifact"])
    return added


def _drop_bands(ad, band_kind: str, keep: set[str] = frozenset()) -> None:
    """Usuwa pasma LSH reklamy danego rodzaju poza `keep` i zmniejsza liczniki markerów."""
    stale = [am for am in AdMarker.objects.filter(ad=ad, marker__kind=band_kind).select_related("marker") if am.marker.value not in keep]
    if not stale:
        return
    for am in stale:
        Marker.objects.filter(pk=am.marker_id, ad_count__gt=0).update(ad_count=F("ad_count") - 1)
    AdMarker.objects.filter(pk__in=[am.pk for am in stale]).delete()


@transaction.atomic
def set_signature(ad, soft_kind: str, values: list[int], artifact: Artifact | None = None) -> int:
    """Zapisuje sygnaturę markera miękkiego i jej pasma LSH jako markery do wyszukiwania kandydatów.

    Stare pasma znikają, więc po zmianie treści reklama nie zostaje w indeksie pod dawnym śladem.
    Puste wartości usuwają sygnaturę i pasma.
    """
    band_kind = BAND_OF[soft_kind]
    if not values:
        AdSignature.objects.filter(ad=ad, kind=soft_kind).delete()
        _drop_bands(ad, band_kind)
        return 0
    AdSignature.objects.update_or_create(ad=ad, kind=soft_kind, defaults={"values": values})
    bands = images.bands(values) if soft_kind in ("image_set", "video_frames") else minhash.bands(values)
    _drop_bands(ad, band_kind, keep=set(bands))
    return attach(ad, [Observation(band_kind, band) for band in bands], artifact)
