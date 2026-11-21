"""Łowca domen: profile operatorów, kandydaci z dzienników certyfikatów, potwierdzenie przez crawlera.

Przebieg:
  1. profil każdego znanego operatora (`profile.build_profile`) i plan zapytań do crt.sh po jego tokenach,
  2. kandydaci: domeny ze świeżych certyfikatów i z Listy Ostrzeżeń CERT Polska, bez tych, które już są w korpusie,
  3. wynik wstępny bez sieci do strony (`scoring.prelim_score`), zapis kandydatów powyżej progu,
  4. crawler pobiera najlepszych (limit na przebieg), a `confirm.evaluate` porównuje stronę ze śladami operatora,
  5. potwierdzona domena daje alert `hunt_confirmed`.
Domeny z korpusu, ponowne przebiegi i kandydaci już rozstrzygnięci niczego nie dublują.
"""

import logging
from collections.abc import Callable
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from ads.models import Analysis
from extractors.url import redact_url
from similarity import alerts as alerting
from workflows import runner

from . import confirm, sources
from .models import HuntCandidate, HuntRun
from .profile import CorpusNames, Profile, build_profile, hunted_operators, operator_ad_ids
from .scoring import DEFAULT_THRESHOLD, prelim_score

log = logging.getLogger(__name__)

DEFAULTS = {"days": 30, "max_queries": 12, "max_crawl": 20, "crawl": True, "threshold": DEFAULT_THRESHOLD}
RETRY_AFTER = timedelta(hours=12)  # niedostępną stronę próbujemy ponownie najwcześniej po tylu godzinach
MAX_ATTEMPTS = 3
RECHECK_AFTER = timedelta(days=7)  # słabego kandydata i odrzuconego sprawdzamy ponownie po tylu dniach (strona mogła się zmienić)
MAX_FAILED_QUERIES = 2  # tyle zapytań pod rząd bez odpowiedzi crt.sh kończy zbieranie kandydatów


def plan_queries(profiles: list[Profile], max_queries: int) -> list[str]:
    """Tokeny do zapytań: najlepszy token każdego operatora, potem drugi i tak dalej. Bez powtórzeń, najwyżej `max_queries`."""
    ranked = [[p.value for p in profile.search_tokens] for profile in profiles]
    plan: list[str] = []
    for rank in range(max((len(r) for r in ranked), default=0)):
        for tokens in ranked:
            if rank < len(tokens) and tokens[rank] not in plan:
                plan.append(tokens[rank])
    return plan[:max_queries]


def collect_hits(profiles: list[Profile], enricher, *, days: int, max_queries: int, now, stats: dict, say) -> dict[str, sources.Hit]:
    cutoff = now - timedelta(days=days)
    hits: dict[str, sources.Hit] = {}
    stats["queries"] = []
    failed_in_row = 0
    for token in plan_queries(profiles, max_queries):
        rows = sources.search_certs(token, enricher, now)
        if rows is None:
            failed_in_row += 1
            stats["queries"].append({"token": token, "ok": False})
            say(f"crt.sh %{token}%: brak odpowiedzi")
            if failed_in_row >= MAX_FAILED_QUERIES:
                stats["aborted"] = "crt.sh nie odpowiada, reszta zapytań pominięta"
                break
            continue
        failed_in_row = 0
        found = sources.hits_from_certs(rows, cutoff)
        stats["queries"].append({"token": token, "ok": True, "certs": len(rows), "domains": len(found)})
        say(f"crt.sh %{token}%: {len(rows)} certyfikatów z ostatnich {sources.MAX_WINDOW_DAYS} dni, {len(found)} domen w oknie {days} dni")
        for domain, hit in found.items():
            known = hits.get(domain)
            if known is None or (hit.not_before and (known.not_before is None or hit.not_before > known.not_before)):
                hits[domain] = hit
    stats["queries_made"] = len(stats["queries"])

    listed = sources.cert_pl_hits([p.value for profile in profiles for p in profile.search_tokens], cutoff)
    stats["cert_pl_hits"] = len(listed)
    for domain, hit in listed.items():
        if domain in hits:
            hits[domain].sources |= hit.sources
        else:
            hits[domain] = hit
    return hits


