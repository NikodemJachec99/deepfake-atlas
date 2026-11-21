"""Pakiet dowodowy operatora albo kampanii: jeden plik ZIP do przekazania prokuraturze albo innemu CERT.

Zawartość (katalog główny nazywa się tak jak plik):

- `raport.html`: samodzielny raport do druku (bez zewnętrznych zasobów, obrazy osadzone). Streszczenie, najmocniejsze
  dowody z wkładem w bitach, najsłabszy punkt, oś czasu, lista reklam, zrzuty, metoda i ograniczenia.
- `dowody/obrazy`, `dowody/wideo`, `dowody/surowe`: artefakty bajt w bajt tak, jak leżą w magazynie. Nazwa pliku to jego
  SHA-256, więc treści nie da się podmienić bez zmiany nazwy. HTML i HAR oszusta są tylko plikami (HTML z końcówką
  `.html.txt`, żeby dwuklik niczego nie uruchomił) i nigdy nie trafiają do raportu jako treść strony.
- `manifest.json`: dla każdego dowodu SHA-256, rozmiar, rodzaj, źródło (adres po redakcji), czas pozyskania do systemu
  i reklamy, z których pochodzi; osobno pominięte pliki z powodem.
- `SHA256SUMS`: sumy wszystkich plików pakietu (format `sha256sum -c`), `weryfikuj.py`: sprawdzenie jednym poleceniem.
- `stix.json` (istniejący eksport STIX zawężony do grupy), `krawedzie.jsonl` (krawędzie z dowodami), `os-czasu.json`.

Surowe pliki nie są redagowane: redakcja zmieniłaby ich sumę i zerwała łańcuch dowodu. Mogą więc zawierać tokeny z
przechwycenia. Wszystko, co generujemy sami (raport, manifest, krawędzie, STIX, oś czasu), ma adresy po `redact_url`.
`?surowe=0` pomija HAR i HTML.
"""

import base64
import hashlib
import heapq
import io
import json
import tempfile
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from django.db.models import F
from django.template import Context, Engine

from ads.models import Ad, Analysis, Source
from enrichment.models import DomainRecord, WarningDomain
from evidence import store
from evidence.kinds import FAMILIES, KINDS
from evidence.models import AdMarker, Artifact
from extractors import video
from extractors.url import redact_url
from people.display import display_value, person_names
from similarity import fusion, simulation, stix, timeline, weakest
from similarity.management.commands.export_corpus import edge_row
from similarity.models import Campaign, CampaignMembership, Edge, EdgeEvidence, Operator, OperatorMembership

FORMAT_VERSION = 1
MAX_FILE_BYTES = 50 * 1024 * 1024
MAX_TOTAL_BYTES = 1024 * 1024 * 1024
MAX_THUMBS = 40
THUMB_PX = 900
MAX_TIMELINE_ROWS = 80
MAX_AD_ROWS = 500
TOP_EVIDENCE = 15
TOP_EDGES = 5
WEAKEST_EDGES = 3
WEAKEST_BOTTOM = 2
WEAKEST_SCENARIOS = 500
WEAKEST_TIME_MS = 2000

IMAGE_KINDS = ("creative_image", "video_frame", "page_screenshot")
STORED_IMAGE_KINDS = (*IMAGE_KINDS, "favicon")  # favicona jest dowodem krawedzi, ale nie wchodzi do galerii zrzutow
IMAGE_SIGNATURES = ((b"\x00\x00\x01\x00", "ico"), (b"\x89PNG", "png"), (b"\xff\xd8\xff", "jpg"), (b"RIFF", "webp"), (b"GIF8", "gif"))
VIDEO_EXT = {"video/mp4": "mp4", "video/quicktime": "mov", "video/webm": "webm"}
ROLE_LABELS = {
    "creative_image": "kreacja reklamy",
    "creative_video": "nagranie reklamy",
    "video_frame": "klatka nagrania",
    "page_screenshot": "zrzut strony",
    "favicon": "favicona",
    "edge_evidence": "artefakt dowodu powiązania",
    "har": "HAR (ruch sieciowy)",
    "html_victim": "HTML strony (profil ofiary)",
    "html_bot": "HTML strony (profil bota)",
}
SOURCE_LABELS = {str(code): label for code, label in Source.choices}
VERDICT_LABELS = {code: label for code, label in Edge.Verdict.choices if code}
RELATION_LABELS = {code: label for code, label in Edge.Relation.choices}
PERSON_KINDS = ("person_mention", "face_match", "brand_impersonated")
TEMPLATE_DIR = Path(__file__).parent / "package_templates"
VERIFY_SCRIPT = Path(__file__).with_name("package_verify.py")

KIND_NOTES = {
    "motif": "wspólny motyw: nie potwierdza wspólnego źródła",
    "kit": "ślad silnika lejka: jedno potwierdzenie, silnik mógł kupić każdy",
}


