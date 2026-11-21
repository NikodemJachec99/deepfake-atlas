"""Import przechwyceń: zapisane strony (HTML z katalogiem zasobów), pliki HAR, zrzuty z narzędzia
`page-capture`, zrzuty ekranu reklam i metadane yt-dlp.

Format pochodzi z paczki organizatora: jeden katalog to jedna sprawa. W sprawie może być kilka stron
(osobne podkatalogi albo kilka HAR-ów) i materiały reklamy wspólne dla całej sprawy.

Każda strona staje się reklamą ze źródłem `capture`. Analiza działa bez sieci: niczego nie pobieramy
z infrastruktury oszustów, bo dowody są już w plikach.
"""

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from django.utils import timezone

from ads.models import Analysis, Source
from ads.services import upsert_ad
from collectors.observation import observation_info
from evidence import store
from extractors import images, ocr
from extractors import video as video_meta
from extractors.har import image_blobs, is_cloudflare, parse_har
from extractors.url import host_of, redact_url, registered_domain
from people import faces
from people.models import Person

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
VIDEO_EXT = {".mp4", ".mov", ".webm", ".mkv"}
MAX_UPLOAD_ARTIFACT = 60 * 1024 * 1024
_SAVED_FROM = re.compile(rb"<!--\s*saved from url=\(\d+\)(\S+)\s*-->")
_SLUG = re.compile(r"[^a-z0-9.]+")


@dataclass
class PageCapture:
    slug: str
    url: str = ""
    html: bytes = b""
    har: dict | None = None
    har_bytes: bytes = b""
    captured_at: str = ""
    time_source: str = ""  # skąd wiemy, kiedy przechwycono: har.pages, har.entries, nask.archive_info, page-capture.manifest
    sources: list[str] = field(default_factory=list)
    observations: list[list] = field(default_factory=list)
    asset_dirs: list[Path] = field(default_factory=list)


@dataclass
class CaseCapture:
    case: str
    pages: list[PageCapture] = field(default_factory=list)
    creatives: list[Path] = field(default_factory=list)
    videos: list[Path] = field(default_factory=list)
    infos: list[dict] = field(default_factory=list)


def _slug(text: str) -> str:
    return _SLUG.sub("-", text.lower()).strip("-")[:60] or "strona"


def _domain(url: str) -> str:
    return registered_domain(host_of(url)) if url.startswith("http") else ""


def _read_saved_html(path: Path) -> tuple[str, bytes]:
    body = path.read_bytes()
    match = _SAVED_FROM.search(body[:4096])
    url = match.group(1).decode("utf-8", errors="replace") if match else ""
    return (url if url.startswith("http") else ""), body


def _capture_manifest(directory: Path) -> Path | None:
    """Katalog z narzędzia page-capture ma manifest.json z polem page_url, czasem zagnieżdżony o poziom."""
    for candidate in [directory / "manifest.json", *directory.glob("*/manifest.json")]:
        if not candidate.is_file():
            continue
        try:
            if "page_url" in json.loads(candidate.read_text(encoding="utf-8", errors="replace")):
                return candidate
        except ValueError:
            continue
    return None


def _read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _local_file_har(data: dict) -> bool:
    """HAR nagrany po otwarciu zapisanej strony z dysku: adres strony zaczyna się od file:."""
    pages = data.get("log", {}).get("pages") or []
    title = str(pages[0].get("title", "")) if pages else ""
    return title.lower().startswith("file:")


def _merge_nask_archive(directory: Path, page_for) -> None:
    """Archiwum z narzędzia NASK: `archive_info.json`, `dns_ssl.json`, `network.har`, `html/rendered.html`.

    Bywa robione po czasie, gdy strona już nie działa, więc tylko uzupełnia to, czego nie ma
    w zapisie z przeglądarki. Adres IP i certyfikat z chwili archiwizacji bierzemy zawsze.
    """
    info = _read_json(directory / "archive_info.json")
    url = info.get("url", "")
    page = page_for(_domain(url), directory.name, url, "archive")
    page.url = page.url or url
    if not page.captured_at and info.get("timestamp_utc"):
        page.captured_at, page.time_source = info["timestamp_utc"], "nask.archive_info"
    har_path = directory / "network.har"
    if page.har is None and har_path.is_file():
        try:
            page.har_bytes = har_path.read_bytes()
            page.har = json.loads(page.har_bytes.decode("utf-8", errors="replace"))
        except ValueError:
            page.har, page.har_bytes = None, b""
    rendered = directory / "html" / "rendered.html"
    if not page.html and rendered.is_file():
        page.html = rendered.read_bytes()

    dns = _read_json(directory / "dns_ssl.json")
    for ip in dns.get("all_addresses") or ([dns["ip"]] if dns.get("ip") else []):
        page.observations.append(["cdn", "cloudflare", {}] if is_cloudflare(ip) else ["ip", ip, {"from": "dns_ssl.json"}])
    serial = (dns.get("ssl") or {}).get("serialNumber")
    if serial:
        page.observations.append(["tls_serial", serial.lower(), {"not_before": (dns.get("ssl") or {}).get("notBefore", "")}])
    page.sources.append(f"{directory.name}/ (archiwum NASK)")


