"""Microsoft Ad Library API. Działa bez autoryzacji i jako jedyna biblioteka zwraca adres docelowy.

Dokumentacja: https://learn.microsoft.com/en-us/advertising/guides/ad-library-api
Bez konta limity są ostre (HTTP 429), więc pobieramy małymi stronami i czekamy, gdy API o to prosi.
"""

import time

import httpx

from ads.models import Source
from ads.services import upsert_ad, upsert_advertiser

BASE = "https://adlibrary.api.bingads.microsoft.com/api/v1"
COUNTRY_PL = 151
PAGE = 20
MAX_WAIT = 90


def _get(client: httpx.Client, params: dict, retries: int = 3) -> httpx.Response:
    for attempt in range(retries + 1):
        response = client.get(f"{BASE}/Ads", params=params)
        if response.status_code != 429 or attempt == retries:
            return response
        wait = response.headers.get("retry-after", "")
        time.sleep(min(MAX_WAIT, int(wait) if wait.isdigit() else 15 * (attempt + 1)))
    return response


def fetch(query: str, country: int = COUNTRY_PL, limit: int = 200, client: httpx.Client | None = None) -> list[dict]:
    client = client or httpx.Client(timeout=30)
    rows: list[dict] = []
    while len(rows) < limit:
        response = _get(client, {"searchText": query, "countryCodes": country, "top": min(PAGE, limit - len(rows)), "skip": len(rows)})
        if response.status_code == 429 and rows:
            break  # oddajemy to, co już mamy; następny skan dobierze resztę
        response.raise_for_status()
        page = response.json().get("value", [])
        if not page:
            break
        rows.extend(page)
    return rows


def save(rows: list[dict]) -> dict:
    created, ads = 0, []
    for row in rows:
        advertiser = upsert_advertiser(Source.MICROSOFT, str(row.get("AdvertiserId") or ""), name=row.get("AdvertiserName") or "")
        ad, is_new = upsert_ad(
            Source.MICROSOFT,
            str(row["AdId"]),
            advertiser=advertiser,
            raw=row,
            title=row.get("Title") or "",
            text=row.get("Description") or "",
            landing_url=row.get("DestinationUrl") or "",
            display_url=row.get("DisplayUrl") or "",
        )
        created += is_new
        ads.append(ad)
    return {"fetched": len(rows), "created": created, "ads": ads}


def collect(query: str, country: int = COUNTRY_PL, limit: int = 200) -> dict:
    return save(fetch(query, country, limit))
