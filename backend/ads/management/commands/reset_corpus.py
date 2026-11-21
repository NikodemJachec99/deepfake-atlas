from django.core.management.base import BaseCommand, CommandError
from django.core.management.color import no_style
from django.db import connection

from ads.models import Ad, Advertiser, Analysis
from enrichment.models import DomainRecord
from evidence.models import Artifact, Marker
from similarity.models import Campaign, Operator


class Command(BaseCommand):
    help = "Czyści korpus: reklamy, markery, krawędzie, kampanie, operatorów i analizy. Zostają Lista Ostrzeżeń i baza osób."

    def add_arguments(self, parser):
        parser.add_argument("--yes", action="store_true", help="Potwierdzenie. Bez niego polecenie nic nie usuwa.")

    def handle(self, *args, **options):
        if not options["yes"]:
            raise CommandError("To usuwa cały korpus. Uruchom z --yes, jeśli na pewno tego chcesz.")
        counts = {}
        models = (Analysis, Ad, Advertiser, Marker, Campaign, Operator, Artifact, DomainRecord)
        # Krawędzie, przypisania i zdarzenia znikają kaskadowo razem z reklamami i analizami.
        for model in models:
            counts[model.__name__] = model.objects.all().delete()[0]
        # Numeracja od nowa, żeby klucze kampanii i operatorów zaczynały się od K-0001 i O-0001.
        with connection.cursor() as cursor:
            for statement in connection.ops.sequence_reset_sql(no_style(), models):
                cursor.execute(statement)
        self.stdout.write(self.style.SUCCESS(f"Usunięto: {counts}"))
