"""Oś obserwacji kampanii i operatora. Daty, domeny i identyfikatory zmyślone."""

from datetime import UTC, datetime

import pytest
from rest_framework.test import APIClient

from ads.models import Ad, AdSnapshot
from enrichment.models import DomainRecord, WarningDomain
from evidence import services as markers
from extractors import Observation
from similarity import timeline
from similarity.models import Campaign, CampaignMembership, Edge, Operator, OperatorMembership

pytestmark = pytest.mark.django_db


def _at(day: int, hour: int = 12) -> datetime:
    return datetime(2026, 10, day, hour, tzinfo=UTC)


def _cert(day: int, domains: list[str] | None = None) -> dict:
    detail = {"from": "crt.sh", "not_before": f"2026-10-{day:02d}T10:00:00", "issuer": "C=US, O=Let's Encrypt, CN=YE1"}
    if domains:
        detail["domains"] = domains
    return detail


@pytest.fixture
def group():
    # reklama z biblioteki: data startu podaje biblioteka, z dokładnością do dnia
    a = Ad.objects.create(source="meta", external_id="1", first_seen=_at(5), last_seen=_at(9))
    AdSnapshot.objects.create(ad=a, observed_at=_at(6), active=False, content_hash="x")
    # dwa przechwycenia z tą samą chwilą obserwacji; last_seen i migawka to tylko data importu
    b = Ad.objects.create(source="capture", external_id="p/1", first_seen=_at(7), last_seen=_at(21))
    AdSnapshot.objects.create(ad=b, observed_at=_at(21), content_hash="y")
    c = Ad.objects.create(source="capture", external_id="p/2", first_seen=_at(7))
    # przechwycenie bez daty w paczce: pierwsze wystąpienie to chwila importu
    u = Ad.objects.create(source="capture", external_id="p/3")
    u.first_seen = u.created_at
    u.save(update_fields=["first_seen"])

    markers.attach(a, [Observation("domain", "zysk-a.example"), Observation("funnel_id", "f-1")])
    markers.attach(b, [Observation("domain", "inwest-b.example"), Observation("funnel_id", "f-1")])
    markers.attach(c, [Observation("domain", "inwest-b.example")])
    markers.attach(u, [Observation("funnel_id", "f-1"), Observation("telegram", "tylko_bez_daty")])
    # odnowienia certyfikatu samej domeny A to jedna seria, wspólny certyfikat A i B to osobne zdarzenie
    markers.attach(a, [Observation("tls_serial", "r1", _cert(2)), Observation("tls_serial", "r2", _cert(4))])
    markers.attach(a, [Observation("tls_serial", "065d31", _cert(3, ["inwest-b.example"]))])
    markers.attach(b, [Observation("tls_serial", "065d31", _cert(3, ["zysk-a.example"]))])
    markers.attach(b, [Observation("tls_serial", "aa11", {"not_before": ""})])  # numer z paczki, bez daty
    # numer z dns_ssl.json z datą w formacie OpenSSL
    markers.attach(c, [Observation("tls_serial", "bb22", {"not_before": "Oct  6 18:53:02 2026 GMT"})])

    DomainRecord.objects.create(domain="zysk-a.example", registered_at=_at(1), registrar="Rejestrator Sp. z o.o.")
    DomainRecord.objects.create(domain="inwest-b.example")  # bez daty rejestracji
    WarningDomain.objects.create(domain="inwest-b.example", added_at=_at(8), removed_at=_at(20))

    ab = Edge.objects.create(ad_a=a, ad_b=b, relation="same_campaign", probability=0.99, bits=20)
    Edge.objects.create(ad_a=a, ad_b=u, relation="same_campaign", probability=0.97, bits=18)
    Edge.objects.create(ad_a=a, ad_b=c, relation="same_campaign", probability=0.95, bits=17, verdict="rejected")
    bc = Edge.objects.create(ad_a=b, ad_b=c, relation="same_operator", probability=0.93, bits=16)

    campaign, operator = Campaign.objects.create(), Operator.objects.create()
    for ad in (a, b, c, u):
        CampaignMembership.objects.create(ad=ad, campaign=campaign)
        OperatorMembership.objects.create(ad=ad, operator=operator)
    outsider = Ad.objects.create(first_seen=_at(2))
    markers.attach(outsider, [Observation("funnel_id", "f-1")])
    return {"a": a.pk, "b": b.pk, "c": c.pk, "u": u.pk, "ab": ab.pk, "bc": bc.pk, "outsider": outsider.pk,
            "campaign": campaign, "operator": operator}


