#!/usr/bin/env python3
"""Próba jury: "Spróbuj zgubić kampanię". Trzy próby oszukania systemu przez prawdziwy upload.

Uruchamiać na OSOBNYM stosie z zaimportowanymi paczkami (wysyła warianty i zakwestionowuje przesłankę, więc zmienia korpus).
Sam Python ze standardowej biblioteki i Pillow (venv backendu: backend/.venv).

  python scripts/proba_jury.py --api http://localhost:8300 --paczki data/raw \
      --sprawy nask/1 nask-backup/p7 nask-backup/p15 nask/3 --pulapka nask/1 \
      --etykiety ../etykiety.json --wynik ../wynik.json --robocze ../robocze

Próby:
1. Przebranie: zrzut kreacji przycięty o 10% i zapisany jako JPEG q=60, 3 zdania tekstu strony podmienione, adres strony
   i domena zamienione na zmyśloną domenę .example. Dwa warianty na sprawę: bez HAR oraz z HAR z podmienioną domeną
   (te same identyfikatory, jak przy przeniesieniu lejka na nową domenę). Sprawa bez HAR dostaje tylko wariant bez HAR.
2. Pułapka: oryginalny zrzut i tekst sprawy, ale strona bez skryptów, bez HAR, bez identyfikatorów, pod obcą domeną.
   Oczekiwane: `similar`, bez `same_operator` (kopia kreacji nie jest markerem rozstrzygającym).
3. Zakwestionowanie mostu: ślad, którego wyłączenie rozdziela grupę (`/api/premises/preview`), potem `/api/premises`
   i `/api/premises/{id}/restore`.

Wynik trafia do pliku JSON (--wynik) ZANIM skrypt przeczyta plik etykiet. Etykiety to JSON
`{"grupy": {"A": ["nask/1", "nask-backup/p7"], "B": ["nask/3"]}}`: sprawy, które analityk uznał za jedną grupę. Etykiety
i paczki są poza repozytorium, a w skrypcie nie ma żadnych danych spraw.
"""

import argparse
import io
import json
import re
import sys
import time
import urllib.error
import urllib.request
import uuid
import zipfile
from html.parser import HTMLParser
from pathlib import Path

try:
    from PIL import Image
except ImportError:  # Pillow jest w venv backendu
    sys.exit("Brak Pillow: uruchom venvem backendu (backend/.venv) albo `uv run --with pillow`.")

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp"}
SOFT = ("minhash", "lsh", "band")
FOREIGN_DOMAIN = "{}.example"
# Zmyślone zdania do podmiany. Nie pochodzą z żadnej sprawy.
INVENTED = [
    "Redakcja potwierdziła, że sprawa jest badana przez odpowiednie służby od kilku dni.",
    "Według pierwszych informacji wydarzenie miało miejsce w godzinach popołudniowych.",
    "Świadkowie opisali sytuację jako nagłą i trudną do przewidzenia dla wszystkich obecnych.",
    "Rzecznik nie odniósł się do pytań dotyczących szczegółów całego zdarzenia.",
]


class Api:
    def __init__(self, base: str, key: str = "") -> None:
        self.base, self.key = base.rstrip("/"), key

    def call(self, method: str, path: str, body=None, raw: tuple[bytes, str] | None = None, expect=(200, 201)):
        headers = {"Accept": "application/json"}
        data = None
        if self.key and method != "GET":
            headers["X-API-Key"] = self.key
        if raw is not None:
            data, headers["Content-Type"] = raw
        elif body is not None:
            data, headers["Content-Type"] = json.dumps(body).encode(), "application/json"
        request = urllib.request.Request(self.base + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=300) as response:
                status, text = response.status, response.read()
        except urllib.error.HTTPError as exc:
            status, text = exc.code, exc.read()
        payload = json.loads(text) if text else None
        if status not in expect:
            raise RuntimeError(f"{method} {path}: HTTP {status}: {str(payload)[:400]}")
        return payload

    def pages(self, path: str) -> list[dict]:
        out, url = [], path
        while url:
            page = self.call("GET", url)
            out += page["results"]
            url = page.get("next")
            url = url.replace(self.base, "") if url else None
        return out


