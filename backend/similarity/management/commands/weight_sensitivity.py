"""Wrażliwość wyników na wagi modelu: jak zmieniają się relacje krawędzi, gdy wagi są inne niż eksperckie.

Przeliczamy zapisane dowody każdej krawędzi tym samym silnikiem (`simulation.score`), zmieniając po kolei:
siłę dowodu każdego typu markera osobno (×0,5 i ×1,5, z tym samym mnożnikiem dla limitu), siłę wszystkich
naraz, szansę wstępną (×0,1 i ×10) oraz progi reguły (pewność 0,8 i 0,95, niezależne potwierdzenie od 3
i od 5 bitów). Niczego nie zapisuje.
"""

import json
from collections import Counter
from contextlib import contextmanager

from django.core.management.base import BaseCommand

from similarity import fusion, simulation
from similarity.models import Edge

SAME_SOURCE = ("same_campaign", "same_operator")


@contextmanager
def scaled(kinds: set[str] | None, factor: float):
    """Siła dowodu wybranych typów (None = wszystkich) pomnożona przez factor."""
    exact, soft = fusion.exact_bits, fusion.soft_bits

    def exact_scaled(kind, df, corpus_n):
        bits = exact(kind, df, corpus_n)
        return bits * factor if kinds is None or kind in kinds else bits

    def soft_scaled(kind, similarity):
        bits = soft(kind, similarity)
        return bits * factor if kinds is None or kind in kinds else bits

    fusion.exact_bits, fusion.soft_bits = exact_scaled, soft_scaled
    try:
        yield
    finally:
        fusion.exact_bits, fusion.soft_bits = exact, soft


@contextmanager
def setting(name: str, value):
    old = getattr(fusion, name)
    setattr(fusion, name, value)
    try:
        yield
    finally:
        setattr(fusion, name, old)


class Command(BaseCommand):
    help = "Wrażliwość relacji krawędzi na wagi i progi modelu. Tylko odczyt."

    def add_arguments(self, parser):
        parser.add_argument("--source", default="capture", help="Krawędzie między reklamami z tego źródła (domyślnie materiały spraw)")
        parser.add_argument("--json", action="store_true", help="Wynik jako JSON")

    def handle(self, *args, **options):
        edges = list(
            Edge.objects.filter(ad_a__source=options["source"], ad_b__source=options["source"]).select_related("ad_a", "ad_b").prefetch_related("evidence")
        )
        label = {e.pk: f"{e.ad_a.labels.get('bundle', '')}/{e.ad_a.labels.get('case', e.ad_a_id)} / {e.ad_b.labels.get('bundle', '')}/{e.ad_b.labels.get('case', e.ad_b_id)}" for e in edges}
        rows = {e.pk: list(e.evidence.all()) for e in edges}
        corpus = {pk: max((r.corpus_n for r in rs), default=0) for pk, rs in rows.items()}

        def relations() -> dict[int, str | None]:
            return {pk: simulation.score(rs, corpus[pk]).relation for pk, rs in rows.items()}

        base = relations()
        base_same = {pk for pk, r in base.items() if r in SAME_SOURCE}

        def diff(name: str) -> dict:
            now = relations()
            changed = {pk: (base[pk], now[pk]) for pk in base if now[pk] != base[pk]}
            lost = sum(1 for pk in base_same if now[pk] not in SAME_SOURCE)
            gained = sum(1 for pk, r in now.items() if r in SAME_SOURCE and pk not in base_same)
            return {"scenario": name, "changed": len(changed), "lost_same_source": lost, "gained_same_source": gained,
                    "transitions": dict(Counter(f"{a}→{b}" for a, b in changed.values())),
                    "same_source_changes": sorted(f"{label[pk]}: {a}→{b}" for pk, (a, b) in changed.items() if a in SAME_SOURCE or b in SAME_SOURCE)}

        results = []
        kinds = sorted({r.kind for rs in rows.values() for r in rs})
        for factor in (0.5, 1.5):
            with scaled(None, factor):
                results.append(diff(f"wszystkie typy ×{factor}"))
            for kind in kinds:
                with scaled({kind}, factor):
                    result = diff(f"{kind} ×{factor}")
                if result["changed"]:
                    results.append(result)
        for value in (1e-5, 1e-3):
            with setting("PRIOR", value):
                results.append(diff(f"szansa wstępna {value:g}"))
        for value in (0.8, 0.95):
            with setting("SAME_PROBABILITY", value):
                results.append(diff(f"próg pewności {value}"))
        for value in (3.0, 5.0):
            with setting("FAMILY_MIN_BITS", value):
                results.append(diff(f"niezależne potwierdzenie od {value:g} bitów"))

        summary = {"edges": len(edges), "same_source": len(base_same), "relations": dict(Counter(base.values())), "scenarios": results,
                   "kinds_checked": len(kinds)}
        if options["json"]:
            self.stdout.write(json.dumps(summary, ensure_ascii=False, indent=1))
            return
        self.stdout.write(f"krawędzi: {len(edges)}, wspólne źródło: {len(base_same)}, relacje: {summary['relations']}, typów markerów: {len(kinds)}")
        for r in results:
            self.stdout.write(f"  {r['scenario']:<45} zmian {r['changed']:>3}  utrata wspólnego źródła {r['lost_same_source']:>3}  nowe {r['gained_same_source']:>3}  {r['transitions']}")
            for change in r["same_source_changes"]:
                self.stdout.write(f"      {change}")
