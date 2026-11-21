#!/usr/bin/env python3
"""Pomiar odporności na brak materiału: te same paczki w wariantach bez HAR, bez zapisu strony i bez zrzutów.

Uruchamiać na OSOBNYM stosie (czyści korpus): python scripts/odpornosc.py --paczki data/raw/nask data/raw/nask-backup
Warianty powstają w data/raw/odpornosc/ (poza gitem), wynik w data/raw/odpornosc/wynik.json i na ekranie.
"""

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
ROOT = Path(__file__).resolve().parent.parent
DUMP = """
import json
from ads.models import Ad
from similarity.models import Edge
def key(ad): return f"{ad.labels.get('bundle')}/{ad.external_id.split('/', 1)[1]}"
pairs = {}
for e in Edge.objects.select_related("ad_a", "ad_b").filter(ad_a__source="capture", ad_b__source="capture"):
    a, b = sorted((key(e.ad_a), key(e.ad_b)))
    pairs[f"{a}|{b}"] = e.relation
print("WYNIK" + json.dumps({"ads": Ad.objects.filter(source="capture").count(), "pairs": pairs}))
"""


def in_assets(path: Path) -> bool:
    return any(part.endswith("_files") for part in path.parts)


def drop(variant: str, path: Path) -> bool:
    name = path.name.lower()
    if variant == "bez_har":
        return name.endswith(".har")
    if variant == "bez_zapisu_strony":
        return (name.endswith((".html", ".htm")) and not in_assets(path)) or (path.is_dir() and name.endswith("_files"))
    if variant == "bez_zrzutow":
        return path.suffix.lower() in IMAGE_EXT and not in_assets(path)
    return False


def build(variant: str, sources: list[Path], target: Path) -> int:
    removed = 0
    for source in sources:
        dest = target / variant / source.name
        shutil.rmtree(dest, ignore_errors=True)
        shutil.copytree(source, dest)
        for path in sorted(dest.rglob("*"), key=lambda p: -len(p.parts)):
            if path.exists() and drop(variant, path):
                shutil.rmtree(path) if path.is_dir() else path.unlink()
                removed += 1
    return removed


def compose(*args: str, capture: bool = False) -> str:
    result = subprocess.run(["docker", "compose", "exec", "-T", "backend", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        sys.exit(f"STOP: {' '.join(args)}\n{result.stderr[-1500:]}")
    return result.stdout if capture else ""


def run_variant(variant: str, sources: list[Path]) -> dict:
    compose("python", "manage.py", "reset_corpus", "--yes")
    for source in sources:
        compose("python", "manage.py", "import_bundle", f"/data/raw/odpornosc/{variant}/{source.name}", "--name", source.name)
    out = compose("python", "manage.py", "shell", "-c", DUMP, capture=True)
    return json.loads(out.split("WYNIK", 1)[1])


def compare(full: dict, other: dict) -> dict:
    same = ("same_campaign", "same_operator")
    base = {p: r for p, r in full["pairs"].items() if r in same}
    kept = sum(1 for p in base if other["pairs"].get(p) in same)
    similar = sum(1 for p in base if other["pairs"].get(p) == "similar")
    gone = sum(1 for p in base if p not in other["pairs"])
    new = sorted(p for p, r in other["pairs"].items() if r in same and full["pairs"].get(p) not in same)
    return {"base": len(base), "kept": kept, "similar": similar, "gone": gone, "new_same_source": new, "ads": other["ads"]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--paczki", nargs="+", required=True, help="katalogi paczek pod data/raw, np. data/raw/nask")
    parser.add_argument("--warianty", nargs="+", default=["pelny", "bez_har", "bez_zapisu_strony", "bez_zrzutow"])
    args = parser.parse_args()
    sources = [(ROOT / p).resolve() for p in args.paczki]
    target = ROOT / "data" / "raw" / "odpornosc"
    results = {}
    for variant in args.warianty:
        removed = build(variant, sources, target)
        print(f"== {variant}: usunięto {removed} plików lub katalogów, import...", flush=True)
        results[variant] = run_variant(variant, sources)
    full = results["pelny"]
    report = {v: compare(full, r) for v, r in results.items() if v != "pelny"}
    (target / "wynik.json").write_text(json.dumps({"pelny": full, "porownanie": report}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"pełny: {full['ads']} stron, połączeń wspólnego źródła między stronami: {sum(r in ('same_campaign', 'same_operator') for r in full['pairs'].values())}")
    for variant, r in report.items():
        print(f"{variant}: stron {r['ads']}, z {r['base']} połączeń zostało {r['kept']}, do podobieństwa {r['similar']}, zniknęło {r['gone']}, nowe wspólne źródło: {len(r['new_same_source'])} {r['new_same_source'][:5]}")


if __name__ == "__main__":
    main()
