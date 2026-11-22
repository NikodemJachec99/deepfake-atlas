"""Zrzuty prawdziwego interfejsu do prezentacji. Tylko odczyt: niczego nie wysyła ani nie zapisuje w bazie.

    uv run --no-project --with playwright python scripts/prezentacja/zrzuty.py --base http://localhost:3010 \
        --api http://localhost:8010 --out data/zgloszenie/zrzuty

Zrzuty zawierają dane organizatora, więc trafiają tylko do data/zgloszenie/ (poza gitem).
Identyfikatory krawędzi zmieniają się przy każdym imporcie, dlatego szukamy ich przez API po sprawach.
"""

import argparse
import json
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

WIDTH, HEIGHT = 1600, 900
CROP = 1040  # szerokość kadru: proporcje miejsca na zrzut na slajdzie
NAV = 170  # pasek nawigacji po lewej


def api(base: str, path: str):
    with urllib.request.urlopen(f"{base}{path}", timeout=30) as response:
        return json.load(response)


def ad_of_case(base: str, case: str, title: str = "") -> int:
    ads = api(base, f"/api/ads?case={case}")["results"]
    return next(a["id"] for a in ads if (a.get("title") or "").startswith(title))


def edge_between(base: str, ad: int, other: int) -> int:
    for edge in api(base, f"/api/ads/{ad}/edges"):
        if other in (edge["ad_a"], edge["ad_b"]):
            return edge["id"]
    raise SystemExit(f"brak krawędzi {ad}-{other}")


def operator_of(base: str, key: str) -> int:
    for group in api(base, "/api/operators?source=capture")["results"]:
        if group["key"] == key:
            return group["id"]
    raise SystemExit(f"brak operatora {key}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://localhost:3010")
    parser.add_argument("--api", default="http://localhost:8010")
    parser.add_argument("--out", default="data/zgloszenie/zrzuty")
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    case1, p3 = ad_of_case(args.api, "1"), ad_of_case(args.api, "p3")
    case2 = ad_of_case(args.api, "2", "«Wiem, kto strzelał»")
    case61 = ad_of_case(args.api, "61", "Trwały")
    same_campaign = edge_between(args.api, case2, case1)
    same_operator = edge_between(args.api, case2, p3)
    operator_a = operator_of(args.api, "O-0001")
    # Para operatora A do potwierdzenia zaplecza: na niej pokazujemy stanowisko oceny i podważenie przesłanki.
    queue = api(args.api, "/api/review?reason=operator_to_confirm")["results"] or api(args.api, "/api/review")["results"]
    review_edge = queue[0]["id"]

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": WIDTH, "height": HEIGHT}, device_scale_factor=1)

        def shot(name: str, url: str, *, left: int, width: int = WIDTH, clicks: list[str] = (),
                 wait_text: str | None = None, scroll: str | None = None, block: str = "nearest"):
            # Kadr bliski proporcjom miejsca na slajdzie (CROP x HEIGHT-22), bez paska nawigacji tam,
            # gdzie nie wnosi treści, i bez paska stanu: pokazuje liczby całej bazy, razem z bibliotekami.
            page.set_viewport_size({"width": width, "height": HEIGHT})
            page.goto(f"{args.base}{url}", wait_until="networkidle")
            for label in clicks:
                page.get_by_role("button", name=label).first.click()
                page.wait_for_load_state("networkidle")
            if wait_text:
                page.get_by_text(wait_text).first.wait_for(timeout=20000)
            if scroll:
                page.get_by_text(scroll).first.evaluate("(e, block) => e.scrollIntoView({block})", block)
            page.wait_for_timeout(1200)
            clip = {"x": left, "y": 0, "width": min(CROP, width - left), "height": HEIGHT - 22}
            page.screenshot(path=str(out / f"{name}.jpg"), type="jpeg", quality=82, clip=clip)
            print(name, url)

        # Krawędź: prawa część grafu i panel dowodów. Reklama: treść bez nawigacji, węższe okno.
        panel, content, narrow = WIDTH - CROP, NAV, NAV + CROP
        shot("graf-operatora", f"/investigation?operator={operator_a}", left=content)
        shot("krawedz-kampania", f"/investigation?ad={case2}&edge={same_campaign}", left=panel,
             wait_text="Identyfikator strony w panelu lejka")
        shot("krawedz-operator", f"/investigation?ad={case2}&edge={same_operator}", left=panel, wait_text="Ten sam operator")
        shot("najslabszy-punkt", f"/investigation?ad={case2}&edge={same_campaign}", left=panel,
             clicks=["Kontekst", "Laboratorium dowodów", "Sprawdź najsłabszy punkt"], wait_text="Najmniejszy zestaw", scroll="Najmniejszy zestaw")
        shot("dwie-twarze", f"/ads/{case61}", left=content, width=narrow, clicks=["Dwie twarze jednego linku"],
             wait_text="Różnice między obserwacjami", scroll="Różnice między obserwacjami")
        shot("karta-reklamy", f"/ads/{p3}?tab=traces", left=content, width=narrow, wait_text="Genom reklamy",
             scroll="Genom reklamy", block="start")
        # Stanowisko oceny i zakwestionowanie przesłanki (podgląd, bez zapisu), karta operatora z "Dlaczego razem".
        shot("do-oceny", f"/review?edge={review_edge}", left=content, wait_text="Co uzasadnia tę hipotezę")
        shot("przeslanka", f"/review?edge={review_edge}", left=content + CROP // 3, clicks=["Zakwestionuj przesłankę"], wait_text="Wpływ na cały korpus")
        shot("karta-operatora", f"/operators/{operator_a}", left=content, wait_text="Dlaczego razem")
        browser.close()


if __name__ == "__main__":
    main()
