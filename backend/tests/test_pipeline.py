"""Potok od zgłoszenia do kampanii z dowodami, na prawdziwej bazie i bez sieci."""

import pytest

from ads.models import Ad, Analysis
from enrichment.models import WarningDomain
from evidence.models import Marker
from people.models import Person
from similarity import decisions
from similarity.models import Campaign, CampaignMembership, Edge, OperatorMembership
from similarity.service import assign_campaign
from tests import fakes
from tests.test_extractors import LANDING_A, OTHER, _article
from workflows import pipeline

pytestmark = pytest.mark.django_db


def analyze(kind: str, value: str) -> Analysis:
    analysis = Analysis.objects.create(input_kind=kind, input_value=value)
    pipeline.run_all(str(analysis.pk))
    analysis.refresh_from_db()
    return analysis


def analyze_url(url: str) -> Analysis:
    return analyze(Analysis.Kind.URL, url)


def test_different_domains_same_tracker_and_template_become_one_campaign():
    # Dwie reklamy: inne domeny, inne teksty na stronie, ten sam identyfikator GA i ten sam szablon.
    fakes.page("https://zysk-a.example/lp/1", LANDING_A)
    fakes.page("https://inwest-b.example/start", LANDING_A.replace("Zarabiaj 12 000 zł", "Odbierz 9 500 zł"))

    first = analyze_url("https://zysk-a.example/lp/1")
    assert first.status == Analysis.Status.DONE
    assert first.result["fuse"]["edges"] == 0
    assert first.result["cluster"]["campaign"] is None

    second = analyze_url("https://inwest-b.example/start")
    assert second.status == Analysis.Status.DONE
    assert second.result["fuse"]["same_campaign"] == 1

    edge = Edge.objects.get()
    assert edge.relation == Edge.Relation.SAME_CAMPAIGN
    assert edge.decisive and edge.probability > 0.99
    kinds = {e.kind for e in edge.evidence.all()}
    assert {"ga4", "meta_pixel", "form_action", "dom_hash", "dom_minhash", "telegram"} <= kinds
    assert "domain" not in kinds  # domeny są różne i mimo to reklamy się łączą
    assert all(e.weight_bits > 0 for e in edge.evidence.all())
    # dowód prowadzi do zapisanego HTML obu stron
    ga = edge.evidence.get(kind="ga4")
    assert ga.artifact_a_id and ga.artifact_b_id and ga.artifact_a_id != ga.artifact_b_id

    campaign = Campaign.objects.get()
    cluster = second.result["cluster"]
    assert (cluster["campaign"], cluster["campaign_id"], cluster["action"], cluster["neighbours"], cluster["size"]) == (
        campaign.key, campaign.pk, "created", 1, 2,
    )
    assert cluster["operator"].startswith("O-") and cluster["operator_size"] == 2
    assert campaign.memberships.count() == 2


def test_unrelated_page_stays_alone():
    fakes.page("https://zysk-a.example/lp/1", LANDING_A)
    fakes.page("https://sklep.example/buty", OTHER)
    analyze_url("https://zysk-a.example/lp/1")
    other = analyze_url("https://sklep.example/buty")
    assert other.result["fuse"]["edges"] == 0
    assert Edge.objects.count() == 0
    assert Campaign.objects.count() == 0


def test_third_variant_joins_existing_campaign():
    for url in ("https://a.example/1", "https://b.example/2", "https://c.example/3"):
        fakes.page(url, LANDING_A)
    analyze_url("https://a.example/1")
    analyze_url("https://b.example/2")
    third = analyze_url("https://c.example/3")
    assert third.result["cluster"]["action"] == "joined"
    assert third.result["cluster"]["size"] == 3
    assert Campaign.objects.count() == 1
    assert Edge.objects.count() == 3


