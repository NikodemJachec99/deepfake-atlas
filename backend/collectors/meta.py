"""Meta Ad Library API (Graph API, `ads_archive`).

W UE zwraca wszystkie reklamy, także komercyjne. Wymaga tokenu po weryfikacji tożsamości
(META_AD_LIBRARY_TOKEN). API nie podaje adresu docelowego ani plików kreacji: zostaje
`ad_snapshot_url`, który trzeba wyrenderować. Scraping webowej biblioteki łamie regulamin Mety,
więc tego tutaj nie ma.

Ten konektor nie był uruchomiony na żywym tokenie. Pola są zgodne z dokumentacją:
https://developers.facebook.com/docs/graph-api/reference/ads_archive/
"""

from datetime import UTC, datetime

import httpx
from django.conf import settings

from ads.models import Source
from ads.services import upsert_ad, upsert_advertiser

FIELDS = [
    "id", "page_id", "page_name", "ad_creation_time", "ad_delivery_start_time", "ad_delivery_stop_time",
    "ad_creative_bodies", "ad_creative_link_titles", "ad_creative_link_descriptions", "ad_creative_link_captions",
    "ad_snapshot_url", "languages", "publisher_platforms", "beneficiary_payers", "eu_total_reach",
    "target_ages", "target_gender", "target_locations",
]


def fetch(search_terms: str, country: str = "PL", limit: int = 500, client: httpx.Client | None = None) -> list[dict]:
    if not settings.META_AD_LIBRARY_TOKEN:
        raise RuntimeError("Brak META_AD_LIBRARY_TOKEN. Token wydaje Meta po weryfikacji tożsamości.")
    client = client or httpx.Client(timeout=60)
    url = f"https://graph.facebook.com/{settings.META_GRAPH_VERSION}/ads_archive"
    params = {
        "access_token": settings.META_AD_LIBRARY_TOKEN,
        "search_terms": search_terms[:100],
        "ad_reached_countries": f'["{country}"]',
        "ad_type": "ALL",
        "ad_active_status": "ALL",
        "fields": ",".join(FIELDS),
        "limit": min(limit, 100),
    }
    rows: list[dict] = []
    while url and len(rows) < limit:
        response = client.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        rows.extend(data.get("data", []))
        url, params = data.get("paging", {}).get("next"), None
    return rows[:limit]


def _first(values) -> str:
    return (values or [""])[0] or ""


def _payer(row: dict) -> str:
    payers = row.get("beneficiary_payers") or []
    return (payers[0].get("payer") or "") if payers else ""


def save(rows: list[dict]) -> dict:
    created, ads = 0, []
    for row in rows:
        advertiser = upsert_advertiser(Source.META, str(row.get("page_id") or ""), name=row.get("page_name") or "", payer=_payer(row))
        start = row.get("ad_delivery_start_time")
        ad, is_new = upsert_ad(
            Source.META,
            str(row["id"]),
            advertiser=advertiser,
            raw=row,
            title=_first(row.get("ad_creative_link_titles")),
            text="\n".join(filter(None, [_first(row.get("ad_creative_bodies")), _first(row.get("ad_creative_link_descriptions"))])),
            display_url=_first(row.get("ad_creative_link_captions")),
            first_seen=datetime.fromisoformat(start).replace(tzinfo=UTC) if start else None,
        )
        created += is_new
        ads.append(ad)
    return {"fetched": len(rows), "created": created, "ads": ads}


def collect(search_terms: str, country: str = "PL", limit: int = 500) -> dict:
    return save(fetch(search_terms, country, limit))
