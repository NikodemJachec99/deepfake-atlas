"""Rejestr typów markerów. Jedno miejsce, w którym zapisana jest siła dowodowa każdego śladu.

Parametry modelu Fellegi-Sunter dla każdego typu:
  m    prawdopodobieństwo, że dwie reklamy tej samej kampanii zgadzają się na tym markerze
  f0   częstość bazowa: jak często dwie niezwiązane strony dzielą tę samą wartość, zanim
       korpus urośnie na tyle, żeby policzyć to z danych
  cap  górna granica wkładu w bitach, czyli maksymalne zaufanie do jednego śladu.
       Przy priorze 1e-4 (ok. -13,3 bita) samotny marker z cap=18 daje pewność ok. 0,96,
       a z cap=16 ok. 0,87, więc wymaga drugiego potwierdzenia (wspólny certyfikat CDN,
       wspólny CRM sieci afiliacyjnej).

Wartości startowe są eksperckie. Etap 2 (model uczony na parach) zastąpi je wagami z danych,
a ten plik zostanie jako opis typów i rodzin.
"""

from dataclasses import dataclass

FAMILIES = {
    "infra": "Infrastruktura",
    "track": "Tracking i lejek",
    "tmpl": "Szablon strony",
    "crea": "Kreacja",
    "narr": "Narracja",
    "pers": "Osoby i marki",
    "beh": "Zachowanie",
}

# Rodziny, które opisują koncepcję, a nie zaplecze. Zgodność tylko w nich daje relację "podobne".
CONCEPT_FAMILIES = frozenset({"narr", "crea", "pers"})


@dataclass(frozen=True)
class Kind:
    code: str
    family: str
    label: str
    m: float
    f0: float
    cap: float
    decisive: bool = False  # sam wystarcza do scalenia, jeśli jest rzadki
    candidate: bool = True  # czy po tym markerze szukamy kandydatów
    soft: bool = False  # porównywany przez podobieństwo, nie przez równość
    lo: float = 0.0  # podobieństwo, od którego marker miękki zaczyna być dowodem
    hi: float = 1.0  # podobieństwo, przy którym osiąga pełną wagę


_KINDS = [
    # Infrastruktura
    Kind("domain", "infra", "Domena", m=0.9, f0=1e-6, cap=18, decisive=True),
    Kind("redirect_domain", "infra", "Domena w łańcuchu przekierowań", m=0.8, f0=1e-5, cap=10),
    Kind("ip", "infra", "Adres IP", m=0.7, f0=1e-4, cap=6),
    Kind("asn", "infra", "System autonomiczny", m=0.5, f0=0.02, cap=1.5, candidate=False),
    Kind("nameserver", "infra", "Serwer nazw", m=0.5, f0=0.01, cap=2, candidate=False),
    Kind("tls_fp", "infra", "Certyfikat TLS", m=0.8, f0=1e-6, cap=16, decisive=True),
    Kind("favicon_hash", "infra", "Hash favicony", m=0.8, f0=1e-4, cap=8),
    Kind("registrar", "infra", "Rejestrator", m=0.5, f0=0.05, cap=1, candidate=False),
    Kind("reg_day", "infra", "Dzień rejestracji domeny", m=0.4, f0=0.003, cap=2, candidate=False),
    Kind("url_path_tpl", "infra", "Szablon ścieżki URL", m=0.6, f0=1e-3, cap=4),
    Kind("url_param_keys", "infra", "Zestaw parametrów URL", m=0.6, f0=1e-3, cap=4),
    # Tracking i lejek
    Kind("ga4", "track", "Google Analytics 4", m=0.9, f0=1e-6, cap=18, decisive=True),
    Kind("ga_ua", "track", "Google Analytics UA", m=0.9, f0=1e-6, cap=18, decisive=True),
    Kind("gtm", "track", "Google Tag Manager", m=0.9, f0=1e-6, cap=18, decisive=True),
    Kind("meta_pixel", "track", "Meta Pixel", m=0.9, f0=1e-6, cap=18, decisive=True),
    Kind("yandex_metrica", "track", "Yandex Metrica", m=0.9, f0=1e-6, cap=18, decisive=True),
    Kind("tiktok_pixel", "track", "TikTok Pixel", m=0.9, f0=1e-6, cap=18, decisive=True),
    Kind("form_action", "track", "Endpoint formularza leadów", m=0.8, f0=1e-5, cap=16, decisive=True),
    Kind("script_host", "track", "Host skryptu zewnętrznego", m=0.5, f0=0.01, cap=2, candidate=False),
    # Szablon strony
    Kind("dom_hash", "tmpl", "Hash struktury DOM", m=0.9, f0=1e-5, cap=10),
    Kind("white_dom_hash", "tmpl", "Hash białej strony cloakingu", m=0.8, f0=1e-5, cap=8),
    Kind("dom_band", "tmpl", "Pasmo LSH szablonu", m=0.0, f0=1.0, cap=0),
    Kind("dom_minhash", "tmpl", "Podobieństwo szablonu", m=0.0, f0=1.0, cap=7, soft=True, lo=0.5, hi=0.9, candidate=False),
    # Kreacja
    Kind("creative_sha256", "crea", "Plik kreacji", m=0.8, f0=1e-6, cap=9),
    # Narracja
    Kind("phone", "narr", "Telefon", m=0.9, f0=1e-6, cap=18, decisive=True),
    Kind("email", "narr", "E-mail", m=0.9, f0=1e-6, cap=18, decisive=True),
    Kind("telegram", "narr", "Telegram", m=0.9, f0=1e-6, cap=18, decisive=True),
    Kind("whatsapp", "narr", "WhatsApp", m=0.9, f0=1e-6, cap=18, decisive=True),
    Kind("crypto_btc", "narr", "Adres Bitcoin", m=0.9, f0=1e-6, cap=18, decisive=True),
    Kind("crypto_eth", "narr", "Adres Ethereum", m=0.9, f0=1e-6, cap=18, decisive=True),
    Kind("iban", "narr", "Rachunek bankowy", m=0.9, f0=1e-6, cap=18, decisive=True),
    Kind("text_band", "narr", "Pasmo LSH tekstu", m=0.0, f0=1.0, cap=0),
    Kind("text_minhash", "narr", "Podobieństwo tekstu", m=0.0, f0=1.0, cap=6, soft=True, lo=0.5, hi=0.85, candidate=False),
    # Osoby i marki
    Kind("advertiser_id", "pers", "Strona reklamodawcy", m=0.9, f0=1e-6, cap=18, decisive=True),
    Kind("payer", "pers", "Płatnik reklamy", m=0.8, f0=1e-5, cap=9),
    Kind("person_mention", "pers", "Wzmianka o osobie", m=0.8, f0=0.01, cap=2.5, candidate=False),
]

KINDS: dict[str, Kind] = {k.code: k for k in _KINDS}

# Pasma LSH służą tylko do znajdowania kandydatów. Dowodem jest podobieństwo policzone z sygnatur.
BAND_OF = {"dom_minhash": "dom_band", "text_minhash": "text_band"}
BAND_KINDS = frozenset(BAND_OF.values())


def kind(code: str) -> Kind:
    return KINDS[code]