def multipart(name: str, filename: str, content: bytes) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    head = f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="{filename}"\r\nContent-Type: application/zip\r\n\r\n'
    return head.encode() + content + f"\r\n--{boundary}--\r\n".encode(), f"multipart/form-data; boundary={boundary}"


# ---------- budowa wariantów ----------

def find_case(raw: Path, key: str) -> Path:
    bundle, case = key.split("/", 1)
    root = raw / bundle
    for path in sorted(root.rglob(case)):
        if path.is_dir() and any(p.is_file() for p in path.iterdir()):
            return path
    sys.exit(f"Nie ma katalogu sprawy {key} pod {root}")


def read_html(case: Path) -> tuple[Path | None, str]:
    pages = sorted(p for p in case.iterdir() if p.suffix.lower() in (".html", ".htm") and p.is_file())
    if not pages:
        return None, ""
    return pages[0], pages[0].read_text(encoding="utf-8", errors="replace")


def source_host(html: str) -> str:
    match = re.search(r"saved from url=\(\d+\)https?://([^/\s?#]+)", html)
    return match.group(1) if match else ""


def crop_jpeg(path: Path, percent: float = 10.0, quality: int = 60) -> bytes:
    """Przycina obraz o `percent` procent powierzchni boków (po połowie z każdej krawędzi) i zapisuje JPEG."""
    image = Image.open(path).convert("RGB")
    w, h = image.size
    dx, dy = int(w * percent / 200), int(h * percent / 200)
    out = io.BytesIO()
    image.crop((dx, dy, w - dx, h - dy)).save(out, "JPEG", quality=quality)
    return out.getvalue()


def swap_sentences(html: str, count: int = 3) -> tuple[str, int]:
    """Podmienia pierwsze zdanie w `count` rozłożonych węzłach tekstu (poza skryptami i stylami)."""
    parts = re.split(r"(<script\b.*?</script>|<style\b.*?</style>|<title\b.*?</title>)", html, flags=re.DOTALL | re.IGNORECASE)
    nodes = []
    for i, part in enumerate(parts):
        if i % 2 == 0:
            for m in re.finditer(r">([^<>]{90,})<", part):
                sentence = re.match(r"\s*([^.!?]{25,}[.!?])\s", m.group(1))
                if sentence:
                    nodes.append((i, m.start(1) + (sentence.start(1)), sentence.group(1)))
    if not nodes:
        return html, 0
    step = max(1, len(nodes) // count)
    chosen = nodes[::step][:count]
    for n, (i, start, sentence) in reversed(list(enumerate(chosen))):
        replacement = INVENTED[n % len(INVENTED)]
        parts[i] = parts[i][:start] + replacement + parts[i][start + len(sentence):]
    return "".join(parts), len(chosen)


class TextOf(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.skip = 0
        self.blocks: list[str] = []
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "template", "svg"):
            self.skip += 1
        self._in_title = tag == "title"

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "template", "svg") and self.skip:
            self.skip -= 1
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        text = " ".join(data.split())
        if self._in_title:
            self.title += text
        elif text and not self.skip:
            self.blocks.append(text)


def plain_page(html: str, host: str) -> str:
    """Strona z samym widocznym tekstem oryginału: bez skryptów, zasobów, identyfikatorów i oryginalnej domeny."""
    parser = TextOf()
    parser.feed(html)
    esc = lambda s: s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    body = "\n".join(f"<p>{esc(b)}</p>" for b in parser.blocks if len(b) > 1)
    return (f'<!DOCTYPE html>\n<!-- saved from url=(0030)https://{host}/artykul -->\n<html lang="pl"><head><meta charset="utf-8">'
            f"<title>{esc(parser.title)}</title></head><body><article>\n{body}\n</article></body></html>\n")


def zip_case(files: dict[str, bytes], tree: list[tuple[Path, str]] | None = None) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(name, data)
        for source, arcname in tree or []:
            archive.write(source, arcname)
    return out.getvalue()