class GroupNotFound(Exception):
    """Grupa nie ma żadnej reklamy, więc nie ma z czego zrobić pakietu."""


@dataclass
class GroupSpec:
    kind: str  # "operator" albo "campaign"
    obj: Operator | Campaign
    relations: list[str]
    ad_ids: list[int]

    @property
    def key(self) -> str:
        return self.obj.key


@dataclass
class Entry:
    """Plik dowodowy w pakiecie albo pominięty."""

    sha256: str
    kind: str
    ads: list[int] = field(default_factory=list)
    roles: list[str] = field(default_factory=list)
    path: str = ""
    size: int = 0
    content_type: str = ""
    source_url: str = ""
    acquired_at: str = ""
    skipped: str = ""


@dataclass
class Package:
    file: object  # plik tymczasowy ZIP, ustawiony na początek
    filename: str
    files: int
    size: int
    skipped: int
    sha256: str = ""  # skrót całego ZIP, do przekazania odbiorcy osobnym kanałem


def spec_for(kind: str, obj) -> GroupSpec:
    if kind == "operator":
        ad_ids = list(OperatorMembership.objects.filter(operator=obj).values_list("ad_id", flat=True))
        relations = [Edge.Relation.SAME_CAMPAIGN, Edge.Relation.SAME_OPERATOR]
    else:
        ad_ids = list(CampaignMembership.objects.filter(campaign=obj).values_list("ad_id", flat=True))
        relations = [Edge.Relation.SAME_CAMPAIGN]
    return GroupSpec(kind, obj, [str(r) for r in relations], sorted(ad_ids))


def pl(value: float, digits: int = 1) -> str:
    return f"{value:.{digits}f}".replace(".", ",")


def human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n} B" if unit == "B" else f"{n:.1f} {unit}".replace(".", ",")
        n /= 1024
    return f"{n} B"


def iso(value: datetime | None) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds") if value else ""


def clip(text: str, n: int) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= n else text[: n - 1] + "…"


def safe_text(value: str, n: int = 200) -> str:
    """Wartość markera do raportu: adresy po redakcji, bez znaków sterujących, przycięta."""
    value = " ".join(str(value).split())
    if value.startswith(("http://", "https://")):
        value = redact_url(value)
    return clip(value, n)


def image_ext(data: bytes) -> str | None:
    return next((ext for magic, ext in IMAGE_SIGNATURES if data.startswith(magic)), None)


def thumbnail(data: bytes) -> str | None:
    """Miniatura do osadzenia w raporcie jako data URI. Bajty muszą być obrazem (po sygnaturze, bez SVG)."""
    if image_ext(data) is None:
        return None
    try:
        from PIL import Image

        with Image.open(io.BytesIO(data)) as img:
            img.load()
            img.thumbnail((THUMB_PX, THUMB_PX))
            if img.mode in ("RGBA", "LA", "P"):
                img = img.convert("RGBA")
                flat = Image.new("RGB", img.size, "white")
                flat.paste(img, mask=img.split()[-1])
                img = flat
            else:
                img = img.convert("RGB")
            out = io.BytesIO()
            img.save(out, "JPEG", quality=82)
    except Exception:  # noqa: BLE001  uszkodzony obraz albo bomba dekompresji: raport działa bez miniatury
        return None
    return "data:image/jpeg;base64," + base64.b64encode(out.getvalue()).decode("ascii")


class Archive:
    """ZIP z jednym katalogiem głównym i rejestrem sum kontrolnych wszystkich zapisanych plików."""

    def __init__(self, target, root: str) -> None:
        self.zip = zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=6)
        self.root = root
        self.sums: dict[str, str] = {}
        self.sizes: dict[str, int] = {}

    def add(self, path: str, data: bytes, compress: bool = True) -> str:
        info = zipfile.ZipInfo(f"{self.root}/{path}", date_time=datetime.now(UTC).timetuple()[:6])
        info.compress_type = zipfile.ZIP_DEFLATED if compress else zipfile.ZIP_STORED
        info.external_attr = 0o644 << 16
        self.zip.writestr(info, data)
        digest = hashlib.sha256(data).hexdigest()
        self.sums[path], self.sizes[path] = digest, len(data)
        return digest

    def add_file(self, path: str, handle) -> str:
        """Dodaje plik z uchwytu bez trzymania go w pamięci."""
        info = zipfile.ZipInfo(f"{self.root}/{path}", date_time=datetime.now(UTC).timetuple()[:6])
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o644 << 16
        digest, size = hashlib.sha256(), 0
        with self.zip.open(info, "w", force_zip64=True) as out:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                digest.update(chunk)
                size += len(chunk)
                out.write(chunk)
        self.sums[path], self.sizes[path] = digest.hexdigest(), size
        return self.sums[path]

    def close(self) -> None:
        self.zip.close()


