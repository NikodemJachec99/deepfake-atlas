"""Potok analizy jednej reklamy.

Każdy etap czyta stan z bazy i zapisuje wynik do bazy, więc Temporal może ponowić dowolny
z nich osobno. Ten sam kod wykonuje runner lokalny (wątek) i testy (synchronicznie).
Etapy zapisują zdarzenia postępu, które interfejs odtwarza przez SSE.

Dwa tryby wejścia:
- na żywo: adres albo tekst, stronę pobiera crawler,
- z przechwycenia (`state["offline"]`): HTML i HAR są już w magazynie dowodów, niczego nie pobieramy.
"""

import base64
import json
from collections.abc import Callable

import mmh3
from django.conf import settings
from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from django.utils.module_loading import import_string

from ads.models import Ad, Analysis, AnalysisEvent, Source
from enrichment import crtsh
from enrichment.models import DomainRecord, WarningDomain
from evidence import services as markers
from evidence import store
from evidence.kinds import FAMILIES, KINDS
from evidence.models import Artifact
from extractors import Observation, embedding, images
from extractors.har import image_blobs, parse_har
from extractors.html import extract_page
from extractors.keywords import keywords, topics
from extractors.text import extract_text
from extractors.url import host_of, redact_url, registered_domain, url_observations
from people.matching import find_people
from people.models import Person
from similarity import alerts as alerting
from similarity import service as linking
from similarity.models import CampaignMembership, Edge, OperatorMembership

STAGES = ["ingest", "crawl", "extract", "enrich", "fuse", "cluster"]
STAGE_LABELS = {
    "ingest": "Przyjęcie materiału",
    "crawl": "Pobranie strony i łańcucha przekierowań",
    "extract": "Ekstrakcja markerów",
    "enrich": "Wzbogacanie infrastruktury",
    "fuse": "Szukanie powiązań",
    "cluster": "Przypisanie do kampanii i operatora",
}


def fetcher():
    return import_string(settings.CRAWLER_FETCHER)()


def enricher():
    return import_string(settings.ENRICHER)()


def emit(analysis: Analysis, stage: str, status: str, message: str = "", payload: dict | None = None) -> AnalysisEvent:
    with transaction.atomic():
        Analysis.objects.select_for_update().get(pk=analysis.pk)
        last = analysis.events.aggregate(m=Max("seq"))["m"] or 0
        return AnalysisEvent.objects.create(
            analysis=analysis, seq=last + 1, stage=stage, status=status, message=message, payload=payload or {}
        )


# --- etapy -----------------------------------------------------------------


def stage_ingest(analysis: Analysis) -> dict:
    if analysis.ad_id:
        return {"ad": analysis.ad_id, "created": False, "source": analysis.ad.source}
    value = analysis.input_value.strip()
    now = timezone.now()
    if analysis.input_kind == Analysis.Kind.URL:
        ad = Ad.objects.create(source=Source.MANUAL, landing_url=redact_url(value), first_seen=now, last_seen=now)
    else:
        ad = Ad.objects.create(source=Source.MANUAL, text=value, first_seen=now, last_seen=now)
    analysis.ad = ad
    analysis.save(update_fields=["ad"])
    return {"ad": ad.pk, "created": True, "source": ad.source}


