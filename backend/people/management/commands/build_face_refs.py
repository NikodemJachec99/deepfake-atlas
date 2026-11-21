import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from django.core.management.base import BaseCommand, CommandError

from people import faces
from people.management.commands.seed_people import PEOPLE

USER_AGENT = "scamdna-hackathon/0.1 (badania nad kampaniami oszustw; kontakt przez repozytorium projektu)"
FREE_LICENSE = re.compile(r"^(CC0|CC BY(-SA)? [\d.]+|Public domain|PD|GFDL)", re.I)
# Imiennicy: opis w Wikidata musi zawierać to słowo. Bez tego "Krzysztof Stanowski" to działacz z lat 80., nie dziennikarz.
HINTS = {"Krzysztof Stanowski": "dziennikarz", "Tomasz Sekielski": "dziennikarz", "Piotr Kraśko": "dziennikarz", "Katarzyna Dowbor": "dziennikar"}
THUMB_WIDTH = 500  # Commons ogranicza miniatury spoza standardowych rozmiarów
MAX_CATEGORY_DOWNLOADS = 12
# Dwa zdjęcia tej samej osoby w SFace mają zwykle podobieństwo wyraźnie powyżej progu dopasowania (0,363).
AGREEMENT = 0.5


def fetch(url: str, attempts: int = 8) -> bytes:
    """Pobranie z ponawianiem. Wikimedia przy zbyt częstych zapytaniach odpowiada 429 z Retry-After."""
    for attempt in range(attempts):
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            if exc.code != 429 or attempt == attempts - 1:
                raise OSError(f"{urllib.parse.urlsplit(url).hostname}: HTTP {exc.code}") from exc
            retry_after = exc.headers.get("Retry-After", "")
            time.sleep(min(int(retry_after), 300) if retry_after.isdigit() else 15 * (attempt + 1))
    raise OSError(url)


def get_json(url: str, params: dict) -> dict:
    return json.loads(fetch(f"{url}?{urllib.parse.urlencode(params)}"))


def get_bytes(url: str) -> bytes:
    return fetch(url)


MAX_ORIGINAL_BYTES = 12 * 1024 * 1024


def image_bytes(info: dict) -> bytes:
    """Miniatura, a gdy Commons ją dławi (429), oryginał pliku, o ile nie jest zbyt duży."""
    try:
        return get_bytes(info["thumb"])
    except OSError:
        if info.get("original") and 0 < info.get("size", 0) <= MAX_ORIGINAL_BYTES:
            return get_bytes(info["original"])
        raise


def strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()


