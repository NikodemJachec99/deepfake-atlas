"""Zapis reklam z bibliotek. Każdy skan zostawia migawkę, jeśli treść się zmieniła."""

import hashlib
import json

from django.utils import timezone

from .models import Ad, AdSnapshot, Advertiser


def upsert_advertiser(source: str, external_id: str, name: str = "", payer: str = "", raw: dict | None = None):
    if not external_id:
        return None
    advertiser, _ = Advertiser.objects.update_or_create(
        source=source, external_id=str(external_id), defaults={"name": name, "payer": payer, "raw": raw or {}}
    )
    return advertiser


def upsert_ad(source: str, external_id: str, *, advertiser=None, raw: dict | None = None, **fields) -> tuple[Ad, bool]:
    """Tworzy lub odświeża reklamę. Zwraca (reklama, czy_nowa)."""
    now = timezone.now()
    raw = raw or {}
    ad, created = Ad.objects.get_or_create(
        source=source,
        external_id=str(external_id),
        defaults={**fields, "advertiser": advertiser, "raw": raw, "first_seen": fields.get("first_seen") or now, "last_seen": now},
    )
    if not created:
        for name, value in fields.items():
            if value:
                setattr(ad, name, value)
        ad.advertiser = advertiser or ad.advertiser
        ad.raw = raw
        ad.last_seen = now
        ad.save()

    content_hash = hashlib.sha1(json.dumps(raw, sort_keys=True, default=str).encode()).hexdigest()
    last = ad.snapshots.order_by("-observed_at").first()
    if last is None or last.content_hash != content_hash:
        AdSnapshot.objects.create(ad=ad, observed_at=now, content_hash=content_hash, raw=raw)
    return ad, created