def build_disguise(case: Path, host_new: str, with_har: bool) -> tuple[bytes, dict]:
    page, html = read_html(case)
    old = source_host(html)
    info = {"stary_host": bool(old), "har": "brak w sprawie", "zdania": 0, "zrzuty": 0}
    files: dict[str, bytes] = {}
    tree: list[tuple[Path, str]] = []
    for item in sorted(case.iterdir()):
        if item.is_file() and item.suffix.lower() in IMAGE_EXT:
            files[f"zrzut_{info['zrzuty']}.jpg"] = crop_jpeg(item)
            info["zrzuty"] += 1
        elif item.is_file() and item.suffix.lower() == ".har":
            if with_har:
                data = item.read_bytes()
                if old:
                    data = data.replace(old.encode(), host_new.encode())
                files[item.name.replace(old, host_new) if old else item.name] = data
                info["har"] = "z podmienioną domeną" if old else "bez zmian"
            else:
                info["har"] = "usunięty"
    if page is not None:
        changed, info["zdania"] = swap_sentences(html, 3)
        if old:
            changed = changed.replace(old, host_new)
        files[page.name] = changed.encode("utf-8")
        assets = case / (page.stem + "_files")
        if assets.is_dir():
            tree += [(p, f"{page.stem}_files/{p.relative_to(assets).as_posix()}") for p in assets.rglob("*") if p.is_file()]
    return zip_case(files, tree), info


def build_trap(case: Path, host_new: str) -> tuple[bytes, dict]:
    _, html = read_html(case)
    files = {"strona.html": plain_page(html, host_new).encode("utf-8")}
    count = 0
    for item in sorted(case.iterdir()):
        if item.is_file() and item.suffix.lower() in IMAGE_EXT:
            files[f"zrzut_{count}{item.suffix.lower()}"] = item.read_bytes()
            count += 1
    return zip_case(files), {"zrzuty": count, "har": "brak", "strona": "sam widoczny tekst, bez skryptów i zasobów"}


# ---------- pomiar ----------

def case_of(external_id: str, labels: dict | None = None) -> str:
    parts = external_id.split("/")
    return "/".join(parts[:2])


def wait_analysis(api: Api, analysis_id: str, limit: int = 900) -> dict:
    deadline = time.monotonic() + limit
    while time.monotonic() < deadline:
        analysis = api.call("GET", f"/api/analyses/{analysis_id}")
        if analysis["status"] in ("done", "failed"):
            return analysis
        time.sleep(2)
    raise RuntimeError(f"Analiza {analysis_id} nie skończyła się w {limit} s")


def markers(detail: dict) -> set[tuple[str, str]]:
    return {(m["kind"], str(m["value"])) for fam in detail["genome"] for m in fam["markers"] if not any(s in m["kind"] for s in SOFT)}


def snapshot(api: Api, ad_id: int, ads_by_id: dict[int, dict], keys: dict[str, int]) -> dict:
    """Stan reklamy: kampania, operator, ich skład i krawędzie. Reklamy z uploadów nie liczą się do składu."""
    detail = api.call("GET", f"/api/ads/{ad_id}")
    out = {"ad": ad_id, "external_id": detail["external_id"], "campaign": detail["campaign"], "operator": detail["operator"], "markers": sorted(markers(detail))}
    for group, route in (("campaign", "campaigns"), ("operator", "operators")):
        key = detail[group]
        members = []
        if key:
            info = api.call("GET", f"/api/{route}/{keys[key]}")
            members = sorted({case_of(ad["external_id"]) for ad in info["ads"] if ad["id"] != ad_id and not ad["external_id"].startswith("upload-")})
        out[f"{group}_cases"] = members
    edges = []
    for edge in api.call("GET", f"/api/ads/{ad_id}/edges"):
        other = edge["ad_b"] if edge["ad_a"] == ad_id else edge["ad_a"]
        other_ad = ads_by_id.get(other)
        if other_ad is None:
            other_ad = api.call("GET", f"/api/ads/{other}")
            ads_by_id[other] = other_ad
        edges.append({"z": other_ad["external_id"], "relacja": edge["relation"], "bity": round(edge["bits"], 1), "pewnosc": round(edge["probability"], 3), "decisive": edge["decisive"], "rodziny": edge["families"]})
    out["krawedzie"] = edges
    return out


def group_keys(api: Api) -> dict[str, int]:
    keys = {}
    for route in ("campaigns", "operators"):
        for item in api.pages(f"/api/{route}"):
            keys[item["key"]] = item["id"]
    return keys


