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


def strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()


class Command(BaseCommand):
    help = (
        "Buduje bazę referencyjną twarzy: zdjęcie osoby z Wikidata (P18), tylko na wolnej licencji z Wikimedia Commons, "
        "wektor SFace i źródło zapisane w people/face_refs.json. Zdjęć nie zapisujemy."
    )

    def add_arguments(self, parser):
        parser.add_argument("--names", help="Lista osób po przecinku. Domyślnie cała baza z seed_people.")

    def handle(self, *args, **options):
        if not faces.ensure_models(download=True):
            raise CommandError("Brak modeli twarzy i nie udało się ich pobrać.")
        names = [n.strip() for n in options["names"].split(",")] if options["names"] else PEOPLE
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
        images = entity["claims"]["P18"]
        filename = images[0]["mainsnak"]["datavalue"]["value"]
        pages = get_json(
            "https://commons.wikimedia.org/w/api.php",
            {
                "action": "query",
                "titles": f"File:{filename}",
                "prop": "imageinfo",
                "iiprop": "url|extmetadata",
                "iiurlwidth": THUMB_WIDTH,
                "format": "json",
            },
        )["query"]["pages"]
        info = next(iter(pages.values()))["imageinfo"][0]
        meta = info.get("extmetadata", {})
        license_name = strip_html(meta.get("LicenseShortName", {}).get("value", ""))
        if not FREE_LICENSE.match(license_name):
            self.stdout.write(f"  {name}: licencja zdjęcia '{license_name}' nie jest wolna, pomijam")
            return None
        found_faces = faces.embeddings(get_bytes(info["thumburl"]))
        if not found_faces:
            self.stdout.write(f"  {name}: na zdjęciu nie wykryto twarzy")
            return None
        # Zdjęcie portretowe: bierzemy największą twarz.
        box, vector = max(found_faces, key=lambda f: f[0][2] * f[0][3])
        self.stdout.write(f"  {name} ({qid}, {description}): {license_name}, twarz {box[2]}x{box[3]} px")
        return {
            "name": name,
            "wikidata": qid,
            "description": description,
            "file": filename,
            "file_page": info["descriptionurl"],
            "license": license_name,
            "license_url": strip_html(meta.get("LicenseUrl", {}).get("value", "")),
            "author": strip_html(meta.get("Artist", {}).get("value", ""))[:200],
            "embedding": [round(v, 6) for v in vector],
        }