def test_events_are_ordered_and_cover_every_stage():
    fakes.page("https://zysk-a.example/lp/1", LANDING_A)
    analysis = analyze_url("https://zysk-a.example/lp/1")
    events = list(analysis.events.all())
    assert [e.seq for e in events] == list(range(1, len(events) + 1))
    started = [e.stage for e in events if e.status == "started"]
    assert started == pipeline.STAGES
    assert events[-1].stage == "end" and events[-1].status == "done"
    crawl = [e for e in events if e.stage == "crawl" and e.status == "info"]
    assert {e.payload["profile"] for e in crawl} == {"victim", "bot"}


def test_cloaking_white_page_becomes_a_marker():
    fakes.page("https://zysk-a.example/lp/1", LANDING_A, bot_html=OTHER)
    analysis = analyze_url("https://zysk-a.example/lp/1")
    assert analysis.result["extract"]["cloaking"] is True
    assert Marker.objects.filter(kind="white_dom_hash").count() == 1


def test_redirect_chain_domains_are_markers():
    fakes.page("https://zysk-a.example/lp/1", LANDING_A, chain=["https://go.tds-hop.example/c/123"])
    analyze_url("https://zysk-a.example/lp/1")
    assert Marker.objects.get(kind="redirect_domain").value == "tds-hop.example"
    assert Marker.objects.get(kind="domain").value == "zysk-a.example"


def test_enrichment_adds_infrastructure_and_cert_label():
    fakes.page("https://zysk-a.example/lp/1", LANDING_A, favicon=b"\x89PNG-fake-icon")
    fakes.DNS["zysk-a.example"] = {"ips": ["203.0.113.7"], "ns": ["ns1.dns.example"], "registrar": "Rejestrator Sp. z o.o."}
    WarningDomain.objects.create(domain="zysk-a.example")
    analysis = analyze_url("https://zysk-a.example/lp/1")
    kinds = set(Marker.objects.values_list("kind", flat=True))
    assert {"ip", "asn", "nameserver", "registrar", "reg_day", "favicon_hash"} <= kinds
    assert analysis.result["enrich"]["cert_pl_listed"] is True
    assert analysis.ad.labels["cert_pl"]["domain"] == "zysk-a.example"


def test_unreachable_page_does_not_fail_the_analysis():
    analysis = analyze_url("https://nie-ma-takiej.example/x")
    assert analysis.status == Analysis.Status.DONE
    assert analysis.result["crawl"]["pages"] == 0
    assert Marker.objects.filter(kind="domain", value="nie-ma-takiej.example").exists()


def test_text_only_ads_link_as_similar_without_any_landing_page():
    # Scenariusz Lead Ads: nie ma strony docelowej, zostaje narracja i osoba.
    Person.objects.create(name="Jan Testowy", wikidata_id="Q999999")
    t1 = "Jan Testowy ujawnia: Polacy zarabiają 12 000 zł miesięcznie dzięki nowej platformie. Sprawdź, zanim usuną ten film!"
    t2 = "Jan Testowy ujawnia: Polacy zarabiają 15 000 zł miesięcznie dzięki nowej platformie. Sprawdź, zanim usuną ten film!!!"
    analyze(Analysis.Kind.TEXT, t1)
    second = analyze(Analysis.Kind.TEXT, t2)
    assert second.result["crawl"]["pages"] == 0
    edge = Edge.objects.get()
    assert edge.relation == Edge.Relation.SIMILAR
    assert {e.kind for e in edge.evidence.all()} == {"text_minhash", "person_mention"}
    assert Campaign.objects.count() == 0


