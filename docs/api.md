# Kontrakt API

Baza: `http://localhost:8000` (port zmienia `BACKEND_PORT`). Schemat OpenAPI: `/api/schema/`, Swagger: `/api/docs/`.
Typy TypeScript i gotowy klient: `frontend/src/lib/api.ts`.

Frontend niczego nie liczy sam. Każda wartość na ekranie pochodzi z tych wywołań.

| Metoda | Ścieżka | Wejście | Wyjście |
|---|---|---|---|
| GET | `/health` | | `{"status":"ok"}` |
| POST | `/api/analyses` | `{"kind":"url"\|"text","value":"..."}` | `Analysis` (201) |
| POST | `/api/analyses/upload` | multipart, pole `files` (wiele plików) | lista `Analysis` (201), jedna na stronę |
| GET | `/api/analyses/{id}` | | `Analysis` z `result` per etap |
| GET | `/api/analyses/{id}/events` | `?after=<seq>` | strumień SSE zdarzeń `AnalysisEvent` |
| GET | `/api/ads` | `?source=&campaign=&operator=&case=&q=&page=` | strona `AdSummary` |
| GET | `/api/ads/{id}` | | `AdDetail`: genom, zrzuty reklamy, reklamodawca |
| GET | `/api/ads/{id}/edges` | | lista `Edge` malejąco po pewności |
| POST | `/api/ads/{id}/recluster` | | ponowne przypisanie do kampanii i operatora |
| GET | `/api/edges/{id}` | | `EdgeDetail`: obie reklamy i lista dowodów |
| POST | `/api/edges/{id}/verdict` | `{"verdict":"confirmed"\|"rejected"\|"unsure","note":""}` | `EdgeDetail`, wpis w dzienniku audytu |
| POST | `/api/edges/{id}/simulate` | `{"exclude":[<id dowodu>],"edge_version":"<Edge.updated_at>"}` | `Simulation`: krawędź przed i po wyłączeniu dowodów, nic nie zapisuje |
| GET | `/api/edges/{id}/suggestions` | | `Suggestions`: co sprawdzić dalej, z brakujących dowodów tej pary |
| GET | `/api/campaigns` | `?page=` | strona grup z `size` |
| GET | `/api/campaigns/{id}` | | reklamy, krawędzie, markery rdzeniowe |
| GET | `/api/operators` | `?page=` | strona grup z `size` |
| GET | `/api/operators/{id}` | | jak kampania, plus lista `campaigns` operatora |
| GET | `/api/campaigns/{id}/timeline` | | `Timeline`: zdarzenia kampanii posortowane po dacie |
| GET | `/api/operators/{id}/timeline` | | `Timeline` operatora, ten sam kształt (opis niżej) |
| GET | `/api/graph` | `?campaign=` \| `?operator=` \| `?ad=`, `?relation=a,b`, `?limit=` | `{nodes, edges}` dla Sigma.js |
| GET | `/api/kinds` | | słownik 7 rodzin i typów markerów |
| GET | `/api/stats` | | liczby do paska stanu |
| GET | `/api/artifacts/{sha256}` | | surowy dowód jako załącznik (nigdy się nie renderuje) |
| GET | `/api/artifacts/{sha256}/image` | | zrzut reklamy jako obraz (tylko artefakty obrazów) |

## Oś czasu

`Timeline` to `{"group": "K-0001", "events": [TimelineEvent]}`. Zdarzenia są posortowane po `at`, a przy tej samej dacie najpierw zaplecze, potem reklama. Zdarzenie bez daty w bazie się nie pojawia.

| `type` | Data z | `value` | `detail` |
|---|---|---|---|
| `domain_registered` | RDAP | domena | `registrar` |
| `cert_issued` | crt.sh, `not_before` | numer seryjny | `issuer`, `domains` (inne domeny z certyfikatu) |
| `ad_first_seen` | `Ad.first_seen` | | |
| `snapshot` | migawka reklamy z biblioteki | | `active` |
| `ad_last_seen` | `Ad.last_seen` reklamy z biblioteki | | |
| `cert_pl_added`, `cert_pl_removed` | Lista Ostrzeżeń CERT Polska | domena | |