def latest_states(ad_ids: list[int]) -> dict[int, dict]:
    """Stan ostatniej analizy każdej reklamy: stąd znamy HAR, HTML i zrzut strony."""
    rows = Analysis.objects.filter(ad_id__in=ad_ids).order_by("ad_id", "-created_at").distinct("ad_id")
    return {a.ad_id: a.state or {} for a in rows}


def edge_artifact_refs(spec: GroupSpec) -> list[tuple[str, int]]:
    """Artefakty wskazane jako dowód na krawędziach grupy: (suma, id reklamy, do której należą)."""
    rows = (
        EdgeEvidence.objects.filter(edge__ad_a_id__in=spec.ad_ids, edge__ad_b_id__in=spec.ad_ids, edge__relation__in=spec.relations)
        .order_by("edge_id", "pk")
        .values_list("artifact_a_id", "artifact_b_id", "edge__ad_a_id", "edge__ad_b_id")
    )
    found: list[tuple[str, int]] = []
    for sha_a, sha_b, ad_a, ad_b in rows.iterator(chunk_size=1000):
        found.append((sha_a, ad_a))
        found.append((sha_b, ad_b))
    return found


def collect_refs(ads: list[Ad], states: dict[int, dict], edge_artifacts: list[tuple[str, int]] | None = None) -> dict[str, Entry]:
    """Które artefakty należą do reklam grupy i w jakiej roli, w kolejności reklam (od najstarszej).

    `edge_artifacts` to artefakty z dowodów na krawędziach grupy (np. favicony): też wchodzą do pakietu,
    żeby każdy dowód z `krawedzie.jsonl` miał plik albo wpis w `pominiete`."""
    refs: dict[str, Entry] = {}

    def ref(sha: str | None, kind: str, ad: Ad) -> None:
        if not sha or not isinstance(sha, str):
            return
        entry = refs.setdefault(sha, Entry(sha256=sha, kind=kind))
        if ad.pk not in entry.ads:
            entry.ads.append(ad.pk)
        if kind not in entry.roles:
            entry.roles.append(kind)

    for ad in ads:
        raw = ad.raw if isinstance(ad.raw, dict) else {}
        for sha in raw.get("creatives", []):
            ref(sha, "creative_image", ad)
        for item in raw.get("videos", []):
            if isinstance(item, dict):
                ref(item.get("sha256"), "creative_video", ad)
                poster = item.get("poster")
                ref(poster.get("artifact") if isinstance(poster, dict) else None, "video_frame", ad)
        state = states.get(ad.pk, {})
        pages = state.get("pages") or {}
        victim, bot = pages.get("victim") or {}, pages.get("bot") or {}
        ref(victim.get("screenshot_sha"), "page_screenshot", ad)
        ref(bot.get("screenshot_sha"), "page_screenshot", ad)
        ref((state.get("capture") or {}).get("har"), "har", ad)
        ref(victim.get("html_sha"), "html_victim", ad)
        ref(bot.get("html_sha"), "html_bot", ad)
    by_pk = {ad.pk: ad for ad in ads}
    for sha, ad_id in edge_artifacts or []:
        if ad_id in by_pk:
            ref(sha, "edge_evidence", by_pk[ad_id])
    return refs


def write_evidence(archive: Archive, refs: dict[str, Entry], include_raw: bool) -> tuple[list[Entry], dict[str, str]]:
    """Zapisuje artefakty do `dowody/`. Zwraca wpisy (też pominięte) i miniatury obrazów do raportu."""
    rows = {a.sha256: a for a in Artifact.objects.filter(pk__in=refs)}
    entries: list[Entry] = []
    thumbs: dict[str, str] = {}
    total = 0
    for sha, entry in refs.items():
        artifact = rows.get(sha)
        if artifact is None:
            entry.skipped = "brak wpisu o artefakcie w bazie"
            entries.append(entry)
            continue
        entry.kind = artifact.kind
        entry.content_type = artifact.content_type
        entry.source_url = redact_url(artifact.source_url) if artifact.source_url else ""
        entry.acquired_at = iso(artifact.created_at)
        entry.size = artifact.size
        raw_kind = artifact.kind == "har" or artifact.kind.startswith("html")
        if raw_kind and not include_raw:
            entry.skipped = "pominięto na żądanie (surowe=0)"
        elif artifact.size > MAX_FILE_BYTES:
            entry.skipped = f"plik ma {human_size(artifact.size)}, limit pakietu to {human_size(MAX_FILE_BYTES)}"
        elif total + artifact.size > MAX_TOTAL_BYTES:
            entry.skipped = f"przekroczony łączny limit pakietu {human_size(MAX_TOTAL_BYTES)}"
        if entry.skipped:
            entries.append(entry)
            continue
        try:
            data = store.get(sha)
        except Exception:  # noqa: BLE001  brak obiektu w magazynie nie może przewrócić całego pakietu
            entry.skipped = "nie udało się odczytać pliku z magazynu"
            entries.append(entry)
            continue
        if hashlib.sha256(data).hexdigest() != sha:
            entry.skipped = "suma SHA-256 odczytanego pliku nie zgadza się z zapisaną: plik w magazynie jest uszkodzony"
            entries.append(entry)
            continue
        if artifact.kind in STORED_IMAGE_KINDS:
            folder, ext, compress = "obrazy", image_ext(data) or "bin", False
        elif artifact.kind == "creative_video":
            folder, ext, compress = "wideo", VIDEO_EXT.get(video.content_type(data[:16]) or "", "bin"), False
        elif artifact.kind == "har":
            folder, ext, compress = "surowe", "har", True
        elif artifact.kind.startswith("html"):
            folder, ext, compress = "surowe", "html.txt", True
        else:
            entry.skipped = f"rodzaj artefaktu spoza pakietu: {artifact.kind}"
            entries.append(entry)
            continue
        entry.path = f"dowody/{folder}/{sha}.{ext}"
        entry.size = len(data)
        archive.add(entry.path, data, compress=compress)
        total += len(data)
        if artifact.kind in IMAGE_KINDS and len(thumbs) < MAX_THUMBS and (thumb := thumbnail(data)):
            thumbs[sha] = thumb
        entries.append(entry)
    return entries, thumbs