def stage_crawl(analysis: Analysis) -> dict:
    ad = analysis.ad
    if analysis.state.get("offline"):
        page = (analysis.state.get("pages") or {}).get("victim") or {}
        emit(
            analysis, "crawl", "info", "Materiał z przechwycenia: strona i ruch sieciowy są już w dowodach",
            {"profile": "capture", "chain": page.get("chain", []), "final_url": page.get("final_url", "")},
        )
        return {"pages": 1 if page.get("html_sha") else 0, "offline": True}
    if not ad.landing_url:
        # Lead Ads i zgłoszenia samym tekstem: nie ma strony, łączymy po pozostałych rodzinach.
        emit(analysis, "crawl", "info", "Brak adresu docelowego, pomijam pobieranie strony")
        return {"pages": 0}
    client = fetcher()
    pages = {}
    for profile in ("victim", "bot"):
        result = client.fetch(ad.landing_url, profile)
        page = {
            "final_url": redact_url(result.final_url),
            "status": result.status,
            "error": result.error,
            "chain": [{"url": redact_url(h.url), "status": h.status, "via": h.via} for h in result.chain],
            "html_sha": None,
        }
        page["engine"] = result.engine
        page["screenshot_sha"] = None
        if result.body:
            artifact = store.put(result.body, kind=f"html_{profile}", content_type=result.content_type, source_url=page["final_url"])
            page["html_sha"] = artifact.sha256
        if result.screenshot:
            # Zrzut wyrenderowanej strony. Pokazujemy obraz, nigdy HTML oszusta.
            shot = store.put(result.screenshot, kind="page_screenshot", content_type="image/png", source_url=page["final_url"])
            page["screenshot_sha"] = shot.sha256
        if result.har and profile == "victim":
            # Ruch sieciowy z przeglądarki trafia tam, gdzie HAR z przechwycenia: te same ekstraktory w etapie extract.
            capture = analysis.state.setdefault("capture", {})
            har_artifact = store.put(json.dumps(result.har).encode("utf-8"), kind="har", content_type="application/json", source_url=page["final_url"])
            capture["har"] = har_artifact.sha256
            found = [*capture.get("observations", []), *([o.kind, o.value, o.detail] for o in parse_har(result.har).observations)]
            # Ponowne uruchomienie etapu nie dubluje śladów.
            capture["observations"] = list({json.dumps(o, sort_keys=True): o for o in found}.values())
            capture["image_hashes"] = images.hash_set(image_blobs(result.har))
        pages[profile] = page
        js_hops = sum(1 for h in result.chain if h.via == "js")
        emit(
            analysis, "crawl", "info",
            f"Profil {profile} ({'przeglądarka' if result.engine == 'browser' else 'HTTP'}): {len(result.chain)} skoków"
            + (f", w tym {js_hops} skryptem" if js_hops else "")
            + f", status {result.status or 'brak'}"
            + (f", błąd: {result.error}" if result.error else ""),
            {
                "profile": profile,
                "engine": result.engine,
                "chain": page["chain"],
                "final_url": page["final_url"],
                "screenshot": page["screenshot_sha"],
                "har": bool(result.har),
                "notes": [redact_url(n) if n.startswith("http") else n for n in result.notes][:20],
            },
        )
    analysis.state["pages"] = pages
    analysis.save(update_fields=["state"])
    return {"pages": sum(1 for p in pages.values() if p["html_sha"])}