def store_candidates(hits: dict[str, sources.Hit], profiles: list[Profile], corpus: CorpusNames, threshold: float, run: HuntRun | None, stats: dict) -> None:
    new = updated = below = skipped = 0
    for domain, hit in sorted(hits.items()):
        if domain in corpus:
            skipped += 1
            continue
        matched_any = False
        for profile in profiles:
            score, parts = prelim_score(domain, hit.issuer, profile)
            if score < threshold:
                continue
            matched_any = True
            candidate, created = HuntCandidate.objects.get_or_create(
                domain=domain,
                operator=profile.operator,
                defaults={
                    "sources": sorted(hit.sources), "cert_issuer": hit.issuer, "cert_serial": hit.serial,
                    "cert_not_before": hit.not_before, "crtsh_id": hit.crtsh_id, "prelim_score": score, "score_parts": parts, "run": run,
                },
            )
            if created:
                new += 1
                continue
            candidate.sources = sorted({*candidate.sources, *hit.sources})
            candidate.prelim_score, candidate.score_parts = score, parts
            if hit.not_before and (candidate.cert_not_before is None or hit.not_before > candidate.cert_not_before):
                candidate.cert_issuer, candidate.cert_serial = hit.issuer, hit.serial
                candidate.cert_not_before, candidate.crtsh_id = hit.not_before, hit.crtsh_id
            candidate.run = run
            candidate.save()
            updated += 1
        if not matched_any:
            below += 1
    stats.update(candidates_new=new, candidates_updated=updated, below_threshold=below, in_corpus_skipped=skipped, domains_seen=len(hits))


def crawl_candidates(profiles: list[Profile], *, threshold: float, max_crawl: int, fetcher, enricher, now, stats: dict, say) -> None:
    by_operator = {p.operator.pk: p for p in profiles}
    eligible = (
        HuntCandidate.objects.filter(operator_id__in=by_operator, prelim_score__gte=threshold)
        .filter(
            Q(status=HuntCandidate.Status.CANDIDATE, checked_at__isnull=True)
            | Q(status=HuntCandidate.Status.UNAVAILABLE, attempts__lt=MAX_ATTEMPTS, checked_at__lt=now - RETRY_AFTER)
            | Q(status__in=[HuntCandidate.Status.CANDIDATE, HuntCandidate.Status.REJECTED], checked_at__lt=now - RECHECK_AFTER)
        )
        .select_related("operator")
        .order_by("-prelim_score", "-created_at")[:max_crawl]
    )
    counts = {"crawled": 0, "confirmed": 0, "rejected": 0, "unavailable": 0, "weak": 0}
    observed_cache: dict[str, confirm.Observed] = {}
    for candidate in eligible:
        profile = by_operator[candidate.operator_id]
        observed = observed_cache.get(candidate.domain)
        if observed is None:
            try:
                observed = confirm.observe(candidate.domain, fetcher, enricher, try_http="crtsh" not in candidate.sources)
            except Exception as exc:  # noqa: BLE001  jedna strona nie zatrzymuje przebiegu
                log.warning("Łowca: %s: %s", candidate.domain, exc)
                observed = confirm.Observed(candidate.domain, error=f"{type(exc).__name__}: {exc}"[:300])
            observed_cache[candidate.domain] = observed
        counts["crawled"] += 1
        candidate.attempts += 1
        candidate.checked_at = now
        candidate.final_url, candidate.http_status = observed.final_url, observed.http_status
        candidate.html_sha, candidate.screenshot_sha, candidate.crawl_error = observed.html_sha, observed.screenshot_sha, observed.error
        if not observed.reachable:
            candidate.status = HuntCandidate.Status.UNAVAILABLE
            candidate.note = "Strona niedostępna dla crawlera"
            counts["unavailable"] += 1
            say(f"{candidate.domain} ({profile.operator.key}): niedostępna ({observed.error})")
            candidate.save()
            continue
        verdict = confirm.evaluate(operator_ad_ids(profile.operator), observed.observations)
        candidate.status, candidate.bits, candidate.probability = verdict.status, verdict.bits, verdict.probability
        candidate.evidence, candidate.note, candidate.crawl_error = verdict.evidence, verdict.note, ""
        candidate.save()
        if verdict.status == HuntCandidate.Status.CONFIRMED:
            alerting.record_hunt(candidate)
            counts["confirmed"] += 1
        elif verdict.status == HuntCandidate.Status.REJECTED:
            counts["rejected"] += 1
        else:
            counts["weak"] += 1
        say(f"{candidate.domain} ({profile.operator.key}): {candidate.get_status_display().lower()}, {verdict.bits} bita")
    stats.update(counts)


