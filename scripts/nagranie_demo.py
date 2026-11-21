#!/usr/bin/env python3
"""Nagranie demo do 2 minut według scenariusza z docs/prezentacja.md.

Wymaga stosu z korpusem przygotowanym jak w scenariuszu (bez spraw p3, p4 i p11) i pliku p3.zip.
Uruchamiać na osobnym stosie, bo wrzucenie p3 zmienia korpus:

    uv run --no-project --with playwright python scripts/nagranie_demo.py \
        --ui http://localhost:3100 --api http://localhost:8100 --zip data/raw/p3.zip --out data/zgloszenie

Wynik: data/zgloszenie/demo.webm (i demo.mp4, jeśli jest ffmpeg). Zawiera dane organizatora, więc jest poza gitem.
"""

import argparse
import json
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

CAPTION_JS = """(text) => {
  let el = document.getElementById('demo-caption');
  if (!el) {
    el = document.createElement('div');
    el.id = 'demo-caption';
    el.style.cssText = 'position:fixed;left:50%;bottom:28px;transform:translateX(-50%);max-width:88%;z-index:99999;'
      + 'background:rgba(10,14,24,.92);color:#fff;font:600 19px/1.35 system-ui,sans-serif;padding:12px 20px;'
      + 'border-radius:10px;box-shadow:0 6px 24px rgba(0,0,0,.4);text-align:center;pointer-events:none';
    document.body.appendChild(el);
  }
  el.textContent = text;
}"""


def caption(page, text: str, hold: float = 0.0) -> None:
    page.evaluate(CAPTION_JS, text)
    if hold:
        page.wait_for_timeout(int(hold * 1000))


def api(base: str, path: str):
    with urllib.request.urlopen(base + path, timeout=30) as response:
        return json.load(response)


def smooth_scroll(page, pixels: int, steps: int = 10) -> None:
    for _ in range(steps):
        page.mouse.wheel(0, pixels / steps)
        page.wait_for_timeout(60)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ui", default="http://localhost:3100")
    parser.add_argument("--api", default="http://localhost:8100")
    parser.add_argument("--zip", default="data/raw/p3.zip")
    parser.add_argument("--out", default="data/zgloszenie")
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    started = time.time()

    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={"width": 1440, "height": 900}, record_video_dir=str(out / "surowe"), record_video_size={"width": 1440, "height": 900})
        page = context.new_page()

        # 1. Discovery i nowa sprawa
        page.goto(args.ui + "/")
        page.wait_for_load_state("networkidle")
        caption(page, "SCAM DNA. Wrzucamy sprawę, której system jeszcze nie widział: nowa domena, inny artykuł, inna osoba.", 4)
        page.set_input_files("input[type=file]", args.zip)
        caption(page, "Analiza bez sieci: strona z przechwycenia, ruch HAR, zrzut reklamy. Sześć etapów na żywo.")
        page.get_by_text("Nowa kampania znanego operatora").first.wait_for(timeout=180_000)
        page.wait_for_timeout(1500)
        caption(page, "Wynik: nowa kampania znanego operatora. Łączą ją identyfikator strony w panelu lejka i piksel Meta, po 18 bitów.", 6)

        # 2. Graf i panel dowodów
        smooth_scroll(page, 700)
        caption(page, "Graf dorysowuje powiązania z reklamami tego samego operatora.", 4)
        # Pozycja listy powiązań ("#24 ↔ #27 · Ten sam operator"), nie legenda grafu.
        page.locator("text=/↔.*Ten sam operator/").first.click()
        page.wait_for_timeout(1500)
        page.get_by_text("Dowody według wkładu").first.scroll_into_view_if_needed()
        caption(page, "Każde połączenie ma listę dowodów: wkład w bitach i w ilu niezależnych źródłach występuje ślad.", 6)

        # 3. Laboratorium dowodów
        lab = page.get_by_text("Laboratorium dowodów").first
        if lab.count():
            lab.click()
            page.wait_for_timeout(800)
            weakest = page.get_by_text("Sprawdź najsłabszy punkt").first
            weakest.scroll_into_view_if_needed()
            weakest.click()
            page.wait_for_timeout(2500)
            caption(page, "Laboratorium: na czym trzyma się hipoteza. Symulacja niczego nie zapisuje.", 6)

        # 4. Karta operatora
        operator = next(g for g in api(args.api, "/api/operators")["results"] if g["key"] == "O-0001")
        page.goto(f"{args.ui}/operators/{operator['id']}")
        page.wait_for_load_state("networkidle")
        caption(page, "Karta operatora: kampanie, reklamy na różnych domenach i ślady, które je spinają.", 6)

        # 5. Dwie twarze jednego linku (sprawa 61)
        ads = api(args.api, "/api/ads?case=61")["results"]
        offer = next((a for a in ads if "strona-2" in a.get("external_id", "")), None)
        if offer:
            page.goto(f"{args.ui}/ads/{offer['id']}")
            page.wait_for_load_state("networkidle")
            twin = page.get_by_text("Dwie twarze jednego linku").first
            twin.scroll_into_view_if_needed()
            twin.click()
            page.wait_for_timeout(2000)
            caption(page, "Sprawa 61: ten sam adres, co do znaku, w 161 s dał dwie różne strony. System podaje możliwe wyjaśnienia, nie przesądza.", 7)

        caption(page, "Nowa domena, inny artykuł, inna osoba. System wie, kto za nią stoi, i pokazuje dlaczego.", 5)
        video = page.video
        context.close()
        browser.close()
        raw = Path(video.path())

    target = out / "demo.webm"
    shutil.move(str(raw), target)
    shutil.rmtree(out / "surowe", ignore_errors=True)
    print(f"nagranie: {target} ({target.stat().st_size // 1024} KB, {time.time() - started:.0f} s nagrywania)")
    try:
        import imageio_ffmpeg

        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        mp4 = out / "demo.mp4"
        subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-i", str(target), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "23", str(mp4)], check=True)
        print(f"mp4: {mp4} ({mp4.stat().st_size // 1024} KB)")
    except ImportError:
        print("bez ffmpeg: zostaje tylko webm (uv run --with imageio-ffmpeg doda mp4)")


if __name__ == "__main__":
    main()
