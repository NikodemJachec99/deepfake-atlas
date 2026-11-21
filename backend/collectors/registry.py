"""Rejestr kolektorów wołanych przez harmonogram. Nowe źródło to nowy wpis tutaj."""

from datetime import date

from ads.models import Analysis

from . import cert_pl, meta, microsoft


def _queue(ads: list, analyze: bool) -> list[str]:
    """Tworzy analizy dla reklam, które jeszcze żadnej nie mają."""
    if not analyze:
        return []
    return [
        str(Analysis.objects.create(ad=ad, input_kind=Analysis.Kind.AD, input_value=ad.external_id).pk)
        for ad in ads
        if not ad.analyses.exists()
    ]


def run(collector: str, params: dict) -> dict:
    analyze = params.get("analyze", True)
    if collector == "cert_pl":
        return {"synced": cert_pl.sync_current(), "analyses": []}
    if collector == "cert_pl_history":
        return {**cert_pl.sync_history(int(params.get("year", date.today().year))), "analyses": []}
    if collector == "microsoft":
        result = microsoft.collect(params["query"], limit=int(params.get("limit", 200)))
    elif collector == "meta":
        result = meta.collect(params["query"], limit=int(params.get("limit", 500)))
    else:
        raise KeyError(f"Nieznany kolektor: {collector}")
    ads = result.pop("ads")
    return {**result, "analyses": _queue(ads, analyze)}