`ads` to identyfikatory reklam grupy, których dotyczy zdarzenie (domena albo certyfikat może łączyć kilka). Ostatnie wystąpienie i migawki są tylko dla reklam z bibliotek, bo dla przechwyceń i zgłoszeń ręcznych to data importu. Z tego samego powodu pomijamy pierwsze wystąpienie przechwycenia, które w paczce nie miało daty.

## Wejście plikami

`POST /api/analyses/upload` przyjmuje to, co analityk realnie ma w ręku:

- zrzut ekranu reklamy (PNG, JPG): OCR wyciąga nazwę reklamodawcy, tekst i numer z Biblioteki Reklam Mety,
- stronę zapisaną z przeglądarki (`.html`, opcjonalnie z katalogiem `_files`),
- plik HAR z ruchem sieciowym,
- katalog z narzędzia `page-capture` (`manifest.json`, `page.har`, `dom.html`),
- archiwum NASK (`archive_info.json`, `dns_ssl.json`, `network.har`, `html/rendered.html`),
- wideo reklamy z plikiem `.info.json` z yt-dlp,
- ZIP z jedną sprawą albo z wieloma sprawami w podkatalogach.

Pliki przesłane razem to jedna sprawa. Analiza działa bez sieci: niczego nie pobieramy z infrastruktury oszustów.

## Strumień postępu (SSE)

`event:` to etap, `data:` to `AnalysisEvent`. Etapy w kolejności: `ingest`, `crawl`, `extract`, `enrich`, `fuse`, `cluster`, `end`.
Każdy etap wysyła `started`, dowolną liczbę `info` i `done` albo `error`. Na końcu przychodzi `event: close`.

```
id: 16
event: fuse
data: {"seq":16,"stage":"fuse","status":"info","message":"Powiązanie z reklamą #12: Ten sam operator",
       "payload":{"edge":8,"other_ad":12,"relation":"same_operator","probability":0.999,"bits":24.1,
                  "families":{"tmpl":15.0,"infra":4.5,"pers":2.5},
                  "top_evidence":[{"family":"tmpl","kind":"kit_path","label":"Ścieżka zaplecza strony",
                                   "value":"POST /api/v1/trigger/field/{id}/","bits":8.0}]}}
```

Zdarzenia `fuse/info` przychodzą po jednym na znalezione powiązanie. Graf w trybie Discovery dorysowuje krawędzie w tej kolejności.
Zdarzenie `crawl/info` niesie łańcuch przekierowań (`payload.chain`), `extract/info` liczbę markerów per rodzina, `cluster/done` kampanię i operatora.

## Relacje

| Relacja | Znaczenie | Warunek |
|---|---|---|
| `same_campaign` | to samo źródło i ta sama opowieść | pewność co najmniej 0,9, marker rozstrzygający albo dwa niezależne potwierdzenia, zgodna narracja |
| `same_operator` | to samo zaplecze, inna opowieść | jak wyżej, bez zgodnej narracji |
| `similar` | podobna koncepcja | zgodna narracja, kreacja albo osoby, albo ten sam silnik lejka bez śladu operatora; brak dowodu wspólnego zaplecza |

Kampania (`K-0033`) to reklamy spięte krawędziami `same_campaign`. Operator (`O-0001`) to reklamy spięte `same_campaign` albo `same_operator`, więc jeden operator ma zwykle kilka kampanii.

## Dowód (`Evidence`)

```json
{
  "id": 512,
  "family": "track", "family_label": "Tracking i lejek",
  "kind": "funnel_id", "label": "Identyfikator strony w panelu lejka",
  "value_a": "11111111-2222-4333-8444-555555555555", "value_b": "11111111-2222-4333-8444-555555555555",
  "similarity": 1.0,
  "df": 2, "corpus_n": 41,
  "raw_bits": 18.0, "weight_bits": 18.0,
  "decisive": true,
  "artifact_a": "<sha256 HAR strony A>", "artifact_b": "<sha256 HAR strony B>"
}
```