def test_campaign_timeline_order_and_content(group):
    body = APIClient().get(f"/api/campaigns/{group['campaign'].pk}/timeline").json()
    assert body["group"] == group["campaign"].key
    a, b, c = group["a"], group["b"], group["c"]
    assert [(e["type"], e["ads"], e["value"]) for e in body["events"]] == [
        ("domain_registered", [a], "zysk-a.example"),
        ("cert_issued", [a], "r1"),
        ("cert_issued", [a, b], "065d31"),
        ("ad_first_seen", [a], ""),
        ("trace_first_observed", [a], "f-1"),
        ("trace_first_observed", [a], "zysk-a.example"),
        ("snapshot", [a], ""),
        ("cert_issued", [c], "bb22"),
        ("ad_first_seen", [b], ""),
        ("ad_first_seen", [c], ""),
        ("trace_first_observed", [b, c], "inwest-b.example"),
        ("link_observable", [b], "1"),
        ("cert_pl_added", [b, c], "inwest-b.example"),
        ("ad_last_seen", [a], ""),
        ("cert_pl_removed", [b, c], "inwest-b.example"),
    ]
    assert [e["at"] for e in body["events"]] == sorted(e["at"] for e in body["events"])
    assert all(e["label"] for e in body["events"])


def test_every_event_says_what_kind_of_time_it_is(group):
    events = APIClient().get(f"/api/campaigns/{group['campaign'].pk}/timeline").json()["events"]
    by = {(e["type"], e["value"], tuple(e["ads"])): e for e in events}
    a, b = group["a"], group["b"]
    assert {e["time_kind"] for e in events} == {"observed", "reported"}
    registered = by[("domain_registered", "zysk-a.example", (a,))]
    assert (registered["time_kind"], registered["source"], registered["precision"]) == ("reported", "rdap", "exact")
    meta_start = by[("ad_first_seen", "", (a,))]
    assert (meta_start["time_kind"], meta_start["source"], meta_start["precision"]) == ("reported", "meta", "day")
    captured = by[("ad_first_seen", "", (b,))]
    assert (captured["time_kind"], captured["source"]) == ("observed", "capture")
    link = by[("link_observable", "1", (b,))]
    # powiązanie widać dopiero od obserwacji późniejszej z dwóch reklam
    assert link["at"] == _at(7).isoformat() and link["source"] == "capture"
    assert link["detail"] == {"count": 1, "relations": {"same_campaign": 1}, "partners": [a], "edges": [group["ab"]], "max_probability": 0.99}
    cert = by[("cert_issued", "065d31", (a, b))]
    assert (cert["time_kind"], cert["source"]) == ("reported", "crt.sh")
    captured_cert = by[("cert_issued", "bb22", (group["c"],))]
    assert (captured_cert["time_kind"], captured_cert["source"]) == ("reported", "capture")
    assert captured_cert["at"] == "2026-10-06T18:53:02+00:00"


