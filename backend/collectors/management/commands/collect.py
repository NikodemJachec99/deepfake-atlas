from django.conf import settings
from django.core.management.base import BaseCommand

from collectors.registry import run
from workflows import pipeline, runner


class Command(BaseCommand):
    help = "Uruchamia kolektor źródła. Przykłady: collect cert_pl | collect microsoft --query inwestycje --run"

    def add_arguments(self, parser):
        parser.add_argument("collector", choices=["cert_pl", "cert_pl_history", "microsoft", "meta"])
        parser.add_argument("--query", default="")
        parser.add_argument("--limit", type=int, default=200)
        parser.add_argument("--year", type=int)
        parser.add_argument("--no-analyze", action="store_true", help="Tylko zapisz reklamy, bez tworzenia analiz")
        parser.add_argument("--run", action="store_true", help="Wykonaj analizy w tym procesie zamiast zlecać je Temporalowi")

    def handle(self, *args, **options):
        params = {"query": options["query"], "limit": options["limit"], "analyze": not options["no_analyze"]}
        if options["year"]:
            params["year"] = options["year"]
        result = run(options["collector"], params)
        analyses = result.pop("analyses")
        self.stdout.write(self.style.SUCCESS(f"{options['collector']}: {result}, analizy: {len(analyses)}"))
        if not analyses:
            return
        if settings.ANALYSIS_RUNNER == "temporal" and not options["run"]:
            for analysis_id in analyses:
                runner.start(analysis_id)
            self.stdout.write(self.style.SUCCESS(f"Zlecono Temporalowi analiz: {len(analyses)}"))
        else:
            for analysis_id in analyses:
                pipeline.run_all(analysis_id)
            self.stdout.write(self.style.SUCCESS(f"Wykonano analiz: {len(analyses)}"))
