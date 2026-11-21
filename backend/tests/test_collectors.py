"""Konektory na nagranych odpowiedziach. Formaty pochodzą z żywych API (sprawdzone 2026-11-21)."""

import httpx
import pytest

from ads.models import Ad, Advertiser
from collectors import cert_pl, meta, microsoft
from collectors.registry import run
from enrichment.models import WarningDomain

pytestmark = pytest.mark.django_db

CERT_CURRENT = [
    {"RegisterPositionId": 730518, "DomainAddress": "Delorer.com", "InsertDate": "2026-11-21T10:41:40+00:00", "DeleteDate": None},
    {"RegisterPositionId": 730000, "DomainAddress": "stara.example", "InsertDate": "2026-06-01T08:00:00+00:00", "DeleteDate": "2026-09-01T08:00:00+00:00"},
]
CERT_ACTIONS = "\n".join(
    [
        '{"RegisterPositionId": 501303, "DomainAddress": "phasetinti.world", "ActionTime": "2026-01-01T01:58:35+00:00", "ActionType": "block"}',
        '{"RegisterPositionId": 501304, "DomainAddress": "pervacombi.world", "ActionTime": "2026-01-01T01:58:38+00:00", "ActionType": "block"}',
        '{"RegisterPositionId": 501303, "DomainAddress": "phasetinti.world", "ActionTime": "2026-07-01T00:00:00+00:00", "ActionType": "unblock"}',
        "",
    ]
)
MS_PAGE = {
    "@odata.count": 2,
    "value": [
        {"AdId": 73323991195987, "AdvertiserName": "Firma A Sp. z o.o.", "AdvertiserId": 138327582, "Title": "Inwestycje w złoto",
         "Description": "Opis", "DisplayUrl": "firma-a.example/zloto", "DestinationUrl": "https://firma-a.example/", "AssetJson": ""},
        {"AdId": 76828563358307, "AdvertiserName": "Firma B", "AdvertiserId": 151138181, "Title": "Apartamenty",
         "Description": "", "DisplayUrl": "firma-b.example", "DestinationUrl": "http://firma-b.example/", "AssetJson": ""},
    ],
}


def client_for(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_cert_current_list_is_upserted():
    client = client_for(lambda request: httpx.Response(200, json=CERT_CURRENT))
    assert cert_pl.sync_current(client) == 2
    assert cert_pl.sync_current(client) == 2  # drugi skan niczego nie dubluje
    assert WarningDomain.objects.count() == 2
    fresh = WarningDomain.objects.get(domain="delorer.com")
    assert fresh.register_position == 730518 and fresh.removed_at is None
    assert WarningDomain.objects.get(domain="stara.example").removed_at is not None


def test_cert_history_keeps_both_dates():
    client = client_for(lambda request: httpx.Response(200, text=CERT_ACTIONS))
    assert cert_pl.sync_history(2026, client) == {"year": 2026, "blocked": 2, "unblocked": 1}
    removed = WarningDomain.objects.get(domain="phasetinti.world")
    assert removed.added_at.month == 1 and removed.removed_at.month == 7
    assert WarningDomain.objects.get(domain="pervacombi.world").removed_at is None


def test_microsoft_ads_are_saved_with_landing_url_and_snapshot():
    def handler(request):
        skip = int(request.url.params["skip"])
        return httpx.Response(200, json=MS_PAGE if skip == 0 else {"value": []})

    result = microsoft.save(microsoft.fetch("inwestycje", limit=40, client=client_for(handler)))
    assert result["fetched"] == 2 and result["created"] == 2
    ad = Ad.objects.get(external_id="73323991195987")
    assert ad.source == "microsoft" and ad.landing_url == "https://firma-a.example/"
    assert ad.advertiser.name == "Firma A Sp. z o.o."
    assert ad.snapshots.count() == 1

    # Ten sam skan drugi raz: reklama zostaje jedna, migawka nie przybywa, bo treść się nie zmieniła.
    again = microsoft.save(microsoft.fetch("inwestycje", limit=40, client=client_for(handler)))
    assert again["created"] == 0
    assert Ad.objects.count() == 2 and ad.snapshots.count() == 1
    assert Advertiser.objects.count() == 2


def test_microsoft_rate_limit_returns_partial_result(monkeypatch):
    monkeypatch.setattr(microsoft.time, "sleep", lambda seconds: None)
    calls = []

    def handler(request):
        calls.append(request.url.params["skip"])
        if request.url.params["skip"] == "0":
            return httpx.Response(200, json=MS_PAGE)
        return httpx.Response(429, text="Too many requests")

    rows = microsoft.fetch("inwestycje", limit=100, client=client_for(handler))
    assert len(rows) == 2
    assert calls.count("2") == 4  # pierwsza próba i trzy ponowienia


def test_meta_requires_token_and_maps_fields(settings):
    settings.META_AD_LIBRARY_TOKEN = ""
    with pytest.raises(RuntimeError):
        meta.fetch("inwestycje")

    row = {
        "id": "1234567890", "page_id": "999", "page_name": "Strona Testowa",
        "ad_creative_bodies": ["Zarabiaj z nami"], "ad_creative_link_titles": ["Platforma"],
        "ad_creative_link_captions": ["zysk.example"], "ad_snapshot_url": "https://www.facebook.com/ads/archive/render_ad/?id=1234567890",
        "beneficiary_payers": [{"payer": "Płatnik X", "beneficiary": "Beneficjent Y"}],
        "ad_delivery_start_time": "2026-11-01",
    }
    ad = meta.save([row])["ads"][0]
    assert ad.source == "meta" and ad.title == "Platforma" and ad.text == "Zarabiaj z nami"
    assert ad.advertiser.payer == "Płatnik X"
    assert ad.landing_url == ""  # API Mety nie podaje adresu docelowego
    assert ad.raw["ad_snapshot_url"].endswith("1234567890")


def test_registry_queues_one_analysis_per_new_ad(monkeypatch):
    monkeypatch.setattr(microsoft, "fetch", lambda query, country=151, limit=200: MS_PAGE["value"])
    first = run("microsoft", {"query": "inwestycje"})
    assert first["fetched"] == 2 and len(first["analyses"]) == 2
    assert run("microsoft", {"query": "inwestycje"})["analyses"] == []
    with pytest.raises(KeyError):
        run("nieznany", {})