RAW_WARNING = (
    "UWAGA. Pliki w tym katalogu to surowa treść pobrana z infrastruktury oszustów: HTML stron i ruch sieciowy (HAR).\n"
    "Nie otwieraj ich w przeglądarce i nie uruchamiaj. Zawierają skrypty i adresy, które mogą szkodzić.\n"
    "HTML ma końcówkę .html.txt właśnie po to, żeby dwuklik otworzył edytor tekstu, a nie przeglądarkę.\n"
    "Pliki są dokładnie takie, jak w chwili przechwycenia (nazwa pliku to jego SHA-256), więc nie są redagowane\n"
    "i mogą zawierać tokeny dostępu oraz inne dane z przechwycenia. Nie przekazuj ich dalej poza postępowanie.\n"
)


@dataclass
class EdgePass:
    """Wynik jednego przejścia po krawędziach grupy: plik JSONL i dane do raportu."""

    count: int = 0
    rejected: int = 0
    by_relation: Counter = field(default_factory=Counter)
    top: list = field(default_factory=list)
    bottom: list = field(default_factory=list)
    aggregate: dict = field(default_factory=dict)


def write_edges(spec: GroupSpec, handle, paths: dict[str, str]) -> EdgePass:
    """Krawędzie grupy do JSONL i zbiorcze dowody do raportu, w jednym przejściu (bez trzymania wszystkich w pamięci).

    Odrzucone przez analityka krawędzie trafiają do pliku z werdyktem `rejected`, ale nie do raportu jako dowód."""
    result = EdgePass()
    queryset = (
        Edge.objects.filter(ad_a_id__in=spec.ad_ids, ad_b_id__in=spec.ad_ids, relation__in=spec.relations)
        .select_related("ad_a", "ad_b")
        .prefetch_related("evidence")
        .order_by("pk")
    )
    counter = 0
    for edge in queryset.iterator(chunk_size=500):
        evidence = list(edge.evidence.all())
        row = edge_row(edge)
        for item, ev in zip(row["evidence"], evidence, strict=True):
            item["raw_bits"] = round(ev.raw_bits, 2)
            item["artifact_a"] = ev.artifact_a_id or ""
            item["artifact_b"] = ev.artifact_b_id or ""
            item["artifact_a_file"] = paths.get(ev.artifact_a_id or "", "")
            item["artifact_b_file"] = paths.get(ev.artifact_b_id or "", "")
            item["value_a"], item["value_b"] = safe_text(ev.value_a, 500), safe_text(ev.value_b, 500)
        handle.write((json.dumps(row, ensure_ascii=False) + "\n").encode("utf-8"))
        result.count += 1
        result.by_relation[edge.relation] += 1
        if edge.verdict == Edge.Verdict.REJECTED:
            result.rejected += 1
            continue
        counter += 1
        heapq.heappush(result.top, (edge.probability, edge.bits, -edge.pk, counter, edge, evidence))
        if len(result.top) > TOP_EDGES:
            heapq.heappop(result.top)
        # Najsłabsze powiązania grupy: tu zarzut wspólnego źródła trzyma się najmniej.
        heapq.heappush(result.bottom, (-edge.probability, -edge.bits, edge.pk, counter, edge, evidence))
        if len(result.bottom) > WEAKEST_BOTTOM:
            heapq.heappop(result.bottom)
        for ev in evidence:
            key = (ev.kind, ev.value_a, ev.value_b)
            slot = result.aggregate.get(key)
            if slot is None:
                slot = result.aggregate[key] = {"best": ev, "edges": 0, "ads": set(), "probability": 0.0, "decisive": False}
            elif ev.weight_bits > slot["best"].weight_bits:
                slot["best"] = ev
            slot["edges"] += 1
            slot["ads"].update((edge.ad_a_id, edge.ad_b_id))
            slot["probability"] = max(slot["probability"], edge.probability)
            slot["decisive"] = slot["decisive"] or ev.decisive
    return result


