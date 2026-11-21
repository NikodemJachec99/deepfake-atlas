from collections import defaultdict
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db.models import Q

from ads.models import Ad
from collectors import bundle
from similarity.models import Edge
from workflows import pipeline


class Command(BaseCommand):
    help = "Importuje paczkę przechwyceń (katalog spraw: zapisane strony, HAR, zrzuty) i od razu ją analizuje."

    def add_arguments(self, parser):
        parser.add_argument("path", help="Katalog paczki albo pojedynczej sprawy")
        parser.add_argument("--name", default="nask", help="Nazwa paczki, trafia do identyfikatorów reklam")

    def handle(self, *args, **options):
        name = options["name"]
        directories = bundle.case_dirs(Path(options["path"]))
        analyses = []
        for directory in directories:
            created = bundle.import_case(directory, bundle=name)
            self.stdout.write(f"Sprawa {directory.name}: stron {len(created)}")
            analyses += created
        for analysis in analyses:
            pipeline.run_all(str(analysis.pk))
        # Reklama analizowana wcześniej nie widziała późniejszych. Drugi przebieg łączenia domyka krawędzie i grupy.
        for analysis in analyses:
            for stage in ("fuse", "cluster"):
                pipeline.run_stage(str(analysis.pk), stage)
        self.report(name)

    def report(self, name: str) -> None:
        ads = list(Ad.objects.filter(labels__bundle=name).select_related("membership__campaign", "operator_membership__operator").order_by("id"))
        write = self.stdout.write
        write(self.style.SUCCESS(f"\nPaczka {name}: {len(ads)} stron z {len({a.labels.get('case') for a in ads})} spraw"))
        by_operator = defaultdict(list)
        for ad in ads:
            campaign = ad.membership.campaign.key if hasattr(ad, "membership") else "-"
            operator = ad.operator_membership.operator.key if hasattr(ad, "operator_membership") else "-"
            listed = "CERT" if "cert_pl" in ad.labels else ""
            by_operator[operator].append(ad)
            write(f"  #{ad.pk:<4} sprawa {ad.labels.get('case', '?'):<3} {operator:<7} {campaign:<7} {listed:<5} {ad.external_id.split('/', 2)[-1][:38]:<38} {ad.title[:44]}")

        write("\nPowiązania między różnymi sprawami:")
        own = {a.pk for a in ads}
        edges = Edge.objects.filter(Q(ad_a_id__in=own) | Q(ad_b_id__in=own)).select_related("ad_a", "ad_b").order_by("-bits")

        def tag(ad) -> str:
            return f"{ad.labels.get('bundle', ad.source)}/{ad.labels.get('case', ad.pk)}"

        cross = [e for e in edges if tag(e.ad_a) != tag(e.ad_b)]
        for edge in cross:
            top = ", ".join(f"{ev.kind} {ev.weight_bits:.1f}" for ev in edge.evidence.all()[:4])
            write(f"  {tag(edge.ad_a):<16} <-> {tag(edge.ad_b):<16} {edge.relation:<14} p={edge.probability:.3f} bity={edge.bits:5.1f}  [{top}]")
        if not cross:
            write("  brak")