def stage_extract(analysis: Analysis) -> dict:
    ad = analysis.ad
    pages = analysis.state.get("pages", {})
    victim = pages.get("victim") or {}
    capture = analysis.state.get("capture") or {}
    counts: dict[str, int] = {}

    def add(observations: list[Observation], artifact=None) -> None:
        markers.attach(ad, observations, artifact)
        for obs in dict.fromkeys(observations):
            family = KINDS[obs.kind].family
            counts[family] = counts.get(family, 0) + 1

    final_url = victim.get("final_url") or ad.landing_url
    if final_url:
        add(url_observations(final_url))
        final_domain = registered_domain(host_of(final_url))
        hop_domains = {registered_domain(host_of(h["url"])) for h in victim.get("chain", [])} - {final_domain, ""}
        add([Observation("redirect_domain", d) for d in sorted(hop_domains)])

    page_text = ""
    html_artifact = None
    if victim.get("html_sha"):
        html_artifact = Artifact.objects.get(pk=victim["html_sha"])
        page = extract_page(store.get(html_artifact.sha256).decode("utf-8", errors="replace"), final_url or "https://nieznana.invalid/")
        add([o for o in page.observations if final_url or o.kind != "page_name"], html_artifact)
        if page.dom_hash:
            add([Observation("dom_hash", page.dom_hash)], html_artifact)
            markers.set_signature(ad, "dom_minhash", page.dom_signature)
        markers.set_signature(ad, "page_text_minhash", page.text_signature)
        page_text = f"{page.title} {page.visible_text}"
        analysis.state["favicon_url"] = page.favicon_url
        if not ad.title and page.title:
            ad.title = page.title[:500]
            ad.save(update_fields=["title"])

        bot = pages.get("bot") or {}
        if bot.get("html_sha") and bot["html_sha"] != victim["html_sha"]:
            bot_page = extract_page(store.get(bot["html_sha"]).decode("utf-8", errors="replace"), bot.get("final_url") or final_url)
            if bot_page.dom_hash and bot_page.dom_hash != page.dom_hash:
                # Automat dostał inną stronę niż ofiara. Ta "biała strona" sama jest odciskiem operatora.
                add([Observation("white_dom_hash", bot_page.dom_hash)], Artifact.objects.get(pk=bot["html_sha"]))
                analysis.state["cloaking"] = True

    # Ślady z przechwycenia: ruch sieciowy z HAR, zrzuty reklamy, metadane wideo.
    captured = [Observation(kind, value, detail or {}) for kind, value, detail in capture.get("observations", []) if kind in KINDS]
    har_artifact = Artifact.objects.filter(pk=capture.get("har")).first() if capture.get("har") else None
    add(captured, har_artifact or html_artifact)

    ad_text = f"{ad.title}\n{ad.text}".strip()
    if ad.text:
        features = extract_text(ad_text)
        add(features.observations)
        markers.set_signature(ad, "text_minhash", features.signature)

    if ad.advertiser_id:
        add([Observation("advertiser_id", f"{ad.advertiser.source}:{ad.advertiser.external_id}")])
        if ad.advertiser.payer:
            add([Observation("payer", ad.advertiser.payer.strip().lower())])

    markers.set_signature(ad, "image_set", [int(v) for v in capture.get("image_hashes", [])])
    markers.set_signature(ad, "video_frames", [int(v) for v in capture.get("video_hashes", [])])
    if capture.get("video_hashes"):
        counts["crea"] = counts.get("crea", 0) + len(capture["video_hashes"])
    if capture.get("image_hashes"):
        counts["crea"] = counts.get("crea", 0) + len(capture["image_hashes"])

    full_text = f"{ad_text} {page_text}"
    # Wektor znaczenia z treści strony (artykuł jest na początku, formularz lejka zwykle na końcu), a bez strony z tekstu reklamy.
    vector = embedding.embed(page_text.strip() or ad_text)
    ad.text_embedding = vector
    ad.save(update_fields=["text_embedding"])
    if vector:
        counts["narr"] = counts.get("narr", 0) + 1
    ad.labels["keywords"] = keywords(full_text)
    ad.labels["topics"] = topics(full_text)
    ad.save(update_fields=["labels"])
    add([Observation("topic", topic) for topic in ad.labels["topics"]])

    people = {p.pk: p for p in Person.objects.all()}
    found = find_people(f"{ad_text} {page_text}", [(p.pk, p.name, p.aliases) for p in people.values()])
    add([Observation("person_mention", people[pk].marker_value, {"name": people[pk].name}) for pk in found])

    analysis.save(update_fields=["state"])
    for family, count in sorted(counts.items()):
        emit(analysis, "extract", "info", f"{FAMILIES[family]}: {count}", {"family": family, "count": count})
    return {
        "markers": counts,
        "cloaking": bool(analysis.state.get("cloaking")),
        "people": [people[pk].name for pk in found],
        "topics": ad.labels["topics"],
        "keywords": ad.labels["keywords"],
    }