def hunt(
    *,
    operator_id: int | None = None,
    days: int = DEFAULTS["days"],
    max_queries: int = DEFAULTS["max_queries"],
    max_crawl: int = DEFAULTS["max_crawl"],
    crawl: bool = DEFAULTS["crawl"],
    threshold: float = DEFAULTS["threshold"],
    run: HuntRun | None = None,
    enricher=None,
    fetcher=None,
    say: Callable[[str], None] = lambda _msg: None,
) -> dict:
    from workflows.pipeline import enricher as default_enricher
    from workflows.pipeline import fetcher as default_fetcher

    enricher = enricher or default_enricher()
    now = timezone.now()
    corpus = CorpusNames()
    operators = hunted_operators(operator_id)
    profiles = [build_profile(op, corpus) for op in operators]
    stats: dict = {
        "operators": len(profiles),
        "tokens": {p.operator.key: [t.value for t in p.search_tokens] for p in profiles},
        "days": days,
        "max_queries": max_queries,
    }
    say(f"Operatorzy: {len(profiles)}, tokenów do zapytań: {sum(len(p.search_tokens) for p in profiles)}")
    profiles = [p for p in profiles if p.search_tokens]
    if not profiles:
        stats["note"] = "brak operatorów z tokenami nazw, nic do szukania"
        return stats

    hits = collect_hits(profiles, enricher, days=days, max_queries=max_queries, now=now, stats=stats, say=say)
    store_candidates(hits, profiles, corpus, threshold, run, stats)
    say(
        f"Domen w certyfikatach i na liście CERT: {stats['domains_seen']}, w korpusie pominięto {stats['in_corpus_skipped']}, "
        f"nowych kandydatów {stats['candidates_new']}, odświeżonych {stats['candidates_updated']}"
    )
    if crawl:
        crawl_candidates(profiles, threshold=threshold, max_crawl=max_crawl, fetcher=fetcher or default_fetcher(), enricher=enricher, now=now, stats=stats, say=say)
    return stats


def create_run(params: dict, operator_id: int | None = None) -> HuntRun:
    return HuntRun.objects.create(operator_id=operator_id, params=params)


def execute(run_id: str, params: dict | None = None, say: Callable[[str], None] = lambda _msg: None) -> dict:
    """Wykonuje przebieg zapisany w bazie (albo zakłada go z `params`, gdy `run_id` jest pusty: harmonogram)."""
    run = HuntRun.objects.get(pk=run_id) if run_id else create_run(params or {}, (params or {}).get("operator"))
    options = {**DEFAULTS, **{k: v for k, v in run.params.items() if k in DEFAULTS}}
    run.status, run.started_at = HuntRun.Status.RUNNING, timezone.now()
    run.save(update_fields=["status", "started_at"])
    try:
        stats = hunt(operator_id=run.params.get("operator"), run=run, say=say, **options)
    except Exception as exc:  # noqa: BLE001
        run.status, run.error = HuntRun.Status.FAILED, f"{type(exc).__name__}: {exc}"[:2000]
        run.finished_at = timezone.now()
        run.save(update_fields=["status", "error", "finished_at"])
        raise
    run.status, run.stats, run.finished_at = HuntRun.Status.DONE, stats, timezone.now()
    run.save(update_fields=["status", "stats", "finished_at"])
    return stats


def submit_for_analysis(candidate: HuntCandidate) -> Analysis:
    """Zgłasza domenę do pełnego potoku analizy. Po nim jest reklamą w korpusie i łączy się z operatorem jak każda."""
    url = candidate.final_url or f"https://{candidate.domain}/"
    analysis = Analysis.objects.create(input_kind=Analysis.Kind.URL, input_value=redact_url(url))
    candidate.analysis = analysis
    candidate.save(update_fields=["analysis", "updated_at"])
    runner.start(str(analysis.pk))
    analysis.refresh_from_db()
    return analysis


def active_run() -> HuntRun | None:
    """Przebieg w kolejce albo w toku z ostatnich dwóch godzin. Drugiego nie uruchamiamy: crt.sh prosi o umiar."""
    since = timezone.now() - timedelta(hours=2)
    return HuntRun.objects.filter(status__in=[HuntRun.Status.QUEUED, HuntRun.Status.RUNNING], created_at__gte=since).first()