def evidence_rows(aggregate: dict, names: dict[str, str], paths: dict[str, str]) -> list[dict]:
    ranked = sorted(aggregate.items(), key=lambda kv: (-kv[1]["best"].weight_bits, -len(kv[1]["ads"]), kv[0]))[:TOP_EVIDENCE]
    out = []
    for (kind, value_a, value_b), slot in ranked:
        best = slot["best"]
        known = KINDS.get(kind)
        shown = display_value(kind, value_a, names) if value_a else ""
        if value_b and value_b != value_a:
            shown = f"{shown} / {display_value(kind, value_b, names)}" if shown else display_value(kind, value_b, names)
        note = ""
        if known and known.motif:
            note = KIND_NOTES["motif"]
        elif known and known.kit:
            note = KIND_NOTES["kit"]
        out.append({
            "family": FAMILIES.get(best.family, best.family),
            "label": known.label if known else kind,
            "value": safe_text(shown) or "(podobieństwo treści)",
            "similarity": pl(best.similarity * 100, 0) if known and known.soft else "",
            "bits": pl(best.weight_bits),
            "probability": pl(slot["probability"] * 100) + "%",
            "pairs": slot["edges"],
            "ads": len(slot["ads"]),
            "df": best.df,
            "corpus_n": best.corpus_n,
            "decisive": slot["decisive"],
            "note": note,
            "files": [paths[a] for a in (best.artifact_a_id, best.artifact_b_id) if a and a in paths],
        })
    return out


def top_edge_rows(top: list, names: dict[str, str], paths: dict[str, str]) -> list[dict]:
    out = []
    for _p, _b, _n, _c, edge, evidence in sorted(top, key=lambda t: (-t[0], -t[1], -t[2])):
        rows = []
        for ev in evidence[:12]:
            known = KINDS.get(ev.kind)
            shown = display_value(ev.kind, ev.value_a, names)
            if ev.value_b and ev.value_b != ev.value_a:
                shown = f"{shown} / {display_value(ev.kind, ev.value_b, names)}"
            rows.append({
                "label": known.label if known else ev.kind,
                "family": FAMILIES.get(ev.family, ev.family),
                "value": safe_text(shown) or "(podobieństwo treści)",
                "bits": pl(ev.weight_bits),
                "df": ev.df,
                "corpus_n": ev.corpus_n,
                "decisive": ev.decisive,
                "files": [paths[a] for a in (ev.artifact_a_id, ev.artifact_b_id) if a and a in paths],
            })
        out.append({
            "id": edge.pk,
            "ad_a": edge.ad_a_id, "ad_b": edge.ad_b_id,
            "ext_a": clip(edge.ad_a.external_id, 60), "ext_b": clip(edge.ad_b.external_id, 60),
            "relation": RELATION_LABELS.get(edge.relation, edge.relation),
            "probability": pl(edge.probability * 100) + "%",
            "bits": pl(edge.bits),
            "verdict": VERDICT_LABELS.get(edge.verdict, "bez decyzji analityka"),
            "model_version": edge.model_version,
            "evidence": rows,
            "more": max(0, len(evidence) - 12),
        })
    return out


def weakest_rows(top: list, bottom: list) -> list[dict]:
    """Test najsłabszego ogniwa dla najmocniejszych par grupy i dla jej najsłabszych powiązań. To symulacja utraty śladów,
    nie wniosek o spójności grupy."""
    strongest = sorted(top, key=lambda t: (-t[0], -t[1], -t[2]))[:WEAKEST_EDGES]
    taken = {t[4].pk for t in strongest}
    weakest_pairs = [t for t in sorted(bottom, key=lambda t: (-t[0], -t[1], t[2])) if t[4].pk not in taken][:WEAKEST_BOTTOM]
    out = []
    for role, picks in (("jedna z najmocniejszych par", strongest), ("jedno z najsłabszych powiązań grupy", weakest_pairs)):
        out += weakest_for(role, picks)
    return out


