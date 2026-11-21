"""Co sprawdzić dalej: wskazówki dla analityka z brakujących dowodów konkretnej pary.

Wskazówki są deterministyczne i wynikają z reguł silnika (`fusion.score_pair`) oraz z tego, jakie
materiały mamy przy obu reklamach. Nie zgadujemy, czy brakujący dowód istnieje, nie oceniamy
prawdopodobieństwa i nie pobieramy niczego ze stron oszustów. Kolejność to kolejność reguł,
nie ocena skuteczności.
"""

from ads.models import Ad
from evidence.kinds import KINDS
from evidence.models import AdMarker
from similarity import fusion, simulation
from similarity.models import Edge

PAGE_EXT = (".html", ".htm", ".mhtml")
NOTE = "Wskazówki wynikają z reguł silnika i z dostępnych materiałów. Kolejność to kolejność reguł, nie ocena skuteczności."
OPERATOR_TRACES = "identyfikator strony w panelu lejka, piksel, konto reklamowe, własny host zasobów, certyfikat albo adres IP"


def materials(ad: Ad) -> dict:
    sources = [str(s).lower() for s in ad.raw.get("sources", [])]
    captured = ad.source == "capture"
    return {
        "har": any(s.endswith(".har") for s in sources),
        "page": any(s.endswith(PAGE_EXT) for s in sources) or (not captured and bool(ad.landing_url)),
        "creative": bool(ad.raw.get("creatives")),
        "captured": captured,
        "library_ids": list(
            AdMarker.objects.filter(ad=ad, marker__kind="meta_ad_ref").values_list("marker__value", flat=True)[:3]
        ),
    }


def side(ad: Ad, letter: str) -> str:
    return f"{letter} (reklama #{ad.pk})"


def suggestion(code: str, missing: str, why: str, next_step: str, limitation: str, rule: str, sides: list[str] | None = None) -> dict:
    return {"code": code, "missing": missing, "why": why, "next_step": next_step, "limitation": limitation, "rule": rule, "sides": sides or []}


def necessary_supports(rows, base: fusion.PairResult) -> list[dict]:
    """Potwierdzenia, bez których krawędź traci wspólne źródło. Każde sprawdzamy z osobna."""
    if not base.checks.get("same_source"):
        return []
    corpus_n = max((r.corpus_n for r in rows), default=0)
    groups: dict[str, list] = {}
    for row in rows:
        kind = KINDS.get(row.kind)
        if kind is None or kind.motif:
            continue
        groups.setdefault("kit" if kind.kit else row.family, []).append(row)
    found = []
    for group, members in sorted(groups.items(), key=lambda g: -sum(r.weight_bits for r in g[1])):
        keep = [r for r in rows if r not in members]
        after = simulation.score(keep, corpus_n)
        if not after.checks.get("same_source"):
            top = max(members, key=lambda r: r.weight_bits)
            label = "ślady silnika lejka" if group == "kit" else KINDS[top.kind].label.lower()
            found.append({"label": label, "value": top.value_a[:80], "after": after.relation})
    return found


