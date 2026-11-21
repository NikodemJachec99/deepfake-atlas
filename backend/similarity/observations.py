"""Porównanie dwóch obserwacji stron offline: ten sam adres, inna treść?

Wejście to tylko to, co już jest w bazie: zapis obserwacji z importu (`Ad.raw["observation"]`),
sygnatury treści, szablonu i obrazów oraz markery. Niczego nie pobieramy z sieci i nie zmieniamy
krawędzi. Różnica treści pod tym samym adresem to obserwacja. Cloaking jest jedną z hipotez obok
jednorazowego tokenu, innego kontekstu przeglądarki i zmiany w czasie.

Progi (nie są wykalibrowaną pewnością, tylko opisem, jak czytać liczby):
- treść i szablon co najmniej 0,9: "identyczne albo prawie identyczne",
- treść co najmniej 0,5 albo szablon co najmniej 0,6: "podobne",
- poniżej: "istotnie różne",
- brak sygnatury treści i szablonu po którejś stronie: "za mało danych".
"""

from datetime import datetime

from django.db.models import Q

from ads.models import Ad, Analysis
from evidence import store
from evidence.kinds import KINDS
from evidence.models import AdMarker, AdSignature
from extractors import images, minhash
from extractors.html import extract_page
from extractors.url import redact_url
from similarity.models import Edge

SAME_TEXT, SAME_DOM = 0.9, 0.9
EXCERPT_CHARS = 300
SIMILAR_TEXT, SIMILAR_DOM = 0.5, 0.6
TRACKER_KINDS = {code for code, k in KINDS.items() if k.family == "track" and code not in ("asset_host", "script_host")}
SIMILARITY = {"page_text_minhash": minhash.text_similarity, "dom_minhash": minhash.similarity, "image_set": images.set_similarity}
URL_MATCH_LABELS = {
    "exact": "identyczny adres",
    "normalized": "ten sam adres po normalizacji",
    "domain": "tylko ta sama domena",
    "different": "różne domeny",
    "unknown": "adres nieznany",
}
VERDICT_LABELS = {
    "identical": "identyczne albo prawie identyczne",
    "similar": "podobne",
    "different": "istotnie różne",
    "insufficient": "za mało danych",
}


def observation(ad: Ad) -> dict:
    stored = ad.raw.get("observation") if isinstance(ad.raw, dict) else None
    return stored or {}


def url_match(a: dict, b: dict) -> str:
    if not a.get("exact_url") or not b.get("exact_url"):
        return "unknown"
    if a["exact_url"] == b["exact_url"]:
        return "exact"
    if a.get("normalized_url") and a.get("normalized_url") == b.get("normalized_url"):
        return "normalized"
    if a.get("domain") and a.get("domain") == b.get("domain"):
        return "domain"
    return "different"


