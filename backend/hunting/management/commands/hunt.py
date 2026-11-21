from django.core.management.base import BaseCommand, CommandError

from hunting import service
from similarity.models import Operator


class Command(BaseCommand):
    help = (
        "Łowca domen: nowe domeny znanych operatorów z logów Certificate Transparency (crt.sh) i z Listy CERT Polska. "
        "Kandydaci dostają wynik wstępny bez sieci do strony, najlepsi trafiają do crawlera i są porównywani ze śladami "
        "operatora. Potwierdzona domena tworzy alert hunt_confirmed."
    )

    def add_arguments(self, parser):
        parser.add_argument("--operator", help="Klucz (O-0007) albo identyfikator operatora; domyślnie wszyscy")
        parser.add_argument("--days", type=int, default=service.DEFAULTS["days"], help="Certyfikaty wystawione w ostatnich N dniach")
        parser.add_argument("--max-queries", type=int, default=service.DEFAULTS["max_queries"], help="Najwyżej tyle zapytań do crt.sh na przebieg")
        parser.add_argument("--max-crawl", type=int, default=service.DEFAULTS["max_crawl"], help="Najwyżej tyle stron do crawlera na przebieg")
        parser.add_argument("--threshold", type=float, default=service.DEFAULTS["threshold"], help="Najniższy wynik wstępny kandydata (0..1)")
        parser.add_argument("--no-crawl", action="store_true", help="Tylko kandydaci i wynik wstępny, bez pobierania stron")

    def handle(self, *args, **options):
        operator_id = None
        if options["operator"]:
            raw = options["operator"].upper().removeprefix("O-").lstrip("0") or "0"
            if not raw.isdigit() or not Operator.objects.filter(pk=int(raw), merged_into__isnull=True).exists():
                raise CommandError(f"Nie ma takiego operatora: {options['operator']}")
            operator_id = int(raw)
        params = {
            "operator": operator_id, "days": options["days"], "max_queries": options["max_queries"],
            "max_crawl": options["max_crawl"], "threshold": options["threshold"], "crawl": not options["no_crawl"],
        }
        run = service.create_run(params, operator_id)
        self.stdout.write(f"Przebieg {run.pk}")
        try:
            stats = service.execute(str(run.pk), say=self.stdout.write)
        except Exception as exc:
            raise CommandError(f"Przebieg nie powiódł się: {type(exc).__name__}: {exc}") from exc
        summary = {k: v for k, v in stats.items() if k not in ("queries", "tokens")}
        self.stdout.write(self.style.SUCCESS(f"Gotowe: {summary}"))