def upload(api: Api, name: str, blob: bytes) -> dict:
    created = api.call("POST", "/api/analyses/upload", raw=multipart("files", f"{name}.zip", blob))
    if len(created) != 1:
        raise RuntimeError(f"{name}: upload dał {len(created)} analiz zamiast 1")
    analysis = wait_analysis(api, created[0]["id"])
    if analysis["status"] != "done" or not analysis["ad"]:
        raise RuntimeError(f"{name}: analiza {analysis['status']}: {analysis['error']}")
    return analysis


def baseline(api: Api, cases: list[str]) -> dict[str, dict]:
    ads = api.pages("/api/ads?source=capture")
    found: dict[str, dict] = {}
    for ad in ads:
        if ad["external_id"].startswith("upload-"):
            continue
        found.setdefault(case_of(ad["external_id"]), ad)
    missing = [c for c in cases if c not in found]
    if missing:
        sys.exit(f"Na stosie nie ma spraw: {missing}")
    return found


def run_variants(api: Api, args, raw: Path, work: Path) -> list[dict]:
    keys = group_keys(api)
    first = baseline(api, args.sprawy)
    ads_by_id: dict[int, dict] = {}
    results = []
    tasks = []
    # Pułapka idzie pierwsza, żeby widziała korpus bez wcześniejszych wariantów.
    trap_case = find_case(raw, args.pulapka)
    tasks.append((f"pulapka|{args.pulapka}|obca_infrastruktura", args.pulapka, *build_trap(trap_case, FOREIGN_DOMAIN.format("obca-infrastruktura"))))
    for i, case_key in enumerate(args.sprawy):
        case = find_case(raw, case_key)
        has_har = any(p.suffix.lower() == ".har" for p in case.iterdir())
        host = FOREIGN_DOMAIN.format(f"zmyslona-{i + 1}")
        tasks.append((f"przebranie|{case_key}|bez_har", case_key, *build_disguise(case, host, with_har=False)))
        if has_har:
            tasks.append((f"przebranie|{case_key}|z_har_nowa_domena", case_key, *build_disguise(case, host, with_har=True)))
    for name, case_key, blob, info in tasks:
        safe = re.sub(r"[^\w.-]+", "_", name)
        (work / f"{safe}.zip").write_bytes(blob)
        started = time.monotonic()
        analysis = upload(api, safe, blob)
        original = snapshot(api, first[case_key]["id"], ads_by_id, keys)
        keys = {**keys, **group_keys(api)}
        variant = snapshot(api, analysis["ad"], ads_by_id, keys)
        survived = sorted(set(map(tuple, original["markers"])) & set(map(tuple, variant["markers"])))
        results.append({
            "wariant": name, "sprawa": case_key, "opis": info, "sekundy": round(time.monotonic() - started, 1),
            "oryginal": {k: original[k] for k in ("external_id", "campaign", "operator", "campaign_cases", "operator_cases")},
            "wynik": {k: variant[k] for k in ("external_id", "campaign", "operator", "campaign_cases", "operator_cases", "krawedzie")},
            "znaczniki": {"oryginal": len(original["markers"]), "wariant": len(variant["markers"]), "wspolne": len(survived),
                          "przetrwaly_rodzaje": sorted({k for k, _ in survived}),
                          "zniknely_rodzaje": sorted({k for k, _ in set(map(tuple, original["markers"])) - set(map(tuple, variant["markers"]))}),
                          "nowe_rodzaje": sorted({k for k, _ in set(map(tuple, variant["markers"])) - set(map(tuple, original["markers"]))})},
        })
        print(f"  {name}: kampania {variant['campaign']}, operator {variant['operator']}", flush=True)
    return results