def test_same_article_with_appended_section_links_by_text():
    # Ten sam artykuł, ale drugi zapis ma doklejoną sekcję prawie tej samej długości.
    # Sam Jaccard spada wtedy do połowy i para nie dostawała żadnego dowodu treści.
    # Pasma LSH przy takim Jaccardzie zwykle się nie spotykają, więc kandydata daje wspólny
    # zestaw parametrów, tak jak w danych organizatora daje go tytuł strony albo silnik lejka.
    from evidence import services as markers
    from extractors import Observation
    from extractors.text import extract_text
    from similarity.service import link_ad

    article = _article(11, 600)
    first, second = Ad.objects.create(), Ad.objects.create()
    for ad, text in ((first, article), (second, article + " " + _article(12, 500))):
        markers.attach(ad, [Observation("url_param_keys", "sub1,utm_source")])
        markers.set_signature(ad, "text_minhash", extract_text(text).signature)
    link_ad(second)
    edge = Edge.objects.get()
    assert edge.relation == Edge.Relation.SIMILAR
    text = edge.evidence.get(kind="text_minhash")
    assert text.similarity > 0.9
    assert text.weight_bits >= 5


def test_shared_contact_in_text_links_ads_into_campaign():
    analyze(Analysis.Kind.TEXT, "Inwestuj z nami w akcje spółek technologicznych, napisz na https://t.me/zysk_support po szczegóły oferty")
    second = analyze(Analysis.Kind.TEXT, "Kurs języka hiszpańskiego online dla początkujących, kontakt przez https://t.me/zysk_support codziennie")
    edge = Edge.objects.get()
    assert edge.relation == Edge.Relation.SAME_CAMPAIGN
    assert edge.evidence.get(kind="telegram").decisive
    assert second.result["cluster"]["action"] == "created"


def test_rerunning_analysis_stages_is_idempotent():
    fakes.page("https://a.example/1", LANDING_A)
    fakes.page("https://b.example/2", LANDING_A)
    analyze_url("https://a.example/1")
    second = analyze_url("https://b.example/2")
    before = (Marker.objects.count(), Edge.objects.count(), Marker.objects.get(kind="ga4").ad_count)
    for stage in ("extract", "enrich", "fuse", "cluster"):
        pipeline.run_stage(str(second.pk), stage)
    assert (Marker.objects.count(), Edge.objects.count(), Marker.objects.get(kind="ga4").ad_count) == before
    assert Marker.objects.get(kind="ga4").ad_count == 2
    assert Campaign.objects.count() == 1


def test_rejected_edge_no_longer_holds_a_campaign_together():
    fakes.page("https://a.example/1", LANDING_A)
    fakes.page("https://b.example/2", LANDING_A)
    analyze_url("https://a.example/1")
    analyze_url("https://b.example/2")
    edge = Edge.objects.get()
    assert CampaignMembership.objects.count() == 2
    decisions.decide(edge.pk, Edge.Verdict.REJECTED, "shared_tool")
    # Odrzucenie jedynej krawędzi rozwiązuje grupę: obie reklamy tracą kampanię i operatora.
    assert CampaignMembership.objects.count() == 0 and OperatorMembership.objects.count() == 0
    lonely = Ad.objects.get(landing_url="https://a.example/1")
    assert assign_campaign(lonely)["neighbours"] == 0


def test_marker_shared_inside_one_campaign_does_not_lose_strength():
    # Rzadkość liczymy po niezależnych źródłach, nie po reklamach. Inaczej im większa kampania,
    # tym słabszy jej własny identyfikator i kolejne odsłony przestają się do niej przyklejać.
    topics = ["akcje spółek technologicznych", "złoto i srebro w sztabkach", "kryptowaluty dla początkujących",
              "obligacje skarbowe na dziesięć lat", "nieruchomości pod wynajem w dużym mieście", "fundusze indeksowe świata"]
    last = None
    for topic in topics:
        last = analyze(Analysis.Kind.TEXT, f"Sprawdź naszą ofertę: {topic}. Napisz do doradcy na https://t.me/zysk_support jeszcze dziś")
    assert Campaign.objects.filter(merged_into__isnull=True).count() == 1
    assert last.result["cluster"]["size"] == len(topics)
    newest = Edge.objects.order_by("-id").first()
    telegram = newest.evidence.get(kind="telegram")
    assert telegram.df == 2  # jedno źródło (kampania) plus nowa reklama
    assert telegram.weight_bits == 18
