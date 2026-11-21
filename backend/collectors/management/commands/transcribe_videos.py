"""Transkrybuje mowę z nagrań w już zaimportowanych reklamach, bez ponownego importu.

Plik bierzemy z magazynu dowodów, a gdy go tam nie ma (ponad limit rozmiaru), z katalogu `--root` po skrócie
SHA-256. Transkrypt trafia do `Ad.raw["videos"][i]["speech"]` (z oznaczeniem źródła) i do tekstu reklamy.
Z `--reanalyze` reklama dostaje nową analizę, więc nazwiska, słowa kluczowe i wektor tekstu liczą się od nowa.
"""

import tempfile
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from ads.models import Ad, Analysis
from collectors.bundle import VIDEO_EXT, _file_sha256
from evidence import store
from evidence.models import Artifact
from extractors import speech
from workflows import pipeline


def merge_text(text: str, old: str, new: str) -> str:
    """Podmienia dawny transkrypt w tekście reklamy na nowy albo dopisuje go na końcu."""
    if old and old in text:
        return text.replace(old, new, 1).strip()
    return f"{text} {new}".strip() if new else text


class Command(BaseCommand):
    help = "Przepisuje mowę z nagrań zaimportowanych reklam na tekst (faster-whisper, lokalnie, CPU)."

    def add_arguments(self, parser):
        parser.add_argument("--root", action="append", default=[], help="Katalog z paczkami, gdy nagrania nie ma w magazynie.")
        parser.add_argument("--all", action="store_true", help="Także nagrania, które już sprawdzono.")
        parser.add_argument("--ad", type=int, action="append", default=[], help="Tylko reklama o tym numerze (można powtórzyć).")
        parser.add_argument("--reanalyze", action="store_true", help="Po zmianie tekstu uruchom analizę reklamy od nowa.")

    def handle(self, *args, **options):
        if not speech.enabled():
            raise CommandError("Transkrypcja wyłączona (TRANSCRIBE=off) albo brak biblioteki faster-whisper.")
        originals = self._index(options["root"])
        queryset = Ad.objects.filter(raw__has_key="videos").order_by("pk")
        if options["ad"]:
            queryset = queryset.filter(pk__in=options["ad"])
        done = silent = missing = 0
        changed_ads: list[Ad] = []
        for ad in queryset:
            videos = ad.raw.get("videos") or []
            text = ad.text
            changed = False
            for entry in videos:
                if not isinstance(entry, dict) or not entry.get("sha256") or ("speech" in entry and not options["all"]):
                    continue
                with tempfile.TemporaryDirectory() as tmp:
                    path = self._file(entry, originals, Path(tmp))
                    if path is None:
                        missing += 1
                        self.stdout.write(self.style.WARNING(f"reklama {ad.pk}: nie ma pliku {entry.get('name')} w magazynie ani w --root"))
                        continue
                    transcript = speech.transcribe(str(path))
                old = (entry.get("speech") or {}).get("text", "")
                if transcript:
                    entry["speech"] = speech.describe(transcript)
                    text = merge_text(text, old, transcript.text)
                    done += 1
                    self.stdout.write(f"reklama {ad.pk}: {transcript.audio_s} s dźwięku w {transcript.elapsed_s} s, {len(transcript.text)} znaków")
                else:
                    entry["speech"] = None
                    text = merge_text(text, old, "")
                    silent += 1
                changed = True
            if changed:
                ad.raw["videos"] = videos
                ad.text = text
                ad.save(update_fields=["raw", "text"])
                changed_ads.append(ad)
        if options["reanalyze"]:
            self._reanalyze(changed_ads)
        self.stdout.write(self.style.SUCCESS(f"Z mową: {done}. Bez mowy albo bez wyniku: {silent}. Nagrania bez pliku: {missing}."))

    def _file(self, entry: dict, originals: dict[str, Path], tmp: Path) -> Path | None:
        sha = entry["sha256"]
        if Artifact.objects.filter(pk=sha, kind="creative_video").exists():
            path = tmp / f"v{Path(entry.get('name', '')).suffix or '.mp4'}"
            path.write_bytes(store.get(sha))
            return path
        return originals.get(sha)

    def _reanalyze(self, ads: list[Ad]) -> None:
        created = []
        for ad in ads:
            last = Analysis.objects.filter(ad=ad).order_by("-pk").first()
            if last is None:
                continue
            created.append(Analysis.objects.create(ad=ad, input_kind=last.input_kind, input_value=last.input_value, state=last.state))
        for analysis in created:
            pipeline.run_all(str(analysis.pk))
        for analysis in created:
            for stage in ("fuse", "cluster"):
                pipeline.run_stage(str(analysis.pk), stage)
        self.stdout.write(f"Nowe analizy: {len(created)}")

    def _index(self, roots: list[str]) -> dict[str, Path]:
        found: dict[str, Path] = {}
        for root in roots:
            for path in Path(root).rglob("*"):
                if path.is_file() and path.suffix.lower() in VIDEO_EXT:
                    found[_file_sha256(path)] = path
        return found