def discover(case_dir: Path, case: str | None = None) -> CaseCapture:
    capture = CaseCapture(case=case or case_dir.name)
    used: set[str] = set()

    def unique(slug: str) -> str:
        base, n = slug, 2
        while slug in used:
            slug, n = f"{base}-{n}", n + 1
        used.add(slug)
        return slug

    def scan(directory: Path, prefix: str) -> None:
        local: dict[str, list[PageCapture]] = {}

        def page_for(domain: str, fallback: str, url: str = "", slot: str = "") -> PageCapture:
            """Strona dla tej domeny. Zapis HTML i HAR tej samej strony łączymy w jedną, ale drugi HAR albo
            drugi HTML z innym adresem to osobne przechwycenie i osobna strona, żeby nie zgubić wariantu."""
            key = domain or f"?{fallback}"
            for page in local.get(key, []):
                if slot not in ("har", "html"):
                    return page  # archiwum i page-capture uzupełniają zapis tej samej domeny, także robione później
                taken = (slot == "har" and page.har is not None) or (slot == "html" and bool(page.html))
                if not taken and (not url or not page.url or page.url == url):
                    return page
            page = PageCapture(slug=unique(_slug(prefix + (domain or fallback))))
            local.setdefault(key, []).append(page)
            return page

        for item in sorted(directory.iterdir()):
            suffix = item.suffix.lower()
            if item.is_file() and suffix in (".html", ".htm"):
                url, body = _read_saved_html(item)
                page = page_for(_domain(url), item.stem, url, "html")
                page.url = page.url or url
                page.html = body
                page.sources.append(item.name)
                assets = item.with_name(f"{item.stem}_files")
                if assets.is_dir():
                    page.asset_dirs.append(assets)
            elif item.is_file() and (suffix == ".har" or item.name.lower() == ".har"):  # plik bywa nazwany samym ".har"
                raw = item.read_bytes()
                try:
                    data = json.loads(raw.decode("utf-8", errors="replace"))
                    summary = parse_har(data)
                except (ValueError, KeyError):
                    continue
                if _local_file_har(data):
                    continue  # zapis otwarcia pliku z dysku, nie ruch strony w sieci
                page = page_for(_domain(summary.page_url), item.stem or "har", summary.page_url, "har")
                page.har, page.har_bytes = data, raw
                page.url = summary.page_url or page.url
                page.captured_at = summary.started_at
                page.time_source = "har.entries" if summary.started_at else ""
                page.sources.append(item.name)
            elif item.is_file() and suffix in IMAGE_EXT:
                capture.creatives.append(item)
            elif item.is_file() and suffix in VIDEO_EXT:
                capture.videos.append(item)
            elif item.is_file() and item.name.endswith(".info.json"):
                try:
                    info = json.loads(item.read_text(encoding="utf-8", errors="replace"))
                except ValueError:
                    continue
                if isinstance(info, dict):
                    info["_file"] = item.name  # łączymy z plikiem nagrania po nazwie
                    capture.infos.append(info)

        for sub in sorted(p for p in directory.iterdir() if p.is_dir() and not p.name.endswith("_files")):
            manifest_path = _capture_manifest(sub)
            if manifest_path:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8", errors="replace"))
                root = manifest_path.parent
                page = page_for(_domain(manifest.get("page_url", "")), sub.name, manifest.get("page_url", ""), "capture")
                page.url = page.url or manifest.get("page_url", "")
                if not page.captured_at and manifest.get("captured_at"):
                    page.captured_at, page.time_source = manifest["captured_at"], "page-capture.manifest"
                har_path, dom_path = root / "page.har", root / "dom.html"
                if har_path.is_file() and page.har is None:
                    page.har_bytes = har_path.read_bytes()
                    page.har = json.loads(page.har_bytes.decode("utf-8", errors="replace"))
                if dom_path.is_file() and not page.html:
                    page.html = dom_path.read_bytes()
                page.sources.append(f"{sub.name}/ (page-capture)")
            elif (sub / "archive_info.json").is_file():
                _merge_nask_archive(sub, page_for)
            elif any(f.suffix.lower() in (".html", ".htm", ".har") for f in sub.iterdir() if f.is_file()):
                scan(sub, f"{sub.name}-")

        capture.pages.extend(page for pages in local.values() for page in pages)

    scan(case_dir, "")
    return capture