def test_duplicates_are_merged_and_ties_stay_ambiguous(group):
    events = APIClient().get(f"/api/campaigns/{group['campaign'].pk}/timeline").json()["events"]
    by = {(e["type"], e["value"]): e for e in events}
    # odnowienia: jedna seria z liczbą wystawień
    series = by[("cert_issued", "r1")]
    assert series["detail"]["count"] == 2 and series["detail"]["last_at"].startswith("2026-10-04")
    # wspólny certyfikat dwóch reklam to jedno zdarzenie z oboma reklamami
    assert sum(1 for e in events if e["value"] == "065d31") == 1
    assert by[("cert_issued", "065d31")]["detail"]["domains"] == ["inwest-b.example", "zysk-a.example"]
    # ślad z dwóch reklam o tej samej chwili: obie podane, bez wybierania pierwszej
    tied = by[("trace_first_observed", "inwest-b.example")]
    assert tied["ads"] == [group["b"], group["c"]] and tied["detail"]["tied"] is True
    # ślad widziany też w reklamie bez daty i poza grupą: liczymy tylko grupę
    funnel = by[("trace_first_observed", "f-1")]
    assert funnel["detail"] == {"kind": "funnel_id", "kind_label": funnel["detail"]["kind_label"], "family": "track", "in_group": 3, "undated_ads": 1}
    assert group["outsider"] not in {ad for e in events for ad in e["ads"]}


def test_missing_dates_are_counted_not_guessed(group):
    body = APIClient().get(f"/api/campaigns/{group['campaign'].pk}/timeline").json()
    assert body["undated"] == {"ads": [group["u"]], "traces": 1, "links": 1, "certificates": 1}
    assert group["u"] not in {ad for e in body["events"] for ad in e["ads"]}
    assert not any(e["type"] == "domain_registered" and e["value"] == "inwest-b.example" for e in body["events"])
    # odrzucone powiązanie nie trafia na oś
    assert sum(1 for e in body["events"] if e["type"] == "link_observable") == 1


def test_operator_timeline_adds_operator_links(group):
    body = APIClient().get(f"/api/operators/{group['operator'].pk}/timeline").json()
    assert body["group"] == group["operator"].key
    links = [(e["ads"], e["detail"]["partners"], e["detail"]["relations"], e["detail"].get("tied", False))
             for e in body["events"] if e["type"] == "link_observable"]
    # b i c mają tę samą chwilę obserwacji: para trafia do reklamy o wyższym numerze, z oznaczonym remisem
    assert links == [([group["b"]], [group["a"]], {"same_campaign": 1}, False), ([group["c"]], [group["b"]], {"same_operator": 1}, True)]


def test_build_is_deterministic(group):
    ids = [group["u"], group["c"], group["b"], group["a"]]
    assert timeline.build(ids, ["same_campaign"]) == timeline.build(list(reversed(ids)), ["same_campaign"])


def test_empty_group_and_missing_group():
    assert timeline.build([], ["same_campaign"]) == {"events": [], "undated": {"ads": [], "traces": 0, "links": 0, "certificates": 0}}
    assert APIClient().get("/api/campaigns/999999/timeline").status_code == 404
    assert APIClient().get("/api/operators/999999/timeline").status_code == 404


def test_links_are_grouped_per_joining_ad_with_limit(monkeypatch):
    from similarity import timeline as tl

    monkeypatch.setattr(tl, "LINK_LIST_LIMIT", 3)
    ads = [Ad.objects.create(source="microsoft", external_id=f"m/{i}", first_seen=_at(1 + i)) for i in range(6)]
    for i, x in enumerate(ads):
        for y in ads[:i]:
            Edge.objects.create(ad_a=y, ad_b=x, relation="same_campaign", probability=0.99, bits=20)
    events = [e for e in tl.build([x.pk for x in ads], ["same_campaign"])["events"] if e["type"] == "link_observable"]
    assert [(e["ads"], e["detail"]["count"]) for e in events] == [([ads[i].pk], i) for i in range(1, 6)]  # 5 zdarzeń zamiast 15
    last = events[-1]["detail"]
    assert last["truncated"] is True and len(last["partners"]) == 3 and len(last["edges"]) == 3