- `df` z `corpus_n`: w ilu niezależnych źródłach występuje ta wartość. Źródłem jest kampania albo reklama bez kampanii.
- `weight_bits`: wkład dowodu po zniżce za korelację w rodzinie. Suma wkładów to `Edge.bits`.
- Markery miękkie (`dom_minhash`, `text_minhash`, `page_text_minhash`) mają `df = 0` i podobieństwo w `similarity`.
- `decisive`: rzadki marker rozstrzygający.
- `id`: stały identyfikator dowodu w obrębie krawędzi. Zmienia się, gdy krawędź jest przeliczana na nowo (wtedy zmienia się też `Edge.updated_at`).

## Laboratorium dowodów (`Simulation`)

`POST /api/edges/{id}/simulate` przelicza parę tym samym silnikiem, raz ze wszystkimi zapisanymi dowodami krawędzi i raz bez wybranych. Niczego nie zapisuje: krawędź, decyzja analityka, dziennik audytu, kampanie i operatorzy zostają bez zmian. Nie wykonuje zapytań na zewnątrz.

Żądanie:

```json
{"exclude": [512, 513], "edge_version": "2026-11-21T14:58:45.826265+00:00"}
```

- `exclude`: identyfikatory dowodów z `EdgeDetail.evidence[].id`. Pusta lista zwraca sam wynik bazowy.
- `edge_version`: opcjonalne, `Edge.updated_at` z chwili wczytania. Jeśli krawędź zmieniła się od tego czasu, odpowiedź to `409` z bieżącym `edge_version`. Interfejs odświeża wtedy dowody.
- Identyfikator dowodu z innej krawędzi: `400`, w polu `unknown` lista nieznanych identyfikatorów.

Odpowiedź:

```json
{
  "edge": 64, "edge_version": "2026-11-21T14:58:45.826265+00:00", "model_version": "fs-5",
  "stored": {"relation": "same_operator", "bits": 56.3, "model_version": "fs-5"},
  "baseline": {
    "relation": "same_operator", "relation_label": "ten sam operator",
    "probability": 1.0, "bits": 56.3, "decisive": true, "duplicate": false,
    "families": {"track": 29.3, "tmpl": 16.0, "infra": 5.8},
    "independent": ["kit", "track"],
    "reasons": ["Pewność 1.000 spełnia próg 0.9.", "Jest rzadki marker rozstrzygający.", "..."]
  },
  "simulated": {"relation": "similar", "relation_label": "podobna koncepcja", "...": "jak baseline"},
  "relation_changed": true,
  "excluded": [{"id": 512, "family": "track", "kind": "funnel_id", "label": "Identyfikator strony w panelu lejka",
                "value": "11111111-2222-4333-8444-555555555555", "weight_bits": 18.0, "decisive": true}],
  "group_impact": {
    "campaign": {"binds_before": false, "binds_after": false, "pair_still_connected": null, "path_length": null,
                 "note": "Krawędź nie spina tej grupy ani przed, ani po."},
    "operator": {"binds_before": true, "binds_after": false, "pair_still_connected": true, "path_length": 2,
                 "note": "Obie reklamy zostają w jednej grupie przez inne krawędzie (ścieżka długości 2)."}
  },
  "warnings": ["Wynik dotyczy tylko tej pary. Pozostałe krawędzie liczymy bez zmian."]
}
```

- `baseline` to przeliczenie zapisanych dowodów bieżącym modelem, `stored` to krawędź z bazy. Gdy się różnią (inna wersja modelu), w `warnings` jest ostrzeżenie, a porównanie idzie względem `baseline`.
- `relation: null` w `simulated` oznacza, że po wyłączeniu krawędź by nie powstała.
- `independent`: niezależne silne potwierdzenia. `kit` to ślady jednego silnika lejka (ścieżki zaplecza, zestaw parametrów, szablon ścieżki) liczone razem.
- `reasons`: zdania odpowiadające regułom z `similarity/fusion.py`, w kolejności sprawdzania.
- `group_impact`: liczone tylko wtedy, gdy krawędź przestałaby spinać grupę. `pair_still_connected` mówi, czy obie reklamy łączy inna ścieżka z krawędzi tego samego rodzaju (bez odrzuconych). `false` oznacza, że grupa rozpadłaby się w tym miejscu na dwie, przy reszcie grafu bez zmian. Nie przeliczamy innych par.
- Bity to wkład dowodów w skali logarytmicznej, nie procent i nie identyfikacja osoby.

