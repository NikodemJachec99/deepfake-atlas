from django.conf import settings
from django.core.management.base import BaseCommand

from ads.models import Ad
from evidence.kinds import BAND_KINDS, KINDS
from evidence.models import AdMarker
from similarity.models import CampaignMembership, Edge

BATCH = 2000


def chunks(rows: list, size: int = BATCH):
    for i in range(0, len(rows), size):
        yield rows[i : i + size]


class Command(BaseCommand):
    help = "Odbudowuje projekcję grafu w Neo4j z Postgresa. Neo4j nie jest źródłem prawdy, więc czyścimy i ładujemy od zera."

    def handle(self, *args, **options):
        from neo4j import GraphDatabase

        ads = [
            {"id": a.pk, "source": a.source, "title": a.title[:200], "landing_url": a.landing_url[:500], "listed": "cert_pl" in a.labels}
            for a in Ad.objects.all()
        ]
        # Do grafu trafiają tylko markery wspólne dla co najmniej dwóch reklam. Reszta niczego nie łączy.
        links = [
            {"ad": am.ad_id, "marker": am.marker_id, "kind": am.marker.kind, "family": KINDS[am.marker.kind].family, "value": am.marker.value[:300]}
            for am in AdMarker.objects.filter(marker__ad_count__gte=2).exclude(marker__kind__in=BAND_KINDS).select_related("marker")
        ]
        edges = [
            {"a": e.ad_a_id, "b": e.ad_b_id, "id": e.pk, "relation": e.relation, "probability": e.probability, "bits": e.bits, "verdict": e.verdict}
            for e in Edge.objects.all()
        ]
        members = [{"ad": m.ad_id, "campaign": m.campaign_id, "key": m.campaign.key} for m in CampaignMembership.objects.select_related("campaign")]

        driver = GraphDatabase.driver(settings.NEO4J_URI, auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD))
        with driver, driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")
            for label, key in (("Ad", "id"), ("Marker", "id"), ("Campaign", "id")):
                session.run(f"CREATE CONSTRAINT IF NOT EXISTS FOR (n:{label}) REQUIRE n.{key} IS UNIQUE")
            for rows in chunks(ads):
                session.run("UNWIND $rows AS r MERGE (a:Ad {id: r.id}) SET a += r", rows=rows)
            for rows in chunks(links):
                session.run(
                    "UNWIND $rows AS r MATCH (a:Ad {id: r.ad}) "
                    "MERGE (m:Marker {id: r.marker}) SET m.kind = r.kind, m.family = r.family, m.value = r.value "
                    "MERGE (a)-[:HAS_MARKER]->(m)",
                    rows=rows,
                )
            for rows in chunks(edges):
                session.run(
                    "UNWIND $rows AS r MATCH (a:Ad {id: r.a}), (b:Ad {id: r.b}) "
                    "MERGE (a)-[l:LINKED {id: r.id}]->(b) "
                    "SET l.relation = r.relation, l.probability = r.probability, l.bits = r.bits, l.verdict = r.verdict",
                    rows=rows,
                )
            for rows in chunks(members):
                session.run(
                    "UNWIND $rows AS r MATCH (a:Ad {id: r.ad}) MERGE (c:Campaign {id: r.campaign}) SET c.key = r.key MERGE (a)-[:IN_CAMPAIGN]->(c)",
                    rows=rows,
                )
            counts = session.run("MATCH (n) RETURN labels(n)[0] AS label, count(*) AS n").data()
            rels = session.run("MATCH ()-[r]->() RETURN type(r) AS type, count(*) AS n").data()
        self.stdout.write(self.style.SUCCESS(f"Neo4j: węzły {counts}, relacje {rels}"))
