"""Eksport operatorów i kampanii do STIX 2.1, formatu wymiany wskaźników między zespołami CERT (czyta go też MISP).

Operator to `intrusion-set`, kampania to `campaign` przypisana do operatora (`attributed-to`). Wskaźniki
(`indicator`) powstają z twardych śladów, które mają odpowiednik w obiektach STIX: domeny, adresy IP, numery
certyfikatów i własne hosty zasobów. Identyfikatory trackerów i paneli lejka nie mają obiektu STIX, więc idą
do właściwości `x_scamdna_identifiers` operatora. Osób, tokenów i adresów z tokenami wizyt nie eksportujemy.

Eksportujemy tylko grupy z materiałów zgłoszonych jako podejrzane (przechwycenia i zgłoszenia ręczne).
Reklamy z bibliotek to w większości legalni reklamodawcy i nie mogą trafić do pliku jako intrusion-set.
Identyfikatory obiektów są deterministyczne (UUIDv5), więc kolejny eksport aktualizuje te same obiekty.
"""

import ipaddress
import uuid
from datetime import UTC, datetime

from ads.models import Ad, Source
from evidence.kinds import KINDS
from evidence.models import AdMarker
from similarity.models import Campaign, CampaignMembership, Operator, OperatorMembership

NAMESPACE = uuid.UUID("6f1c2a0e-5d3b-4c8e-9a71-2b4d6e8f0a13")
SUSPICIOUS_SOURCES = (Source.CAPTURE, Source.MANUAL)
DOMAIN_KINDS = {"domain", "redirect_domain", "asset_host"}
IDENTIFIER_KINDS = {"funnel_id", "meta_pixel", "ga4", "ga_ua", "gtm", "google_ads", "yandex_metrica", "tiktok_pixel", "form_action", "kit_path"}


def sid(kind: str, key: str) -> str:
    return f"{kind}--{uuid.uuid5(NAMESPACE, f'{kind}:{key}')}"


def ts(value: datetime | None) -> str:
    value = value or datetime.now(UTC)
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def quote(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def pattern(kind: str, value: str) -> str | None:
    """Wzorzec STIX dla śladu albo None, gdy ślad nie ma odpowiednika w obiektach STIX."""
    if kind in DOMAIN_KINDS:
        return f"[domain-name:value = '{quote(value.lower())}']"
    if kind == "ip":
        try:
            ip = ipaddress.ip_address(value)
        except ValueError:
            return None
        return f"[{'ipv6' if ip.version == 6 else 'ipv4'}-addr:value = '{ip}']"
    if kind == "tls_serial":
        return f"[x509-certificate:serial_number = '{quote(value)}']"
    return None


def bundle(operator_id: int | None = None, campaign_id: int | None = None) -> dict:
    created = ts(None)
    producer = {
        "type": "identity", "spec_version": "2.1", "id": sid("identity", "scamdna"), "created": created, "modified": created,
        "name": "SCAM DNA", "identity_class": "system",
        "description": "Łączenie fałszywych reklam w kampanie i operatorów na podstawie wspólnych śladów. Każde powiązanie ma dowody.",
    }
    objects: list[dict] = [producer]

    operators = Operator.objects.filter(merged_into__isnull=True, memberships__ad__source__in=SUSPICIOUS_SOURCES).distinct()
    if operator_id:
        operators = operators.filter(pk=operator_id)
    if campaign_id:
        operators = operators.filter(memberships__ad__membership__campaign_id=campaign_id).distinct()

    for operator in operators.order_by("pk"):
        ad_ids = list(OperatorMembership.objects.filter(operator=operator, ad__source__in=SUSPICIOUS_SOURCES).values_list("ad_id", flat=True))
        ads = list(Ad.objects.filter(pk__in=ad_ids))
        first = min((a.first_seen for a in ads if a.first_seen), default=None)
        markers: dict[tuple[str, str], set[int]] = {}
        for ad_id, kind, value in AdMarker.objects.filter(ad_id__in=ad_ids, marker__kind__in=DOMAIN_KINDS | {"ip", "tls_serial"} | IDENTIFIER_KINDS).values_list("ad_id", "marker__kind", "marker__value"):
            markers.setdefault((kind, value), set()).add(ad_id)
        # Identyfikatory bez odpowiednika w STIX: tylko te, które łączą co najmniej dwie reklamy operatora.
        identifiers = [
            {"type": kind, "label": KINDS[kind].label, "value": value, "ads": len(ad_set)}
            for (kind, value), ad_set in sorted(markers.items())
            if kind in IDENTIFIER_KINDS and len(ad_set) >= 2
        ]
        intrusion = {
            "type": "intrusion-set", "spec_version": "2.1", "id": sid("intrusion-set", operator.key), "created": created, "modified": created,
            "created_by_ref": producer["id"], "name": f"SCAM DNA {operator.key}",
            "description": f"Operator {operator.key}: {len(ads)} reklam na wspólnym zapleczu. To hipoteza analityczna z dowodami w SCAM DNA, nie identyfikacja osoby.",
            "first_seen": ts(first) if first else None,
            "x_scamdna_key": operator.key,
            "x_scamdna_identifiers": identifiers,
        }
        objects.append({k: v for k, v in intrusion.items() if v is not None})

        campaign_ids = set(CampaignMembership.objects.filter(ad_id__in=ad_ids).values_list("campaign_id", flat=True))
        if campaign_id:
            campaign_ids &= {campaign_id}
        for campaign in Campaign.objects.filter(pk__in=campaign_ids).order_by("pk"):
            count = CampaignMembership.objects.filter(campaign=campaign, ad_id__in=ad_ids).count()
            camp = {
                "type": "campaign", "spec_version": "2.1", "id": sid("campaign", campaign.key), "created": created, "modified": created,
                "created_by_ref": producer["id"], "name": f"SCAM DNA {campaign.key}",
                "description": f"Kampania {campaign.key}: {count} reklam z tym samym źródłem i tą samą opowieścią.", "x_scamdna_key": campaign.key,
            }
            objects.append(camp)
            objects.append(relationship(producer, camp["id"], "attributed-to", intrusion["id"], created, "Kampania prowadzona na zapleczu operatora."))

        for (kind, value), ad_set in sorted(markers.items()):
            stix_pattern = pattern(kind, value)
            if not stix_pattern:
                continue
            indicator = {
                "type": "indicator", "spec_version": "2.1", "id": sid("indicator", f"{operator.key}:{kind}:{value}"), "created": created,
                "modified": created, "created_by_ref": producer["id"], "name": f"{KINDS[kind].label}: {value}",
                "description": f"{KINDS[kind].label} w {len(ad_set)} z {len(ads)} reklam operatora {operator.key}.",
                "indicator_types": ["malicious-activity"], "pattern": stix_pattern, "pattern_type": "stix", "valid_from": ts(first),
            }
            objects.append(indicator)
            objects.append(relationship(producer, indicator["id"], "indicates", intrusion["id"], created, indicator["description"]))

    return {"type": "bundle", "id": f"bundle--{uuid.uuid4()}", "objects": objects}


def relationship(producer: dict, source: str, kind: str, target: str, created: str, description: str) -> dict:
    return {
        "type": "relationship", "spec_version": "2.1", "id": sid("relationship", f"{source}:{kind}:{target}"), "created": created,
        "modified": created, "created_by_ref": producer["id"], "relationship_type": kind, "source_ref": source, "target_ref": target,
        "description": description,
    }
