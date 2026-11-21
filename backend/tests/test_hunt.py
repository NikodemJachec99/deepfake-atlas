"""Łowca domen: profil operatora, kandydaci z atrapy crt.sh, potwierdzenie przez atrapę crawlera, alert i API. Bez sieci."""

from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone

from ads.models import Ad, Analysis, Source
from enrichment.models import CertLookup, WarningDomain
from evidence import services as markers
from extractors import Observation
from hunting import service
from hunting.models import HuntCandidate, HuntRun
from hunting.names import name_template, name_tokens
from hunting.profile import build_profile
from similarity.models import Alert, Operator, OperatorMembership
from tests import fakes
from tests.test_browser_crawler import entry
from tests.test_extractors import LANDING_A, OTHER

pytestmark = pytest.mark.django_db

FUNNEL = "3f2c9a1e-7b4d-4c2a-9e8f-0a1b2c3d4e5f"
KIT = "POST /api/lead/submit"
ISSUER = "C=US, O=Let's Encrypt, CN=R11"


def stamp(days_ago: float = 1.0) -> str:
    return (timezone.now() - timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%S")


def cert(names: str, *, days_ago: float = 1.0, serial: str = "aa11", issuer: str = ISSUER, cert_id: int = 5001) -> dict:
    return {
        "id": cert_id, "issuer_name": issuer, "name_value": names, "common_name": names.splitlines()[0],
        "not_before": stamp(days_ago), "serial_number": serial,
    }


def make_operator(domains=("wiosenna-kuracja.example", "kuracja-wiosenna24.example", "wiosenna-promocja7.example")) -> Operator:
    """Operator z trzema reklamami (po jednej domenie). Pierwsza ma ślady zaplecza: ścieżkę zestawu, lejek, hash DOM i GA."""
    operator = Operator.objects.create()
    for i, domain in enumerate(domains):
        ad = Ad.objects.create(source=Source.MANUAL, landing_url=f"https://{domain}/", first_seen=timezone.now(), last_seen=timezone.now())
        OperatorMembership.objects.create(ad=ad, operator=operator)
        observations = [Observation("domain", domain)]
        if i == 0:
            observations += [
                Observation("kit_path", KIT), Observation("funnel_id", FUNNEL), Observation("ga4", "G-7K2QX9LM4T"),
                Observation("registrar", "Rejestrator Testowy"),
            ]
        markers.attach(ad, observations)
        if i == 1:
            markers.attach(ad, [Observation("tls_serial", "bb22", {"from": "crt.sh", "issuer": ISSUER})])
    return operator


def kit_page(domain: str) -> None:
    """Strona kandydata z identyfikatorem lejka i ścieżką zestawu operatora w ruchu sieciowym."""
    url = f"https://{domain}/"
    har = {
        "log": {
            "entries": [
                entry(url, text=LANDING_A.replace("G-7K2QX9LM4T", "G-OTHER00000")),
                entry(f"{url}api/lead/submit", method="POST", mime="application/json", text="{}", post=f"offer_uuid={FUNNEL}&name=x"),
            ]
        }
    }
    fakes.page(url, LANDING_A.replace("G-7K2QX9LM4T", "G-OTHER00000"), har=har)


def run_hunt(operator: Operator | None = None, **options) -> HuntRun:
    params = {"operator": operator.pk if operator else None, **options}
    run = service.create_run(params, params["operator"])
    service.execute(str(run.pk))
    run.refresh_from_db()
    return run


# --- profil -------------------------------------------------------------------


def test_name_helpers_split_on_hyphens_and_digits_and_skip_generic_words():
    assert name_tokens("wiosenna-kuracja24-online") == ["wiosenna", "kuracja"]  # "online" jest ogólne
    assert name_tokens("abc-shop") == []  # za krótkie albo ogólne
    assert name_template("wiosenna-kuracja24") == "wiosenna-kuracja{n}"


def test_profile_derives_tokens_with_provenance_and_marker_patterns():
    operator = make_operator()
    profile = build_profile(operator)
    tokens = {p.value: p for p in profile.of_type("name_token")}
    assert set(tokens) == {"wiosenna", "kuracja"}  # "promocja" jest słowem ogólnym
    assert tokens["wiosenna"].to_dict()["ad_count"] == 3 and tokens["kuracja"].to_dict()["ad_count"] == 2
    assert tokens["wiosenna"].weight > tokens["kuracja"].weight
    assert tokens["wiosenna"].to_dict()["domains"] == sorted(profile.domains)
    assert {p.value for p in profile.of_type("name_template")} >= {"wiosenna-kuracja", "kuracja-wiosenna{n}"}
    assert [p.value for p in profile.of_type("cert_issuer")] == ["R11"]
    confirm = {(p.kind, p.value): p.to_dict() for p in profile.of_type("marker")}
    assert confirm[("kit_path", KIT)]["ad_count"] == 1
    assert {"funnel_id", "ga4", "registrar"} <= {kind for kind, _ in confirm}
    assert profile.to_dict()["queries"][0] == "wiosenna"


def test_token_common_in_other_operators_domains_is_not_a_search_token():
    operator = make_operator()
    other = Operator.objects.create()
    for i in range(5):  # pięć obcych domen z tym samym słowem
        ad = Ad.objects.create(source=Source.MANUAL)
        OperatorMembership.objects.create(ad=ad, operator=other)
        markers.attach(ad, [Observation("domain", f"cudze-kuracja{i}.example")])
    tokens = {p.value: p for p in build_profile(operator).of_type("name_token")}
    assert tokens["kuracja"].detail["generic"] is True and tokens["kuracja"].weight == 0.0
    assert tokens["wiosenna"].detail["generic"] is False


# --- przebieg -----------------------------------------------------------------


def test_confirmed_candidate_gets_bits_evidence_and_alert():
    operator = make_operator()
    fakes.CT["wiosenna"] = [
        cert("wiosenna-kuracja2.example\nwww.wiosenna-kuracja2.example", serial="c0ffee", cert_id=777),
        cert("wiosenna-kuracja.example", serial="dd33"),  # ta domena jest już w korpusie
        cert("wiosenna-stara.example", days_ago=60),  # poza oknem 30 dni
        cert("zupelnie-obca.example\nwiosenna-kuracja2.example", serial="c0ffee", cert_id=777),
    ]
    kit_page("wiosenna-kuracja2.example")

    run = run_hunt(operator)

    assert run.status == HuntRun.Status.DONE
    assert run.stats["queries_made"] == 2 and run.stats["in_corpus_skipped"] == 1
    candidate = HuntCandidate.objects.get()
    assert candidate.domain == "wiosenna-kuracja2.example" and candidate.operator == operator
    assert candidate.sources == ["crtsh"] and candidate.cert_serial == "c0ffee" and candidate.crtsh_id == 777
    assert candidate.cert_issuer == ISSUER and candidate.prelim_score >= 0.45
    assert {t["token"] for t in candidate.score_parts["tokens"]} == {"wiosenna", "kuracja"}
    assert candidate.score_parts["issuer"] == "R11"

    assert candidate.status == HuntCandidate.Status.CONFIRMED
    assert candidate.bits > 10 and candidate.probability > 0.9
    by_kind = {e["kind"]: e for e in candidate.evidence}
    assert {"funnel_id", "kit_path"} <= set(by_kind)
    assert by_kind["funnel_id"]["bits"] > 8 and by_kind["funnel_id"]["decisive"] is True
    assert by_kind["funnel_id"]["ad_ids"] == by_kind["kit_path"]["ad_ids"]  # reklama operatora, z której wzięto ślad
    assert "ga4" not in by_kind  # inny identyfikator GA niż u operatora
    assert candidate.screenshot_sha == "" and candidate.html_sha  # zrzutu atrapa nie ma, HTML jest w dowodach

    alert = Alert.objects.get()
    assert alert.kind == Alert.Kind.HUNT_CONFIRMED and alert.ad is None and alert.hunt_candidate == candidate
    assert alert.operator == operator and "wiosenna-kuracja2.example" in alert.description
    assert alert.evidence[0]["bits"] >= alert.evidence[-1]["bits"] and len(alert.evidence) <= 3


def test_domain_already_in_corpus_is_filtered_out():
    operator = make_operator()
    fakes.CT["wiosenna"] = [cert("wiosenna-kuracja.example\nkuracja-wiosenna24.example")]
    run = run_hunt(operator)
    assert run.stats["in_corpus_skipped"] == 2 and run.stats["candidates_new"] == 0
    assert not HuntCandidate.objects.exists() and not Alert.objects.exists()
    assert not any("wiosenna-kuracja.example" in url for url in fakes.FETCH_CALLS)


def test_unreachable_page_is_marked_unavailable_and_retried_later():
    operator = make_operator()
    fakes.CT["wiosenna"] = [cert("wiosenna-kuracja3.example")]  # brak strony w atrapie: błąd połączenia
    run_hunt(operator)
    candidate = HuntCandidate.objects.get()
    assert candidate.status == HuntCandidate.Status.UNAVAILABLE and candidate.attempts == 1
    assert "ConnectError" in candidate.crawl_error and candidate.bits is None
    assert not Alert.objects.exists()

    # zaraz po tym nie próbujemy ponownie, po upływie czasu tak, i strona już działa
    fakes.FETCH_CALLS.clear()
    run_hunt(operator)
    assert fakes.FETCH_CALLS == []
    HuntCandidate.objects.update(checked_at=timezone.now() - timedelta(hours=13))
    kit_page("wiosenna-kuracja3.example")
    run_hunt(operator)
    candidate.refresh_from_db()
    assert candidate.status == HuntCandidate.Status.CONFIRMED and candidate.attempts == 2


def test_page_without_common_traces_is_rejected_and_not_alerted():
    operator = make_operator()
    fakes.CT["wiosenna"] = [cert("wiosenna-kuracja4.example")]
    fakes.page("https://wiosenna-kuracja4.example/", OTHER)
    run_hunt(operator)
    candidate = HuntCandidate.objects.get()
    assert candidate.status == HuntCandidate.Status.REJECTED and candidate.evidence == []
    assert not Alert.objects.exists()


def test_query_limit_is_respected_and_cached_between_runs():
    operator = make_operator()
    fakes.CT["wiosenna"] = [cert("wiosenna-kuracja5.example")]
    fakes.CT["kuracja"] = [cert("kuracja-nowa.example")]
    run = run_hunt(operator, max_queries=1, crawl=False)
    assert fakes.CT_CALLS == ["wiosenna"] and run.stats["queries_made"] == 1
    assert [q["token"] for q in run.stats["queries"]] == ["wiosenna"]
    assert CertLookup.objects.get().domain == "hunt:wiosenna"

    run_hunt(operator, max_queries=1, crawl=False)
    assert fakes.CT_CALLS == ["wiosenna"]  # odpowiedź z pamięci, drugiego zapytania nie ma


def test_empty_crtsh_answer_is_not_cached():
    operator = make_operator()
    run_hunt(operator, max_queries=1, crawl=False)
    assert fakes.CT_CALLS == ["wiosenna"] and not CertLookup.objects.exists()
    fakes.CT["wiosenna"] = [cert("wiosenna-kuracja5.example")]
    run_hunt(operator, max_queries=1, crawl=False)
    assert fakes.CT_CALLS == ["wiosenna", "wiosenna"]  # pusta odpowiedź nie zasłoniła certyfikatu
    assert HuntCandidate.objects.get().domain == "wiosenna-kuracja5.example"


def test_no_crawl_leaves_candidates_without_touching_pages():
    operator = make_operator()
    fakes.CT["wiosenna"] = [cert("wiosenna-kuracja6.example")]
    kit_page("wiosenna-kuracja6.example")
    run = run_hunt(operator, crawl=False)
    assert fakes.FETCH_CALLS == [] and "crawled" not in run.stats
    candidate = HuntCandidate.objects.get()
    assert candidate.status == HuntCandidate.Status.CANDIDATE and candidate.checked_at is None and candidate.bits is None


def test_crawl_limit_takes_best_scored_candidates_first():
    operator = make_operator()
    fakes.CT["wiosenna"] = [cert("wiosenna-kuracja7.example"), cert("wiosenna-zielona.example")]
    for domain in ("wiosenna-kuracja7.example", "wiosenna-zielona.example"):
        kit_page(domain)
    run = run_hunt(operator, max_crawl=1)
    assert run.stats["crawled"] == 1
    assert fakes.FETCH_CALLS == ["https://wiosenna-kuracja7.example/"]  # dwa tokeny wygrywają z jednym
    assert HuntCandidate.objects.get(domain="wiosenna-zielona.example").status == HuntCandidate.Status.CANDIDATE


def test_crtsh_not_answering_stops_the_run_without_candidates():
    operator = make_operator()
    fakes.CT["wiosenna"] = None
    fakes.CT["kuracja"] = None
    run = run_hunt(operator, max_queries=5)
    assert run.status == HuntRun.Status.DONE
    assert run.stats["aborted"] and run.stats["queries_made"] == 2
    assert not HuntCandidate.objects.exists()
    assert not CertLookup.objects.exists()  # brak odpowiedzi nie trafia do pamięci


def test_cert_pl_list_is_a_second_source():
    operator = make_operator()
    now = timezone.now()
    WarningDomain.objects.create(domain="wiosenna-kuracja8.example", added_at=now - timedelta(days=2))
    WarningDomain.objects.create(domain="wiosenna-dawna.example", added_at=now - timedelta(days=90))
    WarningDomain.objects.create(domain="wiosenna-zdjeta.example", added_at=now - timedelta(days=2), removed_at=now)
    WarningDomain.objects.create(domain="wiosenna-wrocila.example", added_at=now - timedelta(days=1), removed_at=now - timedelta(days=5))
    fakes.CT["wiosenna"] = [cert("wiosenna-kuracja8.example")]
    run = run_hunt(operator, crawl=False)
    assert run.stats["cert_pl_hits"] == 2
    domains = {c.domain for c in HuntCandidate.objects.all()}
    assert domains == {"wiosenna-kuracja8.example", "wiosenna-wrocila.example"}
    assert HuntCandidate.objects.get(domain="wiosenna-kuracja8.example").sources == ["cert_pl", "crtsh"]


def test_rerun_does_not_duplicate_candidates_or_alerts():
    operator = make_operator()
    fakes.CT["wiosenna"] = [cert("wiosenna-kuracja2.example")]
    kit_page("wiosenna-kuracja2.example")
    run_hunt(operator)
    CertLookup.objects.all().delete()
    fakes.FETCH_CALLS.clear()
    run = run_hunt(operator)
    assert HuntCandidate.objects.count() == 1 and Alert.objects.count() == 1
    assert fakes.FETCH_CALLS == [] and run.stats["candidates_new"] == 0 and run.stats["candidates_updated"] == 1


def test_hunt_command_runs_one_operator_and_prints_progress():
    operator = make_operator()
    make_operator(("inna-nazwa.example",))
    fakes.CT["wiosenna"] = [cert("wiosenna-kuracja2.example")]
    kit_page("wiosenna-kuracja2.example")
    out = StringIO()
    call_command("hunt", "--operator", operator.key, "--days", "7", "--max-queries", "3", stdout=out)
    text = out.getvalue()
    assert "crt.sh %wiosenna%" in text and "potwierdzony" in text
    assert HuntRun.objects.get().params["days"] == 7 and HuntRun.objects.get().status == HuntRun.Status.DONE
    assert HuntCandidate.objects.get().operator == operator


# --- API ----------------------------------------------------------------------


def confirmed_candidate() -> tuple[Operator, HuntCandidate]:
    operator = make_operator()
    fakes.CT["wiosenna"] = [cert("wiosenna-kuracja2.example")]
    kit_page("wiosenna-kuracja2.example")
    run_hunt(operator)
    return operator, HuntCandidate.objects.get()


def test_api_lists_candidates_with_filters(client):
    operator, candidate = confirmed_candidate()
    HuntCandidate.objects.create(domain="wiosenna-x.example", operator=operator, sources=["cert_pl"], prelim_score=0.9)
    data = client.get("/api/hunt").json()
    assert data["count"] == 2 and data["results"][0]["status"] == "confirmed"  # potwierdzeni pierwsi
    first = data["results"][0]
    assert first["operator"] == operator.key and first["cert"]["issuer"] == ISSUER and first["bits"] > 10
    assert first["evidence"][0]["ad_ids"] and first["alert"] == Alert.objects.get().pk and first["ad"] is None
    assert client.get("/api/hunt?status=candidate").json()["count"] == 1
    assert client.get("/api/hunt?source=cert_pl").json()["results"][0]["domain"] == "wiosenna-x.example"
    assert client.get(f"/api/hunt?operator={operator.key}").json()["count"] == 2
    assert client.get("/api/hunt?operator=999").json()["count"] == 0


def test_api_hunt_profile_shows_patterns_with_origin(client):
    operator = make_operator()
    data = client.get(f"/api/operators/{operator.pk}/hunt-profile").json()
    assert data["operator"]["key"] == operator.key and data["ads"] == 3 and data["queries"][:2] == ["wiosenna", "kuracja"]
    token = next(p for p in data["patterns"] if p["type"] == "name_token" and p["value"] == "wiosenna")
    assert token["role"] == "search" and token["ad_count"] == 3 and len(token["ad_ids"]) == 3 and token["domains"]
    kit = next(p for p in data["patterns"] if p["kind"] == "kit_path")
    assert kit["role"] == "confirm" and kit["value"] == KIT and kit["label"]
    assert client.get("/api/operators/9999/hunt-profile").status_code == 404


def test_api_run_starts_in_background_and_reports_the_run(client):
    operator = make_operator()
    fakes.CT["wiosenna"] = [cert("wiosenna-kuracja2.example")]
    kit_page("wiosenna-kuracja2.example")
    response = client.post("/api/hunt/run", {"operator": operator.pk, "days": 14, "max_queries": 2}, content_type="application/json")
    assert response.status_code == 202
    body = response.json()
    assert body["operator"] == operator.key and body["params"]["days"] == 14 and body["status"] == "done"
    assert body["stats"]["candidates_new"] == 1 and body["stats"]["confirmed"] == 1
    assert client.get(f"/api/hunt/runs/{body['id']}").json()["status"] == "done"
    assert client.get("/api/hunt/runs").json()["results"][0]["id"] == body["id"]


def test_api_run_refuses_second_run_while_one_is_active_and_bad_input(client):
    make_operator()
    HuntRun.objects.create(status=HuntRun.Status.RUNNING)
    busy = client.post("/api/hunt/run", {}, content_type="application/json")
    assert busy.status_code == 409 and busy.json()["run"]["status"] == "running"
    HuntRun.objects.all().delete()
    assert client.post("/api/hunt/run", {"days": 0}, content_type="application/json").status_code == 400
    assert client.post("/api/hunt/run", {"max_queries": 9999}, content_type="application/json").status_code == 400
    assert client.post("/api/hunt/run", {"operator": 9999}, content_type="application/json").status_code == 400
    assert not fakes.CT_CALLS


def test_api_analyze_sends_domain_through_full_pipeline_once(client):
    operator, candidate = confirmed_candidate()
    response = client.post(f"/api/hunt/{candidate.pk}/analyze")
    assert response.status_code == 201
    analysis = Analysis.objects.get(pk=response.json()["id"])
    assert analysis.input_value == "https://wiosenna-kuracja2.example/" and analysis.status == Analysis.Status.DONE
    candidate.refresh_from_db()
    assert candidate.analysis == analysis
    assert client.get("/api/hunt").json()["results"][0]["ad"] == analysis.ad_id != None  # noqa: E711
    # ten sam kształt, ślady operatora na stronie, więc pełny potok przypisuje reklamę do operatora
    assert analysis.result["cluster"]["operator"] == operator.key
    again = client.post(f"/api/hunt/{candidate.pk}/analyze")
    assert again.status_code == 409 and again.json()["analysis"]["id"] == str(analysis.pk)
    assert client.post("/api/hunt/99999/analyze").status_code == 404


def test_hunt_alert_appears_in_alert_list_and_can_be_marked_seen(client):
    confirmed_candidate()
    data = client.get("/api/alerts?unseen=1").json()
    assert data["count"] == 1
    alert = data["results"][0]
    assert alert["kind"] == "hunt_confirmed" and alert["ad"] is None and alert["ad_title"] == ""
    assert alert["domain"] == "wiosenna-kuracja2.example" and alert["hunt_candidate"] and alert["operator"].startswith("O-")
    assert client.post(f"/api/alerts/{alert['id']}/seen", {}, content_type="application/json").json()["seen"] is True
    assert client.get("/api/alerts?unseen=1").json()["count"] == 0


@override_settings(API_WRITE_KEY="sekret")
def test_hunt_writes_need_the_api_key(client):
    make_operator()
    assert client.post("/api/hunt/run", {}, content_type="application/json").status_code == 401
    assert client.post("/api/hunt/1/analyze").status_code == 401
    assert client.get("/api/hunt").status_code == 200