class Command(BaseCommand):
    help = (
        "Buduje bazę referencyjną twarzy: zdjęcie osoby z Wikidata (P18), tylko na wolnej licencji z Wikimedia Commons, "
        "wektor SFace i źródło zapisane w people/face_refs.json. Zdjęć nie zapisujemy."
    )

    def add_arguments(self, parser):
        parser.add_argument("--names", help="Lista osób po przecinku. Domyślnie cała baza z seed_people.")
        parser.add_argument("--file", action="append", default=[], metavar="OSOBA=PLIK",
                            help="Wskazany plik z Commons dla osoby, np. 'Jan Kowalski=File:Jan Kowalski 2024.jpg'. Licencja nadal musi być wolna.")

    def handle(self, *args, **options):
        if not faces.ensure_models(download=True):
            raise CommandError("Brak modeli twarzy i nie udało się ich pobrać.")
        names = [n.strip() for n in options["names"].split(",")] if options["names"] else PEOPLE
        self.forced = dict(item.split("=", 1) for item in options["file"] if "=" in item)
        existing = {ref["name"]: ref for ref in json.loads(faces.REFS_PATH.read_text(encoding="utf-8"))} if faces.REFS_PATH.exists() else {}
        for name in names:
            try:
                ref = self.reference(name)
            except OSError as exc:
                self.stdout.write(f"  {name}: błąd sieci ({exc}), zostaje poprzedni wpis")
                continue
            if ref:
                existing[name] = ref
                self.save(existing)  # po każdej osobie: Commons potrafi przyhamować na długo
            time.sleep(10)
        refs = self.save(existing)
        self.stdout.write(self.style.SUCCESS(f"Osób z twarzą w bazie: {len(refs)}. Zapisano {faces.REFS_PATH.name}"))

    def save(self, refs: dict) -> list[dict]:
        ordered = sorted(refs.values(), key=lambda r: r["name"])
        faces.REFS_PATH.write_text(json.dumps(ordered, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        faces.references.cache_clear()
        return ordered

    def reference(self, name: str) -> dict | None:
        found = get_json(
            "https://www.wikidata.org/w/api.php",
            {"action": "wbsearchentities", "search": name, "language": "pl", "type": "item", "limit": 5, "format": "json"},
        ).get("search", [])
        if not found:
            self.stdout.write(f"  {name}: brak w Wikidata")
            return None
        entities = get_json(
            "https://www.wikidata.org/w/api.php",
            {"action": "wbgetentities", "ids": "|".join(f["id"] for f in found), "props": "claims|descriptions", "languages": "pl|en", "format": "json"},
        )["entities"]

        def is_human_with_photo(entity: dict) -> bool:
            claims = entity.get("claims", {})
            human = any(c["mainsnak"].get("datavalue", {}).get("value", {}).get("id") == "Q5" for c in claims.get("P31", []))
            return human and bool(claims.get("P18"))

        # Imienników jest sporo. Bierzemy pierwszy wynik, który jest człowiekiem (P31 = Q5) i ma zdjęcie.
        def describes(entity: dict) -> str:
            descriptions = entity.get("descriptions", {})
            return " ".join(d.get("value", "") for d in descriptions.values()).lower()

        hint = HINTS.get(name, "")
        qid = next((f["id"] for f in found if is_human_with_photo(entities[f["id"]]) and hint in describes(entities[f["id"]])), None)
        if not qid:
            self.stdout.write(f"  {name}: wśród wyników Wikidata brak człowieka ze zdjęciem")
            return None
        entity = entities[qid]
        descriptions = entity.get("descriptions", {})
        description = (descriptions.get("pl") or descriptions.get("en") or {}).get("value", "")
        files = [c["mainsnak"]["datavalue"]["value"] for c in entity["claims"]["P18"]]
        if name in self.forced:
            return self.from_file(name, qid, description, self.forced[name])
        ref = self.from_file(name, qid, description, files[0])
        if ref:
            return ref
        # Zdjęcie z Wikidata nie nadaje się (zwykle licencja). Szukamy w kategorii osoby na Commons, ale tylko
        # portretów z jedną twarzą, i wymagamy zgodności z drugim niezależnym zdjęciem, żeby nie złapać kogoś obok.
        category = next((c["mainsnak"]["datavalue"]["value"] for c in entity["claims"].get("P373", [])), None)
        if not category:
            self.stdout.write(f"  {name}: brak kategorii na Commons, nie ma czego szukać dalej")
            return None
        return self.from_category(name, qid, description, category)

    def file_infos(self, titles: list[str]) -> list[dict]:
        pages = get_json(
            "https://commons.wikimedia.org/w/api.php",
            {"action": "query", "titles": "|".join(titles), "prop": "imageinfo", "iiprop": "url|extmetadata|mime|size",
             "iiurlwidth": THUMB_WIDTH, "format": "json"},
        )["query"]["pages"]
        out = []
        for page in pages.values():
            if "imageinfo" not in page:
                continue
            info = page["imageinfo"][0]
            meta = info.get("extmetadata", {})
            out.append({
                "file": page["title"].removeprefix("File:"),
                "thumb": info.get("thumburl", ""),
                "original": info.get("url", ""),
                "size": info.get("size", 0),
                "page": info.get("descriptionurl", ""),
                "mime": info.get("mime", ""),
                "license": strip_html(meta.get("LicenseShortName", {}).get("value", "")),
                "license_url": strip_html(meta.get("LicenseUrl", {}).get("value", "")),
                "author": strip_html(meta.get("Artist", {}).get("value", ""))[:200],
            })
        return out

    def entry(self, name, qid, description, info, box, vector, note="") -> dict:
        self.stdout.write(f"  {name} ({qid}, {description}): {info['license']}, {info['file']}, twarz {box[2]}x{box[3]} px{note}")
        return {
            "name": name, "wikidata": qid, "description": description, "file": info["file"], "file_page": info["page"],
            "license": info["license"], "license_url": info["license_url"], "author": info["author"],
            "embedding": [round(v, 6) for v in vector],
        }

    def from_file(self, name, qid, description, filename) -> dict | None:
        title = filename if filename.startswith("File:") else f"File:{filename}"
        infos = self.file_infos([title])
        if not infos:
            self.stdout.write(f"  {name}: plik {filename} nie istnieje na Commons")
            return None
        info = infos[0]
        if not FREE_LICENSE.match(info["license"]):
            self.stdout.write(f"  {name}: licencja zdjęcia '{info['license']}' ({info['file']}) nie jest wolna")
            return None
        found = faces.embeddings(image_bytes(info))
        if not found:
            self.stdout.write(f"  {name}: na zdjęciu {info['file']} nie wykryto twarzy")
            return None
        box, vector = max(found, key=lambda f: f[0][2] * f[0][3])  # portret: największa twarz
        return self.entry(name, qid, description, info, box, vector)

    def from_category(self, name, qid, description, category) -> dict | None:
        def members(cat: str, kind: str) -> list[str]:
            return [m["title"] for m in get_json(
                "https://commons.wikimedia.org/w/api.php",
                {"action": "query", "list": "categorymembers", "cmtitle": cat, "cmtype": kind, "cmlimit": 40, "format": "json"},
            )["query"]["categorymembers"]]

        # Pliki bywają tylko w podkategoriach (np. "... in 2025"), więc schodzimy jeden poziom niżej.
        titles = members(f"Category:{category}", "file")
        for subcat in members(f"Category:{category}", "subcat")[:10]:
            if len(titles) >= 40:
                break
            titles += members(subcat, "file")
        titles = [t for t in dict.fromkeys(titles) if t.lower().endswith((".jpg", ".jpeg", ".png"))][:40]
        infos = [i for chunk in range(0, len(titles), 20) for i in self.file_infos(titles[chunk:chunk + 20])]
        free = [i for i in infos if FREE_LICENSE.match(i["license"]) and i["thumb"]]
        self.stdout.write(f"  {name}: w kategorii {category} plików {len(titles)}, na wolnej licencji {len(free)}")
        portraits = []
        for info in free[:MAX_CATEGORY_DOWNLOADS]:
            try:
                found = faces.embeddings(image_bytes(info))
            except OSError:
                continue
            time.sleep(2)
            if len(found) != 1:
                continue  # zdjęcie grupowe albo bez twarzy: nie wiadomo, kto jest kim
            box, vector = found[0]
            for other_info, other_box, other_vector in portraits:
                if sum(a * b for a, b in zip(vector, other_vector, strict=True)) >= AGREEMENT:
                    best = max([(info, box, vector), (other_info, other_box, other_vector)], key=lambda t: t[1][2] * t[1][3])
                    return self.entry(name, qid, description, *best, note=f" (zgodne z {other_info['file'] if best[0] is info else info['file']})")
            portraits.append((info, box, vector))
        self.stdout.write(f"  {name}: nie znalazłem dwóch zgodnych portretów na wolnej licencji (sprawdzone: {len(portraits)} portretów)")
        return None
