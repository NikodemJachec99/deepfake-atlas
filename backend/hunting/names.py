"""Nazwy domen: rozbicie na tokeny i szablon z cyframi. Czyste funkcje, bez bazy i sieci."""

import re

from extractors.url import domain_label

MIN_TOKEN = 4
# Słowa, które mają setki domen oszustw i legalnych stron naraz. Token z tej listy niczego nie mówi o operatorze,
# a zapytanie o niego do crt.sh zwróciłoby tysiące obcych certyfikatów.
GENERIC_WORDS = frozenset(
    """
    www online shop store sklep oferta oferty promo promocja promocje info strona portal news blog pomoc konto login
    secure security bank bankowy invest invest inwest inwestycja inwestycje inwestowanie trading trade crypto bitcoin
    forex money finance finanse kredyt kredyty pozyczka pozyczki polska poland polish free best official oficjalny
    app apps web site page land landing click track tracker zarabiaj zarobek zarobki praca kasa gazeta wiadomosci
    news24 media group service services support health zdrowie diet dieta slim forte plus premium pro club center
    centrum market direct global digital smart fast easy mega super nowy nowe nowa nowosc the and for with
    """.split()
)

_NON_LETTERS = re.compile(r"[^a-z]+")
_DIGITS = re.compile(r"\d+")


def label_of(domain: str) -> str:
    """Nazwa własna domeny bez końcówki, małymi literami. `Zysk-A12.example` daje `zysk-a12`."""
    return domain_label(domain.lower())


def name_tokens(label: str) -> list[str]:
    """Słowa z nazwy domeny: podział po `-`, `_` i cyfrach, bez krótkich i ogólnych. Kolejność i powtórzenia znikają."""
    out = []
    for part in _NON_LETTERS.split(label.lower()):
        if len(part) >= MIN_TOKEN and part not in GENERIC_WORDS and part not in out:
            out.append(part)
    return out


def name_template(label: str) -> str:
    """Szablon nazwy: ciągi cyfr zastąpione `{n}`. `zysk-a12` i `zysk-a7` mają ten sam szablon `zysk-a{n}`."""
    return _DIGITS.sub("{n}", label.lower())


def has_token(label: str, token: str) -> str:
    """`exact`, gdy token jest osobnym słowem nazwy, `part`, gdy tylko fragmentem słowa (tylko tokeny od 5 liter), inaczej pusty."""
    label = label.lower()
    if token in name_tokens_all(label):
        return "exact"
    if len(token) >= MIN_TOKEN + 1 and token in label:
        return "part"
    return ""


def name_tokens_all(label: str) -> list[str]:
    """Wszystkie słowa nazwy bez filtra ogólnych słów. Do dopasowania tokenu, który już przeszedł filtr."""
    return [p for p in _NON_LETTERS.split(label.lower()) if p]
