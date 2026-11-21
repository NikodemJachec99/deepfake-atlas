"""Prezentacja PDF ze slajdów (scripts/prezentacja/slajdy.html), liczb z API i zrzutów interfejsu.

    uv run --no-project --with playwright python scripts/prezentacja/pdf.py --api http://localhost:8010 \
        --shots data/zgloszenie/zrzuty --out data/zgloszenie/prezentacja.pdf

Liczby na slajdzie z wynikiem bierzemy z API z filtrem źródła `capture` (same paczki organizatora), więc
zgadzają się ze stanem bazy w chwili generowania. PDF zawiera dane organizatora: tylko poza gitem.
"""

import argparse
import json
import urllib.request
from datetime import datetime
from pathlib import Path
from string import Template

from playwright.sync_api import sync_playwright

MAX_BYTES = 10 * 1024 * 1024
HERE = Path(__file__).resolve().parent


def api(base: str, path: str):
    with urllib.request.urlopen(f"{base}{path}", timeout=30) as response:
        return json.load(response)


def numbers(base: str) -> dict:
    operators = api(base, "/api/operators?source=capture")["results"]
    campaigns = api(base, "/api/campaigns?source=capture")["results"]
    ads = api(base, "/api/ads?source=capture&page=1")
    pages = ads["count"]
    rows = list(ads["results"])
    page = 2
    while len(rows) < pages:
        rows += api(base, f"/api/ads?source=capture&page={page}")["results"]
        page += 1
    capture_ids = {a["id"] for a in rows}
    relations: dict[str, int] = {}
    seen = set()
    for ad_id in capture_ids:
        for edge in api(base, f"/api/ads/{ad_id}/edges"):
            if edge["id"] in seen or not {edge["ad_a"], edge["ad_b"]} <= capture_ids:
                continue
            seen.add(edge["id"])
            relations[edge["relation"]] = relations.get(edge["relation"], 0) + 1
    by_key = {g["key"]: g for g in operators}
    return {
        "pages": pages,
        "cases": len({a.get("case") for a in rows if a.get("case")}),
        "campaigns": len(campaigns),
        "operators": len(operators),
        "same_campaign": relations.get("same_campaign", 0),
        "same_operator": relations.get("same_operator", 0),
        "similar": relations.get("similar", 0),
        "cert": sum(1 for a in rows if (a.get("labels") or {}).get("cert_pl")),
        "op_a_pages": by_key.get("O-0001", {}).get("size", 0),
        "op_b_pages": by_key.get("O-0002", {}).get("size", 0),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://localhost:8010")
    parser.add_argument("--shots", default="data/zgloszenie/zrzuty")
    parser.add_argument("--out", default="data/zgloszenie/prezentacja.pdf")
    args = parser.parse_args()
    values = numbers(args.api)
    print("liczby z API:", values)
    html = Template((HERE / "slajdy.html").read_text(encoding="utf-8")).substitute(
        **values, shots=Path(args.shots).resolve().as_uri(), generated=datetime.now().strftime("%d.%m.%Y %H:%M"),
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    source = out.with_suffix(".html")
    source.write_text(html, encoding="utf-8")
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        page.goto(source.resolve().as_uri(), wait_until="load")
        page.pdf(path=str(out), width="1280px", height="720px", print_background=True)
        browser.close()
    size = out.stat().st_size
    print(f"{out}: {size / 1024 / 1024:.2f} MB")
    if size > MAX_BYTES:
        raise SystemExit("PDF ponad 10 MB, limit zgłoszenia")


if __name__ == "__main__":
    main()