def stage_enrich(analysis: Analysis) -> dict:
    ad = analysis.ad
    offline = bool(analysis.state.get("offline"))
    victim = (analysis.state.get("pages") or {}).get("victim") or {}
    final_url = victim.get("final_url") or ad.landing_url
    host = host_of(final_url) if final_url else ""
    if not host:
        emit(analysis, "enrich", "info", "Brak domeny do wzbogacenia")
        return {}
    domain = registered_domain(host)
    source = enricher()
    observations: list[Observation] = []
    summary: dict = {"domain": domain, "offline": offline}

    if not offline:
        # Stan DNS i certyfikatu z dziś ma sens tylko dla strony badanej na żywo. Przechwycenie ma własne adresy z HAR.
        ips = source.resolve(host)
        observations += [Observation("ip", ip) for ip in ips]
        asns = sorted({a for a in (source.asn(ip) for ip in ips[:4]) if a})
        observations += [Observation("asn", a) for a in asns]
        nameservers = source.nameservers(domain)
        observations += [Observation("nameserver", ns) for ns in nameservers]
        summary.update(ips=ips, asn=asns, nameservers=nameservers)

        if final_url.startswith("https://"):
            fingerprint = source.tls_fingerprint(host)
            if fingerprint:
                observations.append(Observation("tls_fp", fingerprint))
                summary["tls_fp"] = fingerprint

        favicon_url = analysis.state.get("favicon_url") or f"{final_url.split('/')[0]}//{host}/favicon.ico"
        icon = fetcher().fetch_bytes(favicon_url)
        if icon:
            artifact = store.put(icon, kind="favicon", source_url=favicon_url)
            # Ten sam sposób liczenia co w Shodanie, żeby wartość dało się wkleić do wyszukiwarki hostów.
            value = str(mmh3.hash(base64.encodebytes(icon)))
            markers.attach(ad, [Observation("favicon_hash", value)], artifact)
            summary["favicon_hash"] = value

    rdap = source.rdap(domain)
    if rdap:
        DomainRecord.objects.update_or_create(
            domain=domain,
            defaults={"registered_at": rdap.registered_at, "registrar": rdap.registrar, "nameservers": rdap.nameservers, "raw": rdap.raw},
        )
        if rdap.registrar:
            observations.append(Observation("registrar", rdap.registrar))
        if rdap.registered_at:
            observations.append(Observation("reg_day", rdap.registered_at.date().isoformat()))
        if offline:
            observations += [Observation("nameserver", ns) for ns in rdap.nameservers]
        summary.update(registrar=rdap.registrar, registered_at=rdap.registered_at.isoformat() if rdap.registered_at else None)

    # Dzienniki certyfikatów są historyczne, więc mają sens także dla przechwyconej strony.
    certs = crtsh.lookup(domain, source)
    if certs is None:
        emit(analysis, "enrich", "info", "crt.sh nie odpowiedział, certyfikaty pominięte")
        summary["crtsh"] = None
    else:
        cert_observations, neighbours = crtsh.observations(domain, certs)
        observations += cert_observations
        summary["crtsh"] = {"certs": len(certs), "used": len(cert_observations), "domains": neighbours}
        if neighbours:
            emit(analysis, "enrich", "info", f"Certyfikat domeny obejmuje też: {', '.join(neighbours[:5])}", {"domains": neighbours})

    markers.attach(ad, observations)

    listed = WarningDomain.objects.filter(domain__in={domain, host}).first()
    if listed:
        ad.labels["cert_pl"] = {
            "domain": listed.domain,
            "added_at": listed.added_at.isoformat() if listed.added_at else None,
            "removed_at": listed.removed_at.isoformat() if listed.removed_at else None,
        }
        ad.save(update_fields=["labels"])
        emit(analysis, "enrich", "info", f"Domena {listed.domain} jest na Liście Ostrzeżeń CERT Polska", ad.labels["cert_pl"])
    summary["cert_pl_listed"] = bool(listed)
    return summary


def edge_payload(edge: Edge, ad_id: int) -> dict:
    return {
        "edge": edge.pk,
        "other_ad": edge.other(ad_id),
        "relation": edge.relation,
        "probability": round(edge.probability, 4),
        "bits": round(edge.bits, 2),
        "families": {f: round(b, 2) for f, b in edge.families.items()},
        "top_evidence": [
            {"family": e.family, "kind": e.kind, "label": KINDS[e.kind].label, "value": e.value_a[:120], "bits": round(e.weight_bits, 2)}
            for e in edge.evidence.all()[:3]
        ],
    }