def suggestions_for(edge: Edge) -> dict:
    rows = list(edge.evidence.all())
    corpus_n = max((r.corpus_n for r in rows), default=0)
    base = simulation.score(rows, corpus_n)
    checks = base.checks
    a, b = edge.ad_a, edge.ad_b
    mat = {"A": materials(a), "B": materials(b)}
    ads = {"A": a, "B": b}
    out = []

    needed = necessary_supports(rows, base)
    if needed:
        parts = "; ".join(f"bez śladu \"{n['label']}\" ({n['value']}) relacja to {simulation.RELATION_LABELS[n['after']]}" for n in needed)
        out.append(suggestion(
            "single_support",
            "niezależne potwierdzenie wspólnego źródła, które utrzyma się bez każdego pojedynczego śladu",
            f"Wspólne źródło trzyma się na śladach, z których każdy jest konieczny: {parts}.",
            f"Poszukać drugiego, niezależnego śladu konta lub infrastruktury: {OPERATOR_TRACES}.",
            "Jeden rzadki ślad bywa wystarczający. Wskazówka mówi o kruchości hipotezy, nie o tym, że jest błędna.",
            "fusion: wspólne źródło wymaga markera rozstrzygającego albo dwóch niezależnych potwierdzeń",
        ))

    both_har = mat["A"]["har"] and mat["B"]["har"]
    if base.relation == "similar" and checks.get("kit_path_bits", 0) >= fusion.FAMILY_MIN_BITS and not checks.get("same_source"):
        out.append(suggestion(
            "engine_without_account",
            "ślad konta operatora wspólny dla obu stron",
            "Wspólne są ścieżki zaplecza, czyli ten sam silnik lejka. Silnik mógł kupić każdy, więc to podobieństwo, nie wspólne źródło.",
            f"Porównać ślady konta z HAR obu stron: {OPERATOR_TRACES}.",
            "Oba HAR-y już przeanalizowano i takiego śladu nie ma. Nowy dowód może dać tylko inne przechwycenie."
            if both_har else "Bez HAR po obu stronach tego porównania nie da się zrobić.",
            "fusion: ślady jednego silnika lejka to jedno potwierdzenie",
        ))
    if base.relation == "similar" and checks.get("story_bits", 0) >= fusion.SIMILAR_MIN_BITS and not checks.get("backed"):
        out.append(suggestion(
            "copy_without_backend",
            "ślad zaplecza wspólny dla obu stron",
            "Zgadza się treść, tytuł albo obrazy, a te da się skopiować. Wspólnego źródła dowodzi dopiero zaplecze.",
            f"Porównać zaplecze obu stron z HAR: {OPERATOR_TRACES}.",
            "Oba HAR-y są i nie dzielą zaplecza: to raczej kopia materiału niż wspólne źródło."
            if both_har else "Bez HAR po obu stronach zaplecza nie da się porównać.",
            "fusion: treść i obrazy nie dowodzą wspólnego źródła",
        ))

    no_har = [k for k in ("A", "B") if mat[k]["captured"] and not mat[k]["har"] and mat[k]["page"]]
    if no_har and base.relation != "same_campaign":
        out.append(suggestion(
            "har_missing",
            "zapis ruchu sieciowego (HAR) strony",
            "HAR daje ścieżki zaplecza, identyfikatory z panelu lejka i hosty zasobów, czyli ślady, które rozstrzygają o wspólnym źródle. "
            "Bez niego para może wyglądać na słabo powiązaną z braku materiału, a nie z powodu różnych źródeł.",
            "Zdobyć HAR tej strony: z archiwum NASK albo z narzędzi deweloperskich przeglądarki w izolowanym środowisku.",
            "Strona mogła już zniknąć albo pokazywać białą stronę dla moderacji. System nie pobiera stron oszustów z interfejsu.",
            "materiały: brak pliku HAR przy reklamie",
            [side(ads[k], k) for k in no_har],
        ))

    shot_only = [k for k in ("A", "B") if mat[k]["creative"] and not mat[k]["page"] and not mat[k]["har"]]
    if shot_only:
        ids = sorted({i for k in shot_only for i in mat[k]["library_ids"]})
        out.append(suggestion(
            "screenshot_only",
            "strona docelowa reklamy",
            "Ze zrzutu reklamy mamy tylko tekst z OCR, nazwę reklamodawcy i hash kreacji. Ślady zaplecza są dopiero na stronie docelowej.",
            f"Odczytać adres docelowy z Biblioteki Reklam Mety po numerze {', '.join(ids)}." if ids else "Ustalić adres docelowy reklamy i zapisać stronę razem z HAR.",
            "Biblioteka Reklam przez API wymaga tokenu, a reklama mogła zostać usunięta.",
            "materiały: przy reklamie jest tylko zrzut ekranu",
            [side(ads[k], k) for k in shot_only],
        ))

    no_page = [k for k in ("A", "B") if not mat[k]["page"] and k not in shot_only]
    if base.relation == "same_operator" and checks.get("story_bits", 0) < fusion.SIMILAR_MIN_BITS and no_page:
        out.append(suggestion(
            "story_unknown",
            "treść strony po jednej ze stron",
            "Wspólne źródło jest, ale bez treści nie da się odróżnić tej samej kampanii od innej kampanii tego operatora.",
            "Dołączyć zapis strony z przeglądarki (HTML).",
            "Operator często zmienia treść, więc nawet z zapisem wynik może zostać \"ten sam operator\".",
            "fusion: ta sama kampania wymaga zgodnej opowieści",
            [side(ads[k], k) for k in no_page],
        ))

    warnings = []
    if edge.verdict == Edge.Verdict.REJECTED:
        warnings.append("Analityk odrzucił tę krawędź. Wskazówki dotyczą dowodów, decyzja zostaje bez zmian.")
    return {
        "edge": edge.pk,
        "relation": base.relation,
        "materials": {k: {key: v for key, v in mat[k].items() if key != "captured"} for k in mat},
        "suggestions": out,
        "note": NOTE,
        "warnings": warnings,
    }
