"""Słowa kluczowe i tematyka materiału.

Słowa kluczowe to najczęstsze znaczące wyrazy tekstu. Służą analitykowi do orientacji.
Tematyka to regułowa klasyfikacja po tematach wyrazów. Jest słabym markerem: mówi, że dwie
reklamy grają na tym samym motywie, a nie że mają wspólne źródło.
"""

import re
from collections import Counter

_WORD = re.compile(r"[a-ząćęłńóśźż]{4,}", re.I)

STOPWORDS = frozenset(
    """
    oraz albo lecz jednak także również więc gdyż ponieważ żeby aby jeśli jeżeli kiedy gdzie który która które których
    którym którego której tego tej tych temu tym tamten jest są był była było były będzie będą być mieć mamy mają miał
    można może mogą musi trzeba bardzo tylko jeszcze już teraz wtedy potem przed przez podczas według wobec między
    około ponad przy nad pod bez dla jako jak tak nie tak też czy się nas nam was wam ich jego jej nim nią nich
    ten ta to te ci co kto coś ktoś nic nikt wszystko wszystkie wszyscy każdy każda każde inne inny inna swój swoje
    swoją swojego mnie mój moja moje nasz nasza nasze twój twoja twoje pan pani państwo tutaj tam stąd więcej mniej
    dzięki zaś natomiast właśnie nawet niż gdy bowiem czyli zatem jednakże choć chociaż mimo oto ponadto dziś dzisiaj
    wczoraj jutro rok roku lata lat dzień dnia dni godzin minut razy raz jeden jedna jedno dwa dwie trzy
    cookies polityka prywatności regulamin kontakt strona stronie menu zaloguj szukaj więcej czytaj komentarze
    komentarz odpowiedz odpowiedź udostępnij reklama https http www godz lubię temu minut sekund wczoraj zobacz kliknij tutaj
    czas czasu szczegóły szczegółów szczegóty ucieka dowiedz dowiedź sprawdź sprawdz zamów teraz działaj skorzystaj
    kliknij więcej dalej wróć zamknij akceptuję akceptuj zgadzam zgoda polityka
    """.split()
) | frozenset(
    # Strony oszustów po polsku dokładają angielskie wyrazy z szablonów i przycisków. Nie niosą tematu.
    """
    have has had having been being were was will would could should shall might must can cannot did does done
    this that these those there their them they then than what when where which while whom whose with without within
    from into onto over under about above after again against before below between both down during each further
    here just more most other only same some such very your yours our ours his her hers its out off once
    found find finding improve improved improving results result poland polish best better good great new free
    click read more learn know like make made get got use used using need want help show shown take taken
    people person time times year years today now also even every many much really still well since because
    home page site website contact privacy policy terms cookies menu login search share follow comment comments
    """.split()
)

# Tematy wyrazów (bez końcówek), po których rozpoznajemy motyw.
TOPICS: dict[str, tuple[str, ...]] = {
    "inwestycje": ("inwest", "zysk", "zarab", "zarob", "giełd", "akcj", "kryptowalut", "bitcoin", "dochod", "dochód", "kapitał", "depozyt", "broker", "handl", "oszczędn", "pasywn"),
    "zdrowie": ("lek", "suplement", "staw", "cukrzyc", "ciśnien", "odchudz", "prostat", "słuch", "grzybic", "serc", "kapsuł", "tablet", "lekarz", "terapi", "kuracj", "schudn", "ból"),
    "hazard": ("kasyn", "bonus", "spin", "zakład", "jackpot", "slot", "bonanz", "wygran", "ruletk", "bukmach"),
    "sensacja": ("aresztow", "kajdank", "zamach", "skandal", "wyprowadz", "ujawni", "pilne", "szok", "emisj", "napaś", "zatrzyman", "strzel", "prokurat", "wyciek"),
    "sklep": ("promocj", "rabat", "dostaw", "koszyk", "wyprzeda", "zamów", "przecen", "kupon"),
}
MIN_TOPIC_HITS = 3


def keywords(text: str, limit: int = 12) -> list[str]:
    words = [w.lower() for w in _WORD.findall(text)]
    counts = Counter(w for w in words if w not in STOPWORDS)
    return [word for word, count in counts.most_common(limit) if count >= 2]


def topics(text: str) -> list[str]:
    """Tematy materiału od najmocniejszego. Pusta lista, gdy żaden nie ma wyraźnego pokrycia."""
    words = [w.lower() for w in _WORD.findall(text)]
    scores = {
        topic: sum(1 for word in words if word.startswith(stems))
        for topic, stems in TOPICS.items()
    }
    ranked = sorted(((score, topic) for topic, score in scores.items() if score >= MIN_TOPIC_HITS), reverse=True)
    return [topic for _, topic in ranked[:2]]
