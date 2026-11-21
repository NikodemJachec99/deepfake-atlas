"""Dociąga certyfikaty z crt.sh dla domen, dla których import nie dostał odpowiedzi.

Nieudana odpowiedź nie trafia do pamięci podręcznej, więc wystarczy zapytać o domeny bez świeżego
wpisu. Nowe markery dopinamy do wszystkich reklam domeny i przeliczamy ich krawędzie i grupy,
tak jak robi to analiza. Pełny ponowny import nie jest potrzebny.
"""

from collections import defaultdict
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from ads.models import Ad
from enrichment import crtsh
from enrichment.models import CertLookup
from evidence import services as markers
from evidence.models import AdMarker
from similarity import service as linking
from workflows.pipeline import enricher


class Command(BaseCommand):
    help = "Dociąga crt.sh dla domen bez zapisanej odpowiedzi, dopina tls_serial i przelicza krawędzie tych reklam."

    def add_arguments(self, parser):
        parser.add_argument("--domain", action="append", default=[], help="Tylko ta domena (można podać kilka razy).")
        parser.add_argument("--all", action="store_true", help="Także domeny ze świeżą odpowiedzią (z pamięci, bez pytania crt.sh).")

    def handle(self, *args, **options):
        ads_by_domain: dict[str, set[int]] = defaultdict(set)
        rows = AdMarker.objects.filter(marker__kind="domain").values_list("marker__value", "ad_id")
        for domain, ad_id in rows:
            ads_by_domain[domain].add(ad_id)
        domains = sorted(ads_by_domain)
        if options["domain"]:
            domains = [d for d in domains if d in set(options["domain"])]
        if not options["all"]:
            fresh = timezone.now() - timedelta(days=crtsh.CACHE_DAYS)
            known = set(CertLookup.objects.filter(domain__in=domains, fetched_at__gte=fresh).values_list("domain", flat=True))
            domains = [d for d in domains if d not in known]
        if not domains:
            self.stdout.write("Wszystkie domeny mają odpowiedź crt.sh.")
            return

        source = enricher()
        touched: set[int] = set()
        done: list[str] = []
        for i, domain in enumerate(domains):
            certs = crtsh.lookup(domain, source)
            if certs is None:
                rest = domains[i:]
                self.stdout.write(self.style.WARNING(f"crt.sh nie odpowiedział przy {domain}. Bez odpowiedzi zostaje {len(rest)}: {', '.join(rest)}"))
                break
            observations, neighbours = crtsh.observations(domain, certs)
            added = 0
            for ad in Ad.objects.filter(pk__in=ads_by_domain[domain]):
                new = markers.attach(ad, observations)
                if new:
                    touched.add(ad.pk)
                    added += new
            done.append(domain)
            extra = f", inne domeny z certyfikatu: {', '.join(neighbours)}" if neighbours else ""
            self.stdout.write(f"{domain}: {len(certs)} certyfikatów, {added} nowych markerów{extra}")

        for ad in Ad.objects.filter(pk__in=touched).order_by("pk"):
            linking.link_ad(ad)
        for ad in Ad.objects.filter(pk__in=touched).order_by("pk"):
            linking.assign_campaign(ad)
            linking.assign_operator(ad)
        self.stdout.write(self.style.SUCCESS(f"Domeny z odpowiedzią: {len(done)} z {len(domains)}. Przeliczone reklamy: {len(touched)}."))