def stage_fuse(analysis: Analysis) -> dict:
    ad = analysis.ad
    edges = linking.link_ad(ad)
    for edge in sorted(edges, key=lambda e: e.probability, reverse=True):
        emit(
            analysis, "fuse", "info", f"Powiązanie z reklamą #{edge.other(ad.pk)}: {edge.get_relation_display()}", edge_payload(edge, ad.pk)
        )
    return {
        "edges": len(edges),
        "duplicates": sum(1 for e in edges if e.duplicate),
        "same_campaign": sum(1 for e in edges if e.relation == Edge.Relation.SAME_CAMPAIGN),
        "same_operator": sum(1 for e in edges if e.relation == Edge.Relation.SAME_OPERATOR),
        "similar": sum(1 for e in edges if e.relation == Edge.Relation.SIMILAR),
    }


ASSESSMENTS = {
    "duplicate": "Duplikat materiału, który już jest w korpusie",
    "known_campaign": "Nowa odsłona znanej kampanii",
    "known_operator": "Nowa kampania znanego operatora",
    "similar_only": "Podobna koncepcja, brak dowodu wspólnego źródła",
    "new_pattern": "Nowy wzorzec, brak powiązań z korpusem",
}


def stage_cluster(analysis: Analysis) -> dict:
    ad = analysis.ad
    was_in_campaign = CampaignMembership.objects.filter(ad=ad).exists()
    was_in_operator = OperatorMembership.objects.filter(ad=ad).exists()
    campaign, operator = linking.assign_campaign(ad), linking.assign_operator(ad)
    result = {**campaign, **operator}
    alerts = alerting.record(ad, was_in_campaign=was_in_campaign, was_in_operator=was_in_operator, campaign=campaign, operator=operator)
    result["alerts"] = [a.kind for a in alerts]
    fused = analysis.result.get("fuse", {})
    if fused.get("duplicates"):
        assessment = "duplicate"
    elif result.get("campaign"):
        assessment = "known_campaign"
    elif result.get("operator"):
        assessment = "known_operator"
    elif fused.get("similar"):
        assessment = "similar_only"
    else:
        assessment = "new_pattern"
    return {**result, "assessment": assessment, "assessment_label": ASSESSMENTS[assessment]}


HANDLERS: dict[str, Callable[[Analysis], dict]] = {
    "ingest": stage_ingest,
    "crawl": stage_crawl,
    "extract": stage_extract,
    "enrich": stage_enrich,
    "fuse": stage_fuse,
    "cluster": stage_cluster,
}


# --- sterowanie ------------------------------------------------------------


def run_stage(analysis_id: str, stage: str) -> dict:
    analysis = Analysis.objects.select_related("ad", "ad__advertiser").get(pk=analysis_id)
    if analysis.status == Analysis.Status.QUEUED:
        analysis.status = Analysis.Status.RUNNING
        analysis.save(update_fields=["status"])
    emit(analysis, stage, "started", STAGE_LABELS[stage])
    try:
        summary = HANDLERS[stage](analysis)
    except Exception as exc:
        emit(analysis, stage, "error", f"{type(exc).__name__}: {exc}")
        raise
    analysis.result[stage] = summary
    analysis.save(update_fields=["result"])
    emit(analysis, stage, "done", STAGE_LABELS[stage], summary)
    return summary


def finish(analysis_id: str, error: str = "") -> None:
    analysis = Analysis.objects.get(pk=analysis_id)
    analysis.status = Analysis.Status.FAILED if error else Analysis.Status.DONE
    analysis.error = error
    analysis.finished_at = timezone.now()
    analysis.save(update_fields=["status", "error", "finished_at"])
    emit(analysis, "end", "error" if error else "done", error or "Analiza zakończona", {"status": analysis.status})


def run_all(analysis_id: str) -> None:
    try:
        for stage in STAGES:
            run_stage(analysis_id, stage)
    except Exception as exc:  # noqa: BLE001
        finish(analysis_id, error=f"{type(exc).__name__}: {exc}")
        return
    finish(analysis_id)