def _parse(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None
    except ValueError:
        return None


def _html_sha(ad: Ad) -> str | None:
    analysis = Analysis.objects.filter(ad=ad).order_by("-created_at").first()
    state = analysis.state if analysis else {}
    return ((state.get("pages") or {}).get("victim") or {}).get("html_sha")


def text_excerpt(ad: Ad) -> dict | None:
    """Krótki fragment widocznego tekstu z zapisanego HTML strony, jako zwykły tekst. Bez pobierania strony,
    bez znaczników. Adresy w tekście mają zredagowane sekrety. Brak zapisu strony daje null."""
    sha = _html_sha(ad)
    if not sha:
        return None
    try:
        html = store.get(sha).decode("utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        return None
    text = " ".join(extract_page(html, ad.landing_url or "").visible_text.split())
    if not text:
        return None
    text = " ".join(redact_url(word) if word.startswith(("http://", "https://")) else word for word in text.split())
    cut = text[:EXCERPT_CHARS]
    if len(text) > EXCERPT_CHARS:
        cut = cut.rsplit(" ", 1)[0] + " …"
    return {"text": cut, "chars": len(text), "source": "zapis HTML strony z przechwycenia", "artifact": sha}


def side(ad: Ad, obs: dict) -> dict:
    return {
        "ad": ad.pk,
        "external_id": ad.external_id,
        "title": ad.title[:200],
        "text_excerpt": text_excerpt(ad),
        "exact_url": obs.get("exact_url", ""),
        "captured_at": obs.get("captured_at") or None,
        "time_source": obs.get("time_source") or None,
        "context": obs.get("context") or None,
        "hosts": obs.get("hosts", []),
        "sources": list(ad.raw.get("sources", [])) if isinstance(ad.raw, dict) else [],
        "creatives": list(ad.raw.get("creatives", [])) if isinstance(ad.raw, dict) else [],
    }


def compare(a: Ad, b: Ad) -> dict:
    obs_a, obs_b = observation(a), observation(b)
    limitations = ["Kontekst odbiorcy (moderacja, ofiara) jest nieznany. Różnica treści pod jednym adresem to obserwacja, nie dowód cloakingu."]
    if not obs_a or not obs_b:
        limitations.append("Przy co najmniej jednej reklamie brak zapisu obserwacji (import sprzed tej funkcji albo materiał bez strony). Wynik opiera się na tym, co zostało.")

    match = url_match(obs_a, obs_b)
    when_a, when_b = _parse(obs_a.get("captured_at", "")), _parse(obs_b.get("captured_at", ""))
    gap = abs((when_b - when_a).total_seconds()) if when_a and when_b and (when_a.tzinfo is None) == (when_b.tzinfo is None) else None
    if gap is None:
        limitations.append("Przynajmniej jedna data przechwycenia jest nieznana, więc nie wiadomo, czy strony widziano w tym samym czasie.")

    sigs: dict[int, dict[str, list[int]]] = {a.pk: {}, b.pk: {}}
    for sig in AdSignature.objects.filter(ad_id__in=[a.pk, b.pk], kind__in=SIMILARITY):
        sigs[sig.ad_id][sig.kind] = sig.values
    content = {}
    for kind, fn in SIMILARITY.items():
        if kind in sigs[a.pk] and kind in sigs[b.pk]:
            content[kind] = round(fn(sigs[a.pk][kind], sigs[b.pk][kind]), 3)
        else:
            content[kind] = None

    trackers: dict[int, set[str]] = {a.pk: set(), b.pk: set()}
    for ad_id, kind, value in AdMarker.objects.filter(ad_id__in=[a.pk, b.pk], marker__kind__in=TRACKER_KINDS).values_list("ad_id", "marker__kind", "marker__value"):
        trackers[ad_id].add(f"{KINDS[kind].label}: {value}")
    hosts_a, hosts_b = set(obs_a.get("hosts", [])), set(obs_b.get("hosts", []))

    text, dom = content["page_text_minhash"], content["dom_minhash"]
    if text is None and dom is None:
        verdict = "insufficient"
    elif (text or 0) >= SAME_TEXT and (dom is None or dom >= SAME_DOM):
        verdict = "identical"
    elif (text or 0) >= SIMILAR_TEXT or (dom or 0) >= SIMILAR_DOM:
        verdict = "similar"
    else:
        verdict = "different"

    differences = []
    if a.title and b.title and a.title.strip().lower() != b.title.strip().lower():
        differences.append(f"Inny tytuł strony: \"{a.title[:80]}\" i \"{b.title[:80]}\".")
    if a.title and b.title and a.title.strip().lower() == b.title.strip().lower() and verdict == "different":
        differences.append("Ten sam tytuł, ale treść różna: zgodny tytuł bywa mylący.")
    only_a, only_b = sorted(trackers[a.pk] - trackers[b.pk]), sorted(trackers[b.pk] - trackers[a.pk])
    if only_a or only_b:
        differences.append(f"Trackery tylko po stronie A: {len(only_a)}, tylko po stronie B: {len(only_b)}.")
    if hosts_a and hosts_b and hosts_a != hosts_b:
        differences.append(f"Hosty w ruchu sieciowym: {len(hosts_a & hosts_b)} wspólnych, {len(hosts_a - hosts_b)} tylko w A, {len(hosts_b - hosts_a)} tylko w B.")
    ctx_a, ctx_b = obs_a.get("context") or {}, obs_b.get("context") or {}
    if ctx_a and ctx_b:
        changed = [k for k in ("browser", "platform", "mobile", "accept_language", "cookies", "referer") if ctx_a.get(k) != ctx_b.get(k)]
        if changed:
            differences.append("Inny kontekst przeglądarki: " + ", ".join(changed) + ".")
    else:
        limitations.append("Brak nagłówków żądania po co najmniej jednej stronie, więc kontekstu przeglądarki nie da się porównać.")

    hypotheses = []
    if match in ("exact", "normalized") and verdict == "different":
        hypotheses = [
            "cloaking: inna strona dla różnych odbiorców",
            "jednorazowy token wizyty: kolejne wejście tym samym adresem dostaje inną stronę",
            "inny kontekst przeglądarki (nagłówki, język, ciasteczka)",
            "zmiana strony w czasie między przechwyceniami",
        ]
    elif match == "domain":
        limitations.append("Adresy różnią się ścieżką albo parametrami, więc różnica treści może wynikać po prostu z innego adresu.")

    return {
        "a": side(a, obs_a),
        "b": side(b, obs_b),
        "url_match": match,
        "url_match_label": URL_MATCH_LABELS[match],
        "seconds_between": gap,
        "content": content,
        "trackers_only_a": only_a,
        "trackers_only_b": only_b,
        "hosts_only_a": sorted(hosts_a - hosts_b),
        "hosts_only_b": sorted(hosts_b - hosts_a),
        "verdict": verdict,
        "verdict_label": VERDICT_LABELS[verdict],
        "differences": differences,
        "hypotheses": hypotheses,
        "limitations": limitations,
        "thresholds": {"same_text": SAME_TEXT, "same_dom": SAME_DOM, "similar_text": SIMILAR_TEXT, "similar_dom": SIMILAR_DOM},
    }


def artifacts(ad: Ad) -> dict:
    """Bezpieczne odnośniki do dowodów: HAR i zapis HTML tylko do pobrania, zrzut reklamy jako obraz.
    Zrzut reklamy to reklama, nie strona docelowa, więc podajemy go osobno."""
    analysis = Analysis.objects.filter(ad=ad).order_by("-created_at").first()
    state = analysis.state if analysis else {}
    har = (state.get("capture") or {}).get("har")
    html = ((state.get("pages") or {}).get("victim") or {}).get("html_sha")
    creatives = list(ad.raw.get("creatives", [])) if isinstance(ad.raw, dict) else []
    return {
        "har": {"sha256": har, "download": f"/api/artifacts/{har}"} if har else None,
        "html": {"sha256": html, "download": f"/api/artifacts/{html}"} if html else None,
        "page_screenshot": None,  # zrzutów stron nie mamy; nie podstawiamy zrzutu reklamy
        "ad_creatives": [{"sha256": sha, "image": f"/api/artifacts/{sha}/image"} for sha in creatives],
    }


def candidates(ad: Ad, limit: int = 20) -> list[dict]:
    """Inne strony, z którymi warto porównać: ten sam adres dokładny albo po normalizacji, a w tej samej
    sprawie także ta sama domena. Bez sieci, tylko po zapisie obserwacji."""
    own = observation(ad)
    if not own.get("exact_url"):
        return []
    query = Q(raw__observation__exact_url=own["exact_url"]) | Q(raw__observation__normalized_url=own.get("normalized_url") or "-")
    if own.get("domain") and ad.labels.get("case"):
        query |= Q(raw__observation__domain=own["domain"], labels__case=ad.labels.get("case"), labels__bundle=ad.labels.get("bundle"))
    out = []
    for other in Ad.objects.filter(query).exclude(pk=ad.pk).order_by("id")[:limit]:
        obs = observation(other)
        match = url_match(own, obs)
        out.append({
            "ad": other.pk,
            "external_id": other.external_id,
            "title": other.title[:200],
            "url_match": match,
            "url_match_label": URL_MATCH_LABELS[match],
            "captured_at": obs.get("captured_at") or None,
        })
    order = {"exact": 0, "normalized": 1, "domain": 2}
    return sorted(out, key=lambda c: (order.get(c["url_match"], 3), c["ad"]))


def compare_with_links(a: Ad, b: Ad) -> dict:
    result = compare(a, b)
    result["a"]["artifacts"] = artifacts(a)
    result["b"]["artifacts"] = artifacts(b)
    low, high = sorted((a.pk, b.pk))
    edge = Edge.objects.filter(ad_a_id=low, ad_b_id=high).first()
    result["edge"] = {"id": edge.pk, "relation": edge.relation, "detail": f"/api/edges/{edge.pk}"} if edge else None
    result["graph"] = f"/api/graph?ad={a.pk}"
    result["note"] = "Porównanie tylko do odczytu. Nie zmienia krawędzi, grup ani decyzji analityka i niczego nie pobiera z sieci."
    return result
