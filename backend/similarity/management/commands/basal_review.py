"""Sugestie przeglądu krawędzi z lokalnego modelu basal. Doradczo, bez zmian krawędzi, dowodów i grup."""

from collections import Counter

from django.core.management.base import BaseCommand, CommandError

from similarity import assist
from similarity.models import Edge

MAX_LIMIT = 1000
STOP_AFTER_UNAVAILABLE = 3  # usługa leży: nie męczymy jej resztą krawędzi


class Command(BaseCommand):
    help = "Pyta lokalny model basal, które krawędzie wymagają przeglądu człowieka. Wymaga BASAL_MODE=shadow|on i BASAL_URL."

    def add_arguments(self, parser):
        parser.add_argument("--edge", type=int, action="append", default=[], help="Tylko ta krawędź (można kilka razy).")
        parser.add_argument("--relation", action="append", default=[], help="Tylko krawędzie tej relacji.")
        parser.add_argument("--limit", type=int, default=100, help=f"Najwyżej tyle krawędzi (do {MAX_LIMIT}).")

    def handle(self, *args, **options):
        try:
            client = assist.BasalClient(assist.Config.from_settings())
        except assist.AssistDisabled as exc:
            raise CommandError(str(exc)) from exc
        edges = Edge.objects.order_by("pk")
        if options["edge"]:
            edges = edges.filter(pk__in=options["edge"])
        if options["relation"]:
            edges = edges.filter(relation__in=options["relation"])
        counts: Counter = Counter()
        down = 0
        for edge in edges[: max(1, min(options["limit"], MAX_LIMIT))]:
            suggestion = assist.review_edge(edge, client)
            counts[suggestion.status if suggestion.status != "ok" else f"ok:{suggestion.answer}"] += 1
            down = down + 1 if suggestion.status in ("unavailable", "timeout") else 0
            if down >= STOP_AFTER_UNAVAILABLE:
                self.stdout.write(self.style.WARNING(f"basal nie odpowiada ({suggestion.error}), przerywam."))
                break
        self.stdout.write(f"Sugestie ({client.config.model}, {assist.QUESTION_VERSION}): {dict(sorted(counts.items()))}")
