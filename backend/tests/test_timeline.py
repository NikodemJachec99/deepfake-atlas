"""Oś czasu kampanii i operatora. Daty i domeny zmyślone."""

from datetime import UTC, datetime

import pytest
from rest_framework.test import APIClient

from ads.models import Ad, AdSnapshot
from enrichment.models import DomainRecord, WarningDomain
from evidence import services as markers
from extractors import Observation
from similarity.models import Campaign, CampaignMembership, Operator, OperatorMembership

pytestmark = pytest.mark.django_db


def _at(day: int, hour: int = 12) -> datetime:
    return datetime(2026, 10, day, hour, tzinfo=UTC)


@pytest.fixture
def group():
    first = Ad.objects.create(source="meta", external_id="1", first_seen=_at(5), last_seen=_at(9))
    # przechwycenie z paczki: last_seen i migawka to tylko data importu
    second = Ad.objects.create(source="capture", external_id="p/1", first_seen=_at(7), last_seen=_at(21))
    AdSnapshot.objects.create(ad=second, observed_at=_at(21), content_hash="y")
    # przechwycenie bez daty w paczce: pierwsze wystąpienie to chwila importu
    undated = Ad.objects.create(source="capture", external_id="p/2")
    undated.first_seen = undated.created_at
    undated.save(update_fields=["first_seen"])
    markers.attach(first, [Observation("domain", "zysk-a.example")])
    markers.attach(second, [Observation("domain", "inwest-b.example")])
    shared = {"from": "crt.sh", "not_before": "2026-10-03T18:53:02", "issuer": "C=US, O=Let's Encrypt, CN=YE1", "domains": ["inwest-b.example"]}
    markers.attach(first, [Observation("tls_serial", "065d31", shared)])
    markers.attach(second, [Observation("tls_serial", "065d31", {**shared, "domains": ["zysk-a.example"]})])
    # numer z paczki nie ma daty wystawienia, więc nie trafia na oś
    markers.attach(second, [Observation("tls_serial", "aa11", {"not_before": ""})])
    DomainRecord.objects.create(domain="zysk-a.example", registered_at=_at(1), registrar="Rejestrator Sp. z o.o.")
    DomainRecord.objects.create(domain="inwest-b.example")  # bez daty rejestracji
    WarningDomain.objects.create(domain="inwest-b.example", added_at=_at(8), removed_at=_at(20))
    AdSnapshot.objects.create(ad=first, observed_at=_at(6), active=False, content_hash="x")

    campaign, operator = Campaign.objects.create(), Operator.objects.create()
    for ad in (first, second, undated):
        CampaignMembership.objects.create(ad=ad, campaign=campaign)
        OperatorMembership.objects.create(ad=ad, operator=operator)
    outsider = Ad.objects.create(first_seen=_at(2))
    return {"first": first.pk, "second": second.pk, "undated": undated.pk, "outsider": outsider.pk, "campaign": campaign, "operator": operator}


def test_campaign_timeline_is_sorted_and_complete(group):
    body = APIClient().get(f"/api/campaigns/{group['campaign'].pk}/timeline").json()
    assert body["group"] == group["campaign"].key
    events = body["events"]
    assert [e["at"] for e in events] == sorted(e["at"] for e in events)
    a, b = group["first"], group["second"]
    assert [(e["type"], e["ads"], e["value"]) for e in events] == [
        ("domain_registered", [a], "zysk-a.example"),
        ("cert_issued", [a, b], "065d31"),
        ("ad_first_seen", [a], ""),
        ("snapshot", [a], ""),
        ("ad_first_seen", [b], ""),
        ("cert_pl_added", [b], "inwest-b.example"),
        ("ad_last_seen", [a], ""),
        ("cert_pl_removed", [b], "inwest-b.example"),
    ]
    assert events[0]["detail"] == {"registrar": "Rejestrator Sp. z o.o."}
    assert events[1]["detail"]["issuer"].endswith("CN=YE1")
    assert events[3]["detail"] == {"active": False}
    assert all(e["label"] for e in events)
    shown = {ad for e in events for ad in e["ads"]}
    assert group["outsider"] not in shown
    assert group["undated"] not in shown


def test_operator_timeline_has_the_same_shape(group):
    body = APIClient().get(f"/api/operators/{group['operator'].pk}/timeline").json()
    assert body["group"] == group["operator"].key
    assert len(body["events"]) == 8


def test_timeline_of_missing_group_is_404():
    assert APIClient().get("/api/campaigns/999999/timeline").status_code == 404
    assert APIClient().get("/api/operators/999999/timeline").status_code == 404
