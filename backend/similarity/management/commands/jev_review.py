"""Sugestie przeglądu krawędzi z zewnętrznej usługi Jev. Doradczo, bez zmian krawędzi, dowodów i grup.

Limity jednego uruchomienia: liczba zapytań (`JEV_MAX_REQUESTS`) i budżet w USD (`JEV_BUDGET_USD`, liczony
z `usage.input_tokens` i `JEV_PRICE_PER_MTOK`). Zły klucz (401) albo brak środków (402) kończy przebieg od razu.
Limit zapytań (429) i przeciążenie (529): czekamy wskazany czas, najwyżej `MAX_WAIT_S`, i próbujemy dalej.
"""

import time
from collections import Counter

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from similarity import assist
from similarity.models import Edge

MAX_LIMIT = 1000
STOP_AFTER_FAILURES = 3  # usługa leży albo ciągle odmawia: nie męczymy jej resztą krawędzi
MAX_WAIT_S = 30.0
STOP_NOW = {"unauthorized", "payment"}
RETRYABLE = {"unavailable", "timeout", "rate_limited"}


class Command(BaseCommand):
    help = "Pyta usługę Jev, które krawędzie wymagają przeglądu człowieka. Wymaga JEV_MODE=shadow|on, JEV_MODEL i TYPESAFE_API_KEY."

    def add_arguments(self, parser):
        parser.add_argument("--edge", type=int, action="append", default=[], help="Tylko ta krawędź (można kilka razy).")
        parser.add_argument("--relation", action="append", default=[], help="Tylko krawędzie tej relacji.")
        parser.add_argument("--limit", type=int, default=100, help=f"Najwyżej tyle krawędzi (do {MAX_LIMIT}).")

    def handle(self, *args, **options):
        try:
            client = assist.JevClient(assist.Config.from_settings())
        except assist.AssistDisabled as exc:
            raise CommandError(str(exc)) from exc
        max_requests = max(1, int(getattr(settings, "JEV_MAX_REQUESTS", 100)))
        budget = float(getattr(settings, "JEV_BUDGET_USD", 0.10))
        price = float(getattr(settings, "JEV_PRICE_PER_MTOK", 0.042))

        edges = Edge.objects.order_by("pk")
        if options["edge"]:
            edges = edges.filter(pk__in=options["edge"])
        if options["relation"]:
            edges = edges.filter(relation__in=options["relation"])
        limit = min(max(1, min(options["limit"], MAX_LIMIT)), max_requests)

        counts: Counter = Counter()
        failures, tokens, sent = 0, 0, 0
        for edge in edges[:limit]:
            if tokens * price / 1e6 >= budget:
                self.stdout.write(self.style.WARNING(f"Budżet {budget:.4f} USD wyczerpany, przerywam."))
                break
            suggestion = assist.review_edge(edge, client)
            sent += 1
            tokens += suggestion.input_tokens or 0
            counts[suggestion.status if suggestion.status != "ok" else f"ok:{suggestion.answer}"] += 1
            if suggestion.status in STOP_NOW:
                self.stdout.write(self.style.WARNING(f"Jev: {suggestion.error}. Przerywam."))
                break
            failures = failures + 1 if suggestion.status in RETRYABLE else 0
            if failures >= STOP_AFTER_FAILURES:
                self.stdout.write(self.style.WARNING(f"Jev nie odpowiada albo odmawia ({suggestion.error}), przerywam."))
                break
            if suggestion.status == "rate_limited":
                wait = getattr(client, "last_retry_after", None)
                time.sleep(min(MAX_WAIT_S, wait if wait is not None else 2.0 ** failures))
        cost = tokens * price / 1e6
        self.stdout.write(
            f"Sugestie ({client.config.model}, {assist.QUESTION_VERSION}): {dict(sorted(counts.items()))}; "
            f"zapytań {sent}, tokenów wejściowych {tokens}, koszt ok. {cost:.6f} USD"
        )
