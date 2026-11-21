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
| GET | `/api/campaigns` | `?page=` | strona grup z `size` |
| GET | `/api/campaigns/{id}` | | reklamy, krawędzie, markery rdzeniowe |
| GET | `/api/operators` | `?page=` | strona grup z `size` |
| GET | `/api/operators/{id}` | | jak kampania, plus lista `campaigns` operatora |
| GET | `/api/graph` | `?campaign=` \| `?operator=` \| `?ad=`, `?relation=a,b`, `?limit=` | `{nodes, edges}` dla Sigma.js |
| GET | `/api/kinds` | | słownik 7 rodzin i typów markerów |
| GET | `/api/stats` | | liczby do paska stanu |
| GET | `/api/artifacts/{sha256}` | | surowy dowód jako załącznik (nigdy się nie renderuje) |
| GET | `/api/artifacts/{sha256}/image` | | zrzut reklamy jako obraz (tylko artefakty obrazów) |

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

Oś czasu kampanii (migawki są w bazie, brakuje endpointu), stan źródeł i skanów, przegląd bazy osób, kolejka etykietowania, alerty, raporty, role i klucze. Interfejs nie powinien udawać tych danych.
