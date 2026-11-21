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
    story: bool = False  # dowodzi tej samej treści (tekst, obraz, kontakt), a nie tylko tego samego motywu
    # Ślad oprogramowania lejka albo trackera. Ścieżki zaplecza, szablon ścieżki i zestaw parametrów
    # ustawia ten sam silnik, więc przy liczeniu niezależnych rodzin są jednym potwierdzeniem.
    kit: bool = False
    # Wspólny motyw (osoba, marka, tematyka). Różni operatorzy grają na tych samych, więc motyw
    # nie potwierdza wspólnego źródła, nawet gdy jest ich kilka naraz.
    motif: bool = False


_KINDS = [
    # Infrastruktura
    Kind("domain", "infra", "Domena", m=0.9, f0=1e-6, cap=18, decisive=True),
    Kind("redirect_domain", "infra", "Domena w łańcuchu przekierowań", m=0.8, f0=1e-5, cap=10),
    Kind("ip", "infra", "Adres IP", m=0.7, f0=1e-4, cap=6),
    Kind("asn", "infra", "System autonomiczny", m=0.5, f0=0.02, cap=1.5, candidate=False),
    Kind("nameserver", "infra", "Serwer nazw", m=0.5, f0=0.01, cap=2, candidate=False),
    Kind("tls_fp", "infra", "Certyfikat TLS", m=0.8, f0=1e-6, cap=16, decisive=True),
    Kind("tls_serial", "infra", "Numer seryjny certyfikatu", m=0.8, f0=1e-6, cap=16, decisive=True),
    Kind("favicon_hash", "infra", "Hash favicony", m=0.8, f0=1e-4, cap=8),
    Kind("registrar", "infra", "Rejestrator", m=0.5, f0=0.05, cap=1, candidate=False),
    Kind("reg_day", "infra", "Dzień rejestracji domeny", m=0.4, f0=0.003, cap=2, candidate=False),
    Kind("url_path_tpl", "infra", "Szablon ścieżki URL", m=0.6, f0=1e-3, cap=4, kit=True),
    Kind("url_param_keys", "infra", "Zestaw parametrów URL", m=0.6, f0=1e-3, cap=4, kit=True),
    Kind("cdn", "infra", "Sieć CDN", m=0.5, f0=0.3, cap=0.5, candidate=False),
    Kind("server_sig", "infra", "Sygnatura serwera", m=0.5, f0=0.05, cap=1.5, candidate=False),
    # Tracking i lejek
    Kind("ga4", "track", "Google Analytics 4", m=0.9, f0=1e-6, cap=18, decisive=True),
    Kind("ga_ua", "track", "Google Analytics UA", m=0.9, f0=1e-6, cap=18, decisive=True),
    Kind("gtm", "track", "Google Tag Manager", m=0.9, f0=1e-6, cap=18, decisive=True),
    Kind("meta_pixel", "track", "Meta Pixel", m=0.9, f0=1e-6, cap=18, decisive=True),
    Kind("yandex_metrica", "track", "Yandex Metrica", m=0.9, f0=1e-6, cap=18, decisive=True),
    Kind("tiktok_pixel", "track", "TikTok Pixel", m=0.9, f0=1e-6, cap=18, decisive=True),
    Kind("form_action", "track", "Endpoint formularza leadów", m=0.8, f0=1e-5, cap=16, decisive=True),
    Kind("script_host", "track", "Host skryptu zewnętrznego", m=0.5, f0=0.01, cap=2, candidate=False),
    Kind("google_ads", "track", "Konto Google Ads", m=0.9, f0=1e-6, cap=18, decisive=True),
    Kind("capi_token", "track", "Token Meta Conversions API (skrót)", m=0.9, f0=1e-6, cap=18, decisive=True),
    Kind("funnel_id", "track", "Identyfikator strony w panelu lejka", m=0.8, f0=1e-6, cap=18, decisive=True),
    Kind("funnel_param", "track", "Klucz afiliacyjny lub parametr lejka", m=0.7, f0=1e-5, cap=12),
    Kind("asset_host", "track", "Host zasobów lub trackera", m=0.7, f0=1e-4, cap=9),
    # Szablon strony
    Kind("dom_hash", "tmpl", "Hash struktury DOM", m=0.9, f0=1e-5, cap=10),
    Kind("white_dom_hash", "tmpl", "Hash białej strony cloakingu", m=0.8, f0=1e-5, cap=8),
    Kind("kit_path", "tmpl", "Ścieżka zaplecza strony", m=0.7, f0=1e-4, cap=8, kit=True),
    Kind("dom_band", "tmpl", "Pasmo LSH szablonu", m=0.0, f0=1.0, cap=0),
    Kind("dom_minhash", "tmpl", "Podobieństwo szablonu", m=0.0, f0=1.0, cap=7, soft=True, lo=0.5, hi=0.9, candidate=False),
    # Kreacja
    Kind("creative_sha256", "crea", "Plik kreacji", m=0.8, f0=1e-6, cap=9, story=True),
    Kind("creative_phash", "crea", "Hash percepcyjny zrzutu reklamy", m=0.8, f0=1e-6, cap=12, decisive=True, story=True),
    Kind("image_band", "crea", "Klucz wyszukiwania obrazów", m=0.0, f0=1.0, cap=0),
    Kind("image_set", "crea", "Wspólne obrazy na stronie", m=0.0, f0=1.0, cap=7, soft=True, lo=0.25, hi=0.7, candidate=False, story=True),
    Kind("video_band", "crea", "Klucz wyszukiwania klatek nagrania", m=0.0, f0=1.0, cap=0),
    # Te same klatki w dwóch nagraniach: ten sam materiał wideo, także po ponownym zakodowaniu albo przycięciu.
    Kind("video_frames", "crea", "Wspólne klatki nagrania reklamy", m=0.0, f0=1.0, cap=10, soft=True, lo=0.25, hi=0.6, candidate=False, story=True),
    # Narracja
    Kind("phone", "narr", "Telefon", m=0.9, f0=1e-6, cap=18, decisive=True, story=True),
    Kind("email", "narr", "E-mail", m=0.9, f0=1e-6, cap=18, decisive=True, story=True),
    Kind("telegram", "narr", "Telegram", m=0.9, f0=1e-6, cap=18, decisive=True, story=True),
    Kind("whatsapp", "narr", "WhatsApp", m=0.9, f0=1e-6, cap=18, decisive=True, story=True),
    Kind("crypto_btc", "narr", "Adres Bitcoin", m=0.9, f0=1e-6, cap=18, decisive=True, story=True),
    Kind("crypto_eth", "narr", "Adres Ethereum", m=0.9, f0=1e-6, cap=18, decisive=True, story=True),
    Kind("iban", "narr", "Rachunek bankowy", m=0.9, f0=1e-6, cap=18, decisive=True, story=True),
    Kind("page_title", "narr", "Tytuł strony", m=0.7, f0=1e-4, cap=7, story=True),
    Kind("page_text_band", "narr", "Pasmo LSH treści strony", m=0.0, f0=1.0, cap=0),
    Kind("page_text_minhash", "narr", "Podobieństwo treści strony", m=0.0, f0=1.0, cap=8, soft=True, lo=0.5, hi=0.9, candidate=False, story=True),
    Kind("topic", "narr", "Tematyka", m=0.6, f0=0.15, cap=1.5, candidate=False, motif=True),
    Kind("text_band", "narr", "Pasmo LSH tekstu", m=0.0, f0=1.0, cap=0),
    Kind("text_minhash", "narr", "Podobieństwo tekstu", m=0.0, f0=1.0, cap=6, soft=True, lo=0.5, hi=0.85, candidate=False, story=True),
    # Osoby i marki
    Kind("advertiser_id", "pers", "Strona reklamodawcy", m=0.9, f0=1e-6, cap=18, decisive=True),
    Kind("payer", "pers", "Płatnik reklamy", m=0.8, f0=1e-5, cap=9),
    Kind("person_mention", "pers", "Wzmianka o osobie", m=0.8, f0=0.01, cap=2.5, candidate=False, motif=True),
    Kind("meta_ad_ref", "pers", "Identyfikator reklamy lub kampanii Meta", m=0.9, f0=1e-6, cap=18, decisive=True),
    Kind("page_name", "pers", "Nazwa strony lub reklamodawcy", m=0.5, f0=1e-4, cap=8),
    Kind("brand_impersonated", "pers", "Podszycie pod markę", m=0.7, f0=0.02, cap=3, candidate=False, motif=True),
    Kind("face_match", "pers", "Twarz osoby z bazy referencyjnej", m=0.8, f0=0.01, cap=2.5, candidate=False, motif=True),
    # Zachowanie
    Kind("ad_naming", "beh", "Nazewnictwo reklam i zestawów", m=0.5, f0=1e-5, cap=8),
    Kind("lang_trace", "beh", "Ślad językowy operatora", m=0.5, f0=0.05, cap=1.5, candidate=False),
]

KINDS: dict[str, Kind] = {k.code: k for k in _KINDS}

# Pasma LSH służą tylko do znajdowania kandydatów. Dowodem jest podobieństwo policzone z sygnatur.
BAND_OF = {
    "dom_minhash": "dom_band",
    "text_minhash": "text_band",
    "page_text_minhash": "page_text_band",
    "image_set": "image_band",
    "video_frames": "video_band",
}
BAND_KINDS = frozenset(BAND_OF.values())


def kind(code: str) -> Kind:
    return KINDS[code]