def run_bridge(api: Api, raw_cases: list[str]) -> dict:
    """Szuka śladu, którego wyłączenie rozdziela grupę, i przechodzi cały cykl: podgląd, zakwestionowanie, przywrócenie."""
    ads = [a for a in api.pages("/api/ads?source=capture") if not a["external_id"].startswith("upload-")]
    count: dict[tuple[str, str], int] = {}
    for ad in ads:
        for marker in markers(api.call("GET", f"/api/ads/{ad['id']}")):
            count[marker] = count.get(marker, 0) + 1
    candidates = sorted((m for m, n in count.items() if n >= 2), key=lambda m: -count[m])
    tried, chosen = [], None
    for kind, value in candidates:
        try:
            preview = api.call("POST", "/api/premises/preview", {"kind": kind, "value": value}, expect=(200,))
        except RuntimeError as exc:
            tried.append({"kind": kind, "blad": str(exc)[:120]})
            continue
        splits = {g: len(preview["groups"][g]["split"]) for g in ("campaign", "operator")}
        tried.append({"kind": kind, "krawedzie": preview["edge_count"], "rozdzielone": splits})
        if chosen is None and (splits["operator"] or splits["campaign"]):
            chosen = (kind, value, preview)
    out = {"kandydaci": len(candidates), "sprawdzone": tried[:200], "wybrany": None}
    if chosen is None:
        return out
    kind, value, preview = chosen
    # w wyniku zapisujemy rodzaj i skrót wartości, nie samą wartość (identyfikatory kont operatora)
    import hashlib
    out["wybrany"] = {"kind": kind, "wartosc_skrot": hashlib.sha256(value.encode()).hexdigest()[:12], "podglad": preview}
    affected = sorted({ad for g in ("campaign", "operator") for item in preview["groups"][g]["split"] for ad in item["before"]})

    def states() -> dict[str, dict]:
        rows = {}
        for ad_id in affected:
            detail = api.call("GET", f"/api/ads/{ad_id}")
            rows[str(ad_id)] = {"sprawa": case_of(detail["external_id"]), "kampania": detail["campaign"], "operator": detail["operator"]}
        return rows

    out["stany"] = {"przed": states()}
    premise = api.call("POST", "/api/premises", {"kind": kind, "value": value, "reason": "Próba jury: sprawdzenie, czy ślad jest jedynym mostem między grupami"}, expect=(201,))
    out["zakwestionowanie"] = {"id": premise["id"], "regroup": premise.get("regroup")}
    out["stany"]["po_zakwestionowaniu"] = states()
    restored = api.call("POST", f"/api/premises/{premise['id']}/restore", {}, expect=(200, 201))
    out["przywrocenie"] = {"status": restored.get("status"), "regroup": restored.get("regroup")}
    out["stany"]["po_przywroceniu"] = states()
    out["przywrocone_calkowicie"] = out["stany"]["przed"] == out["stany"]["po_przywroceniu"]
    return out


# ---------- ocena ----------

def verdict(item: dict, member_of: dict[str, str], groups: dict[str, list[str]]) -> dict:
    """Ocena względem etykiet. Przebranie ma dołączyć do grupy sprawy, pułapka nie może dostać wspólnego źródła z grupą."""
    result = item["wynik"]
    trap = item["wariant"].startswith("pulapka")
    group = member_of.get(item["sprawa"])
    expected = set(groups.get(group, [])) - {item["sprawa"]}
    got = set(result["operator_cases"]) | set(result["campaign_cases"])
    foreign = sorted(c for c in got if c in member_of and member_of[c] != group)
    own = sorted(got & (expected | {item["sprawa"]}))
    relations = {}
    for edge in result["krawedzie"]:
        if not edge["z"].startswith("upload-"):
            relations.setdefault(case_of(edge["z"]), set()).add(edge["relacja"])
    to_original = sorted(relations.get(item["sprawa"], []))
    common = {r for c, rs in relations.items() if c in (expected | {item["sprawa"]}) for r in rs} & {"same_campaign", "same_operator"}
    return {
        "grupa": group, "oczekiwanie": "similar, bez wspólnego źródła" if trap else "ta sama grupa co oryginał",
        "w_grupie": own, "obce_w_grupie": foreign, "do_oryginalu": to_original,
        "operator_oryginalu": item["oryginal"]["operator"], "operator_wariantu": result["operator"], "kampania_wariantu": result["campaign"],
        "zgodne": (not common and not result["operator"]) if trap else (bool(own) and not foreign),
    }