## Co sprawdzić dalej (`Suggestions`)

`GET /api/edges/{id}/suggestions` zwraca kilka deterministycznych wskazówek dla analityka. Wynikają z reguł silnika i z materiałów przy obu reklamach. Nic nie pobiera z sieci, nie zgaduje, czy brakujący dowód istnieje, nie ocenia prawdopodobieństwa. Pusta lista to poprawny wynik: para ma pełny materiał i odporną hipotezę.

```json
{
  "edge": 3082, "relation": "same_operator",
  "materials": {"A": {"har": true, "page": false, "creative": true, "library_ids": []},
                "B": {"har": true, "page": true, "creative": true, "library_ids": []}},
  "suggestions": [{
    "code": "single_support",
    "missing": "niezależne potwierdzenie wspólnego źródła, które utrzyma się bez każdego pojedynczego śladu",
    "why": "Wspólne źródło trzyma się na śladach, z których każdy jest konieczny: bez śladu \"host zasobów lub trackera\" (crimsonbase.pro) relacja to podobna koncepcja.",
    "next_step": "Poszukać drugiego, niezależnego śladu konta lub infrastruktury: ...",
    "limitation": "Jeden rzadki ślad bywa wystarczający. Wskazówka mówi o kruchości hipotezy, nie o tym, że jest błędna.",
    "rule": "fusion: wspólne źródło wymaga markera rozstrzygającego albo dwóch niezależnych potwierdzeń",
    "sides": []
  }],
  "note": "Wskazówki wynikają z reguł silnika i z dostępnych materiałów. Kolejność to kolejność reguł, nie ocena skuteczności.",
  "warnings": []
}
```

| `code` | Kiedy |
|---|---|
| `single_support` | wspólne źródło znika po wyłączeniu jednego rodzaju śladu (sprawdzane symulacją) |
| `engine_without_account` | relacja `similar` na samych ścieżkach zaplecza, bez śladu konta operatora |
| `copy_without_backend` | relacja `similar` na zgodnej treści lub obrazach, bez zaplecza |
| `har_missing` | strona z przechwycenia bez pliku HAR (`sides` mówi, po której stronie) |
| `screenshot_only` | przy reklamie jest tylko zrzut; gdy znamy numer z Biblioteki Reklam, wskazówka go podaje |
| `story_unknown` | ten sam operator, ale po jednej stronie brak treści strony, więc nie da się sprawdzić, czy to ta sama kampania |

`sides` to lista stron pary w formacie `A (reklama #id)`, których wskazówka dotyczy. Pusta, gdy dotyczy pary jako całości.

## Typy markerów

Pełny słownik zwraca `/api/kinds`. Najważniejsze:

| Rodzina | Typy |
|---|---|
| Infrastruktura | `domain`, `redirect_domain`, `ip`, `asn`, `nameserver`, `tls_fp`, `tls_serial`, `favicon_hash`, `registrar`, `reg_day`, `url_path_tpl`, `url_param_keys`, `cdn`, `server_sig` |
| Tracking i lejek | `ga4`, `ga_ua`, `gtm`, `meta_pixel`, `google_ads`, `yandex_metrica`, `tiktok_pixel`, `capi_token`, `funnel_id`, `funnel_param`, `asset_host`, `form_action`, `script_host` |
| Szablon strony | `kit_path`, `dom_hash`, `dom_minhash`, `white_dom_hash` |
| Kreacja | `creative_sha256` |
| Narracja | `page_title`, `page_text_minhash`, `text_minhash`, `phone`, `email`, `telegram`, `whatsapp`, `crypto_btc`, `crypto_eth`, `iban` |
| Osoby i marki | `person_mention`, `brand_impersonated`, `page_name`, `advertiser_id`, `payer`, `meta_ad_ref` |
| Zachowanie | `ad_naming`, `lang_trace` |

## Czego API jeszcze nie ma

Stan źródeł i skanów, przegląd bazy osób, kolejka etykietowania, alerty, raporty, role i klucze. Interfejs nie powinien udawać tych danych.
