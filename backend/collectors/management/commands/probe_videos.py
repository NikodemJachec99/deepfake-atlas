"""Uzupełnia metadane nagrań w już zaimportowanych reklamach, bez ponownego importu.

Plik bierzemy z magazynu dowodów, a gdy go tam nie ma (ponad limit rozmiaru), z katalogu `--root` po skrócie
SHA-256. Klatka poglądowa trafia do magazynu jako `video_frame`. Reklamy i markery zostają bez zmian, zmienia
się tylko opis nagrań w `Ad.raw["videos"]`.
"""

import tempfile
from pathlib import Path

from django.core.management.base import BaseCommand

from ads.models import Ad
from collectors.bundle import VIDEO_EXT, _file_sha256, describe_video
from evidence import store
from evidence.models import Artifact


class Command(BaseCommand):
    help = "Odczytuje długość, rozdzielczość i klatkę poglądową nagrań w zaimportowanych reklamach."

    def add_arguments(self, parser):
        parser.add_argument("--root", action="append", default=[], help="Katalog z paczkami, gdy nagrania nie ma w magazynie.")
        parser.add_argument("--all", action="store_true", help="Także nagrania, które mają już metadane.")

    def handle(self, *args, **options):
        originals = self._index(options["root"])
        updated = missing = 0
        for ad in Ad.objects.filter(raw__has_key="videos").order_by("pk"):
            videos = ad.raw.get("videos") or []
            changed = False
            for i, entry in enumerate(videos):
                if not isinstance(entry, dict) or not entry.get("sha256") or ("duration_s" in entry and not options["all"]):
                    continue
                sha = entry["sha256"]
                base = {k: entry[k] for k in ("name", "size", "sha256", "speech") if k in entry}
                base["stored"] = Artifact.objects.filter(pk=sha, kind="creative_video").exists()
                if base["stored"]:
                    with tempfile.TemporaryDirectory() as tmp:
                        path = Path(tmp) / f"v{Path(entry.get('name', '')).suffix or '.mp4'}"
                        path.write_bytes(store.get(sha))
                        videos[i] = describe_video(path, base, [])
                elif sha in originals:
                    videos[i] = describe_video(originals[sha], base, [])
                else:
                    missing += 1
                    self.stdout.write(self.style.WARNING(f"reklama {ad.pk}: nie ma pliku {entry.get('name')} w magazynie ani w --root"))
                    continue
                changed = True
            if changed:
                ad.raw["videos"] = videos
                ad.save(update_fields=["raw"])
                updated += 1
        self.stdout.write(self.style.SUCCESS(f"Zaktualizowane reklamy: {updated}. Nagrania bez pliku: {missing}."))

    def _index(self, roots: list[str]) -> dict[str, Path]:
        found: dict[str, Path] = {}
        for root in roots:
            for path in Path(root).rglob("*"):
                if path.is_file() and path.suffix.lower() in VIDEO_EXT:
                    found[_file_sha256(path)] = path
        return found