def table(results: list[dict], member_of: dict[str, str], groups: dict[str, list[str]]) -> list[dict]:
    rows = []
    print(f"{'wariant':50} {'oryg.':8} {'wariant':8} {'do oryginału':14} {'markery':8} zgodne  zniknęły")
    for item in results:
        v = verdict(item, member_of, groups)
        m = item["znaczniki"]
        print(f"{item['wariant']:50} {v['operator_oryginalu']!s:8} {v['operator_wariantu']!s:8} {','.join(v['do_oryginalu']) or '-':14} {m['wspolne']}/{m['oryginal']:<5} {'tak' if v['zgodne'] else 'NIE':6} {','.join(m['zniknely_rodzaje'])[:60]}")
        rows.append({"wariant": item["wariant"], **v})
    return rows


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api", required=True, help="adres API osobnego stosu, np. http://localhost:8300")
    parser.add_argument("--paczki", required=True, type=Path, help="katalog z paczkami (data/raw)")
    parser.add_argument("--sprawy", nargs="+", required=True, help="sprawy do przebrania, np. nask/1 nask-backup/p7")
    parser.add_argument("--pulapka", required=True, help="sprawa, z której powstaje pułapka (kopia kreacji i tekstu)")
    parser.add_argument("--etykiety", required=True, type=Path, help="plik etykiet JSON, czytany dopiero po zapisaniu wyniku")
    parser.add_argument("--wynik", required=True, type=Path, help="plik wyniku JSON (poza repozytorium)")
    parser.add_argument("--robocze", required=True, type=Path, help="katalog na warianty (poza repozytorium)")
    parser.add_argument("--klucz", default="", help="API_WRITE_KEY, jeśli stos go wymaga")
    parser.add_argument("--bez-mostu", action="store_true", help="pomiń próbę 3")
    parser.add_argument("--tylko-ocena", action="store_true", help="nie wysyłaj niczego: oceń zapisany wcześniej plik --wynik według etykiet")
    args = parser.parse_args()
    if args.tylko_ocena:
        saved = json.loads(args.wynik.read_text(encoding="utf-8"))
        results, bridge = saved["warianty"], saved["most"]
    else:
        api = Api(args.api, args.klucz)
        api.call("GET", "/health")
        args.robocze.mkdir(parents=True, exist_ok=True)
        bridge = None
        if not args.bez_mostu:
            print("== próba 3: zakwestionowanie mostu (na korpusie bez wariantów)", flush=True)
            bridge = run_bridge(api, args.sprawy)
        print("== próby 1 i 2: warianty przez upload", flush=True)
        results = run_variants(api, args, args.paczki, args.robocze)
        args.wynik.write_text(json.dumps({"warianty": results, "most": bridge}, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"Wynik zapisany: {args.wynik}", flush=True)

    labels = json.loads(args.etykiety.read_text(encoding="utf-8"))
    groups = labels["grupy"]
    member_of = {case: group for group, cases in groups.items() for case in cases}
    print()
    rows = table(results, member_of, groups)
    if bridge and bridge["wybrany"]:
        b = bridge["wybrany"]
        print(f"\nMost: {b['kind']} (skrót {b['wartosc_skrot']}), krawędzi {b['podglad']['edge_count']}, grup do rozdzielenia {b['podglad']['split_count']}")
        print(f"  zakwestionowanie: {json.dumps(bridge['zakwestionowanie']['regroup'], ensure_ascii=False)[:300]}")
        print(f"  przywrócenie:     status {bridge['przywrocenie']['status']}, stan grup jak przed zakwestionowaniem: {bridge['przywrocone_calkowicie']}")
        for step, rows_ in bridge["stany"].items():
            print(f"    {step}: " + ", ".join(f"{r['sprawa']}={r['operator']}" for r in rows_.values()))
        splitting = [t["kind"] for t in bridge["sprawdzone"] if t.get("rozdzielone") and any(t["rozdzielone"].values())]
        print(f"  ślady, których wyłączenie rozdziela grupę: {splitting} (z {bridge['kandydaci']} wspólnych)")
    elif bridge:
        print(f"\nMost: żaden z {bridge['kandydaci']} wspólnych śladów nie rozdziela grupy")
    (args.wynik.parent / (args.wynik.stem + "_ocena.json")).write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