def _first_seen(value: str):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else timezone.make_aware(parsed)


def describe_video(path: Path, entry: dict, infos: list[dict]) -> dict:
    """Metadane nagrania, klatka poglądowa w magazynie i długość oryginału z metadanych pobrania, jeśli jest."""
    probed = video_meta.probe(str(path))
    poster = None
    if probed and probed.poster_jpeg:
        poster = store.put(probed.poster_jpeg, kind="video_frame", content_type="image/jpeg", source_url=f"{path.name}#t={probed.poster_at_s}").sha256
    info = next((i for i in infos if i.get("_file", "").removesuffix(".info.json") == path.stem), None)
    duration = info.get("duration") if info else None
    original = float(duration) if isinstance(duration, int | float) and not isinstance(duration, bool) and duration > 0 else None
    described = video_meta.describe(entry, probed, poster, original)
    if not entry["stored"]:
        described.setdefault("missing", []).append(f"plik ma {entry['size'] // (1024 * 1024)} MB, ponad limit magazynu, więc nie da się go odtworzyć")
    return described


def analyze_video(path: Path) -> tuple[list[int], str, list[list], str]:
    """Treść nagrania z kilku klatek: hasze percepcyjne, tekst z OCR i twarze z bazy referencyjnej.

    Hasze trafiają do miękkiego markera `video_frames`, tekst do tekstu reklamy (adresy po redakcji),
    a z twarzy zostaje najlepsze trafienie dla każdej osoby. Brak OpenCV albo nieczytelny plik: puste wyniki.
    """
    hashes: list[int] = []
    lines: list[str] = []
    best: dict[str, tuple[float, dict]] = {}
    for frame in video_meta.sample_frames(str(path)):
        value = images.dhash(frame.jpeg)
        if value is not None and not any(images.distance(value, seen) <= images.MAX_DISTANCE for seen in hashes):
            hashes.append(value)
        for line in ocr.read_bytes(frame.jpeg):
            if line not in lines:
                lines.append(line)
        for face in faces.match_faces(frame.jpeg):
            if face.name not in best or face.score > best[face.name][0]:
                best[face.name] = (face.score, {"file": path.name, "at_s": frame.at_s, "name": face.name, "score": face.score, "box": list(face.box)})
    text = " ".join(redact_url(word) if word.startswith(("http://", "https://")) else word for word in " ".join(lines).split())
    # Nagranie ekranu z kanału albo z biblioteki reklam ma ten sam układ co zrzut: reklamodawca, "Sponsorowane", numer biblioteki.
    shot = ocr.parse_ad_screenshot(lines)
    observations = [[o.kind, o.value, {**o.detail, "file": path.name, "from": "klatki nagrania"}] for o in shot.observations]
    for name, (_score, detail) in best.items():
        person = Person.objects.filter(name=name).first() or Person.objects.create(name=name)
        observations.append(["face_match", person.marker_value, detail])
    return hashes, text, observations, shot.advertiser


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def import_case(case_dir: Path, bundle: str = "upload", case: str | None = None) -> list[Analysis]:
    """Zapisuje sprawę do bazy i zwraca analizy gotowe do uruchomienia (jedna na stronę)."""
    capture = discover(Path(case_dir), case)

    creative_obs: list[list] = []
    creative_shas: list[str] = []
    ocr_texts: list[str] = []
    advertiser = ""
    for image in capture.creatives:
        artifact = store.put(image.read_bytes(), kind="creative_image", source_url=image.name)
        creative_shas.append(artifact.sha256)
        phash = images.dhash(image.read_bytes())
        if phash is not None:
            creative_obs.append(["creative_phash", images.to_hex(phash), {"file": image.name, "artifact": artifact.sha256}])
        shot = ocr.parse_ad_screenshot(ocr.read_image(str(image)))
        advertiser = advertiser or shot.advertiser
        if shot.text:
            ocr_texts.append(shot.text)
        creative_obs += [[o.kind, o.value, {**o.detail, "artifact": artifact.sha256}] for o in shot.observations]
        for face in faces.match_faces(image.read_bytes()):
            person = Person.objects.filter(name=face.name).first() or Person.objects.create(name=face.name)
            detail = {"file": image.name, "artifact": artifact.sha256, "name": face.name, "score": face.score, "box": list(face.box)}
            creative_obs.append(["face_match", person.marker_value, detail])

    video_files = []
    video_hashes: list[int] = []
    for item in capture.videos:
        size = item.stat().st_size
        entry = {"name": item.name, "size": size, "sha256": _file_sha256(item), "stored": size <= MAX_UPLOAD_ARTIFACT}
        if entry["stored"]:
            store.put(item.read_bytes(), kind="creative_video", source_url=item.name)
        video_files.append(describe_video(item, entry, capture.infos))
        creative_obs.append(["creative_sha256", entry["sha256"], {"file": item.name}])
        frame_hashes, frame_text, frame_faces, frame_advertiser = analyze_video(item)
        advertiser = advertiser or frame_advertiser
        video_hashes += [h for h in frame_hashes if h not in video_hashes]
        if frame_text:
            ocr_texts.append(frame_text)
        creative_obs += frame_faces

    for info in capture.infos:
        library_id = str(info.get("playlist_id") or info.get("id") or "").split("_")[0]
        if library_id.isdigit():
            creative_obs.append(["meta_ad_ref", library_id, {"from": "metadane pobranego wideo"}])

    pages = capture.pages
    if not pages and (capture.creatives or capture.videos or capture.infos):
        # Sprawa bez strony docelowej: sama reklama, np. wideo z Biblioteki Reklam.
        pages = [PageCapture(slug="reklama")]

    analyses = []
    for page in pages:
        url = redact_url(page.url)
        state: dict = {"offline": True, "capture": {"observations": [*creative_obs, *page.observations], "sources": page.sources}}
        blobs = image_blobs(page.har) if page.har is not None else []
        for directory in page.asset_dirs:
            blobs += [f.read_bytes() for f in sorted(directory.iterdir()) if f.is_file() and f.suffix.lower() in IMAGE_EXT]
        state["capture"]["image_hashes"] = images.hash_set(blobs)
        state["capture"]["video_hashes"] = video_hashes
        if page.har is not None:
            summary = parse_har(page.har)
            har_artifact = store.put(page.har_bytes, kind="har", content_type="application/json", source_url=url)
            state["capture"]["har"] = har_artifact.sha256
            state["capture"]["observations"] += [[o.kind, o.value, o.detail] for o in summary.observations]
            chain = [{**hop, "url": redact_url(hop["url"])} for hop in summary.chain]
            html = page.html or summary.html.encode("utf-8")
        else:
            chain = [{"url": url, "status": 200, "via": "http"}] if url else []
            html = page.html
        html_sha = None
        if html:
            html_sha = store.put(html, kind="html_victim", content_type="text/html", source_url=url).sha256
        state["pages"] = {"victim": {"final_url": url, "status": 200 if html else 0, "error": "", "chain": chain, "html_sha": html_sha}}

        info = capture.infos[0] if capture.infos else {}
        ad, _ = upsert_ad(
            Source.CAPTURE,
            f"{bundle}/{capture.case}/{page.slug}",
            raw={
                "case": capture.case,
                "bundle": bundle,
                "sources": page.sources,
                "creatives": creative_shas,
                "videos": video_files,
                "advertiser_name": advertiser,
                "library_url": info.get("webpage_url", ""),
                "observation": observation_info(page.url, page.captured_at, page.time_source, page.har),
            },
            landing_url=url,
            text=" ".join(ocr_texts),
            title=info.get("title", "") if not page.url else "",
            first_seen=_first_seen(page.captured_at),
        )
        ad.labels["case"] = capture.case
        ad.labels["bundle"] = bundle
        ad.save(update_fields=["labels"])
        analyses.append(Analysis.objects.create(ad=ad, input_kind=Analysis.Kind.AD, input_value=ad.external_id, state=state))
    return analyses


def case_dirs(root: Path) -> list[Path]:
    """Katalogi spraw w paczce. Paczka organizatora ma je o poziom niżej, w `do_udostępnienia/`."""
    root = Path(root)
    subdirs = [p for p in root.iterdir() if p.is_dir()]
    if len(subdirs) == 1 and not any(p.is_file() for p in root.iterdir()):
        return case_dirs(subdirs[0])
    has_material = any(p.is_file() and p.suffix.lower() in (".html", ".htm", ".har", *IMAGE_EXT, *VIDEO_EXT) for p in root.iterdir())
    if has_material:
        return [root]
    return sorted(subdirs, key=lambda p: (0, int(p.name)) if p.name.isdigit() else (1, p.name))