def weakest_for(role: str, picks: list) -> list[dict]:
    out = []
    for _p, _b, _n, _c, edge, _ev in picks:
        try:
            result = weakest.weakest_link(edge, max_scenarios=WEAKEST_SCENARIOS, time_limit_ms=WEAKEST_TIME_MS)
        except simulation.SimulationError:
            continue
        searched = result["searched"]
        out.append({
            "edge": edge.pk,
            "role": role,
            "pair": f"#{edge.ad_a_id} i #{edge.ad_b_id}",
            "baseline": {
                "relation": result["baseline"]["relation_label"],
                "probability": pl(result["baseline"]["probability"] * 100) + "%",
                "bits": pl(result["baseline"]["bits"]),
            },
            "message": result["message"],
            "complete": searched["complete"],
            "checked": searched["scenarios_checked"],
            "solutions": [
                {
                    "labels": s["labels"],
                    "change": s["change"],
                    "probability": pl(s["simulated"]["probability"] * 100) + "%",
                    "bits": pl(s["simulated"]["bits"]),
                }
                for s in result["solutions"][:3]
            ],
            "more": max(0, len(result["solutions"]) - 3),
        })
    return out


def summary_data(spec: GroupSpec, ads: list[Ad], seen: dict, names: dict[str, str]) -> dict:
    ad_ids = [a.pk for a in ads]
    markers = AdMarker.objects.filter(ad_id__in=ad_ids, marker__kind__in=("domain", *PERSON_KINDS)).values_list("ad_id", "marker__kind", "marker__value")
    domains: dict[str, set[int]] = {}
    people: dict[tuple[str, str], set[int]] = {}
    for ad_id, kind, value in markers:
        if kind == "domain":
            domains.setdefault(value, set()).add(ad_id)
        else:
            people.setdefault((kind, display_value(kind, value, names)), set()).add(ad_id)
    records = {r.domain: r for r in DomainRecord.objects.filter(domain__in=domains)}
    listed = {w.domain: w for w in WarningDomain.objects.filter(domain__in=domains)}
    domain_rows = []
    for domain, ad_set in sorted(domains.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        record, warn = records.get(domain), listed.get(domain)
        domain_rows.append({
            "domain": safe_text(domain, 120),
            "ads": len(ad_set),
            "registered": record.registered_at.date().isoformat() if record and record.registered_at else "",
            "cert_pl": ("na liście od " + warn.added_at.date().isoformat() if warn.added_at else "na liście") if warn else "",
        })
    advertisers: Counter = Counter()
    for ad in ads:
        raw = ad.raw if isinstance(ad.raw, dict) else {}
        name = ad.advertiser.name if ad.advertiser and ad.advertiser.name else raw.get("advertiser_name", "")
        if name:
            advertisers[(clip(name, 120), clip(ad.advertiser.payer, 120) if ad.advertiser else "")] += 1
    kind_label = {"person_mention": "wzmianka o osobie", "face_match": "twarz z bazy referencyjnej", "brand_impersonated": "podszycie pod markę"}
    people_rows = [
        {"name": safe_text(name, 120), "how": kind_label[kind], "ads": len(ad_set)}
        for (kind, name), ad_set in sorted(people.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    ]
    dated = [seen[a.pk].at for a in ads if a.pk in seen]
    campaigns = Counter(a.membership.campaign.key for a in ads if hasattr(a, "membership"))
    return {
        "ads": len(ads),
        "sources": [{"label": SOURCE_LABELS.get(code, code), "n": n} for code, n in Counter(str(a.source) for a in ads).most_common()],
        "cases": len({a.labels.get("case") for a in ads if a.labels.get("case")}),
        "campaigns": [{"key": k, "ads": n} for k, n in sorted(campaigns.items())],
        "period_from": min(dated).astimezone(UTC).date().isoformat() if dated else "",
        "period_to": max(dated).astimezone(UTC).date().isoformat() if dated else "",
        "dated": len(dated),
        "undated": len(ads) - len(dated),
        "domains_total": len(domain_rows),
        "domains": domain_rows[:25],
        "advertisers": [{"name": n, "payer": p, "ads": c} for (n, p), c in advertisers.most_common(15)],
        "people": people_rows[:20],
        "cert_pl": sum(1 for a in ads if "cert_pl" in a.labels),
    }


def timeline_rows(events: list[dict]) -> list[dict]:
    time_kind = {"observed": "zaobserwowano", "reported": "podane przez źródło"}
    rows = []
    for e in events:
        detail = e["detail"]
        bits = []
        if e["type"] == "link_observable":
            bits.append(f"{detail.get('count', 0)} powiązań z wcześniejszymi reklamami")
        elif e["type"] == "trace_first_observed":
            bits.append(f"{detail.get('kind_label', '')}, w grupie: {detail.get('in_group', '')} reklam")
        elif e["type"] == "cert_issued":
            bits.append(f"wystawca: {detail.get('issuer', '') or 'brak danych'}; wystawień: {detail.get('count', 1)}")
        elif e["type"] == "domain_registered" and detail.get("registrar"):
            bits.append(f"rejestrator: {detail['registrar']}")
        value = safe_text(e["value"], 90) if e["type"] != "link_observable" else ""
        rows.append({
            "at": e["at"][:16].replace("T", " ") + (" UTC" if "T" in e["at"] else ""),
            "label": e["label"],
            "value": value,
            "detail": clip("; ".join(bits), 140),
            "time_kind": time_kind.get(e["time_kind"], e["time_kind"]),
            "source": e["source"],
            "precision": "dzień" if e["precision"] == "day" else "",
            "ads": ", ".join(f"#{a}" for a in e["ads"][:4]) + (" …" if len(e["ads"]) > 4 else ""),
        })
    return rows


def ad_rows(ads: list[Ad], seen: dict, ad_files: dict[int, list[Entry]], thumbs: dict[str, str]) -> list[dict]:
    out = []
    for ad in ads[:MAX_AD_ROWS]:
        raw = ad.raw if isinstance(ad.raw, dict) else {}
        advertiser = ad.advertiser.name if ad.advertiser and ad.advertiser.name else raw.get("advertiser_name", "")
        files = ad_files.get(ad.pk, [])
        out.append({
            "id": ad.pk,
            "external_id": clip(ad.external_id, 80),
            "source": SOURCE_LABELS.get(str(ad.source), str(ad.source)),
            "title": clip(ad.title or ad.text, 100),
            "url": clip(redact_url(ad.landing_url), 140) if ad.landing_url else "",
            "campaign": ad.membership.campaign.key if hasattr(ad, "membership") else "",
            "first_seen": seen[ad.pk].at.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC") if ad.pk in seen else "brak daty",
            "advertiser": clip(advertiser, 80),
            "files": [{"role": ROLE_LABELS.get(e.roles[0], e.roles[0]), "sha": e.sha256[:12], "stored": bool(e.path)} for e in files],
        })
    return out


def gallery(ads: list[Ad], ad_files: dict[int, list[Entry]], thumbs: dict[str, str], entries: list[Entry]) -> tuple[list[dict], int]:
    by_sha = {e.sha256: e for e in entries}
    out, shown = [], set()
    for ad in ads:
        for entry in ad_files.get(ad.pk, []):
            if entry.kind not in IMAGE_KINDS or entry.sha256 in shown or not entry.path:
                continue
            shown.add(entry.sha256)
            e = by_sha[entry.sha256]
            out.append({
                "sha": e.sha256, "path": e.path, "role": ROLE_LABELS.get(e.kind, e.kind),
                "ads": ", ".join(f"#{a}" for a in e.ads[:5]) + (" …" if len(e.ads) > 5 else ""),
                "acquired": e.acquired_at, "size": human_size(e.size), "thumb": thumbs.get(e.sha256, ""),
                "source": clip(e.source_url, 120),
            })
    images_total = len(out)
    return [g for g in out if g["thumb"]], images_total


def build(kind: str, obj, include_raw: bool = True) -> Package:
    """Buduje pakiet grupy. Zwraca plik tymczasowy ZIP; wołający zamyka go po wysłaniu."""
    spec = spec_for(kind, obj)
    if not spec.ad_ids:
        raise GroupNotFound(spec.key)
    now = datetime.now(UTC)
    root = f"scamdna-pakiet-{spec.key}-{now:%Y%m%d}"
    ads = list(
        Ad.objects.filter(pk__in=spec.ad_ids)
        .select_related("advertiser", "membership__campaign", "operator_membership__operator")
        .order_by(F("first_seen").asc(nulls_last=True), "id")
    )
    states = latest_states(spec.ad_ids)
    names = person_names()
    seen = {ad.pk: s for ad in ads if (s := timeline.ad_seen(ad))}

    target = tempfile.TemporaryFile()
    archive = Archive(target, root)
    try:
        refs = collect_refs(ads, states, edge_artifact_refs(spec))
        entries, thumbs = write_evidence(archive, refs, include_raw)
        paths = {e.sha256: e.path for e in entries if e.path}
        if any(e.path.startswith("dowody/surowe/") for e in entries):
            archive.add("dowody/surowe/OSTRZEZENIE.txt", RAW_WARNING.encode("utf-8"))

        with tempfile.TemporaryFile() as edge_file:
            edges = write_edges(spec, edge_file, paths)
            edge_file.seek(0)
            archive.add_file("krawedzie.jsonl", edge_file)

        line = timeline.build(spec.ad_ids, spec.relations)
        archive.add("os-czasu.json", json.dumps({"group": spec.key, **line}, ensure_ascii=False, indent=1).encode("utf-8"))
        stix_args = {"operator_id": obj.pk} if kind == "operator" else {"campaign_id": obj.pk}
        stix_bundle = stix.bundle(**stix_args)
        archive.add("stix.json", json.dumps(stix_bundle, ensure_ascii=False, indent=1).encode("utf-8"))
        archive.add("weryfikuj.py", VERIFY_SCRIPT.read_bytes())

        ad_files: dict[int, list[Entry]] = {}
        for entry in entries:
            for ad_id in entry.ads:
                ad_files.setdefault(ad_id, []).append(entry)
        images, images_total = gallery(ads, ad_files, thumbs, entries)
        stored = [e for e in entries if e.path]
        skipped = [e for e in entries if not e.path]
        top_edges = top_edge_rows(edges.top, names, paths)
        context = {
            "kind": kind,
            "kind_word": "operatora" if kind == "operator" else "kampanii",
            "key": spec.key,
            "generated": now.strftime("%Y-%m-%d %H:%M UTC"),
            "model_version": fusion.model_version(),
            "summary": summary_data(spec, ads, seen, names),
            "evidence": evidence_rows(edges.aggregate, names, paths),
            "edges_count": edges.count,
            "edges_rejected": edges.rejected,
            "top_edges": top_edges,
            "weakest": weakest_rows(edges.top, edges.bottom),
            "timeline": timeline_rows(line["events"][:MAX_TIMELINE_ROWS]),
            "timeline_total": len(line["events"]),
            "timeline_undated": line["undated"],
            "ads": ad_rows(ads, seen, ad_files, thumbs),
            "ads_total": len(ads),
            "images": images,
            "images_total": images_total,
            "files_total": len(stored),
            "files_size": human_size(sum(e.size for e in stored)),
            "skipped": [{"sha": e.sha256, "role": ROLE_LABELS.get(e.kind, e.kind), "reason": e.skipped} for e in skipped],
            "root": root,
            "include_raw": include_raw,
            "stix_objects": len(stix_bundle["objects"]),
            "relation_counts": [{"label": RELATION_LABELS.get(r, r), "n": n} for r, n in edges.by_relation.most_common()],
        }
        archive.add("raport.html", render_report(context).encode("utf-8"))

        external = {ad.pk: ad.external_id for ad in ads}
        manifest = {
            "format": FORMAT_VERSION,
            "system": "SCAM DNA",
            "wygenerowano": now.isoformat(timespec="seconds"),
            "grupa": {"typ": kind, "klucz": spec.key, "id": obj.pk, "reklam": len(ads)},
            "model": fusion.model_version(),
            "opis": (
                "Pliki w dowody/ są kopiami artefaktów bajt w bajt. Nazwa pliku to jego SHA-256. czas_pozyskania to chwila zapisu "
                "artefaktu w systemie SCAM DNA, nie moment, w którym oszust opublikował materiał. Adresy w źródle po redakcji tokenów."
            ),
            "pliki": [
                {
                    "sciezka": e.path, "sha256": e.sha256, "rozmiar": e.size, "rodzaj": e.kind, "typ_mime": e.content_type,
                    "zrodlo": e.source_url, "czas_pozyskania": e.acquired_at,
                    "reklamy": [{"id": a, "external_id": external[a]} for a in e.ads],
                }
                for e in sorted(stored, key=lambda e: e.path)
            ],
            "pliki_pakietu": [
                {"sciezka": p, "sha256": archive.sums[p], "rozmiar": archive.sizes[p]}
                for p in sorted(archive.sums)
                if not p.startswith("dowody/")
            ],
            "pominiete": [{"sha256": e.sha256, "rodzaj": e.kind, "rozmiar": e.size, "powod": e.skipped} for e in skipped],
            "reklamy": [
                {
                    "id": ad.pk, "external_id": ad.external_id, "zrodlo": str(ad.source),
                    "adres": redact_url(ad.landing_url) if ad.landing_url else "",
                    "pierwsza_obserwacja": iso(seen[ad.pk].at) if ad.pk in seen else "",
                    "rodzaj_czasu": seen[ad.pk].time_kind if ad.pk in seen else "",
                }
                for ad in ads
            ],
        }
        archive.add("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=1).encode("utf-8"))
        sums = "".join(f"{archive.sums[p]}  {p}\n" for p in sorted(archive.sums))
        archive.zip.writestr(zipfile.ZipInfo(f"{root}/SHA256SUMS", date_time=now.timetuple()[:6]), sums.encode("utf-8"))
    except BaseException:
        archive.close()
        target.close()
        raise
    archive.close()
    size = target.seek(0, 2)
    target.seek(0)
    whole = hashlib.sha256()
    for chunk in iter(lambda: target.read(1 << 20), b""):
        whole.update(chunk)
    target.seek(0)
    return Package(target, f"{root}.zip", len(archive.sums) + 1, size, len(skipped), whole.hexdigest())


_engine = None


def render_report(context: dict) -> str:
    global _engine
    if _engine is None:
        _engine = Engine(dirs=[str(TEMPLATE_DIR)], autoescape=True)
    return _engine.get_template("raport.html").render(Context(context))

