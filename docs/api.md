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
| GET | `/api/ads/{id}/observations` | | obserwacja strony reklamy i strony do porównania (ten sam adres albo domena w sprawie) |
| GET | `/api/observations/compare` | `?a=ID&b=ID` | `ObservationComparison`: dwie strony obok siebie, tylko do odczytu |
| GET | `/api/edges/{id}` | | `EdgeDetail`: obie reklamy i lista dowodów |
| POST | `/api/edges/{id}/verdict` | `{"verdict":"confirmed"\|"rejected"\|"unsure","reason":"...","note":""}` | `EdgeDetail`; wpis w historii decyzji z migawką i w dzienniku audytu |
| GET | `/api/edges/{id}/decisions` | | `EdgeDecisions`: historia decyzji od najnowszej (opis niżej) |
| GET | `/api/edges/{id}/precedents` | `?limit=` (domyślnie 5, najwyżej 20) | `Precedents`: podobne wcześniejsze rozstrzygnięcia innych par (opis niżej) |
| POST | `/api/edges/{id}/simulate` | `{"exclude":[<id dowodu>],"edge_version":"<Edge.updated_at>"}` | `Simulation`: krawędź przed i po wyłączeniu dowodów, nic nie zapisuje |
| GET | `/api/edges/{id}/suggestions` | | `Suggestions`: co sprawdzić dalej, z brakujących dowodów tej pary |
| POST | `/api/edges/{id}/weakest-link` | `{"max_group_size":2,"max_scenarios":500,"time_limit_ms":3000,"edge_version":"..."}` | `WeakestLink`: najmniejsze zestawy grup śladów, których utrata zmienia relację |
| GET | `/api/campaigns` | `?page=` | strona grup z `size` |
| GET | `/api/campaigns/{id}` | | reklamy, krawędzie, markery rdzeniowe |
| GET | `/api/operators` | `?page=` | strona grup z `size` |
| GET | `/api/operators/{id}` | | jak kampania, plus lista `campaigns` operatora |
| GET | `/api/campaigns/{id}/timeline` | | `Timeline`: oś obserwacji kampanii (opis niżej) |
| GET | `/api/operators/{id}/timeline` | | `Timeline` operatora, ten sam kształt (opis niżej) |
| GET | `/api/graph` | `?campaign=` \| `?operator=` \| `?ad=`, `?relation=a,b`, `?limit=` | `{nodes, edges}` dla Sigma.js |
| GET | `/api/kinds` | | słownik 7 rodzin i typów markerów |
| GET | `/api/stats` | | liczby do paska stanu |
| GET | `/api/artifacts/{sha256}` | | surowy dowód jako załącznik (nigdy się nie renderuje) |
| GET | `/api/artifacts/{sha256}/image` | | zrzut reklamy jako obraz (tylko artefakty obrazów) |

## Oś obserwacji

`Timeline` to `{"group": "K-0001", "events": [TimelineEvent], "undated": {...}}`. Zdarzenia są posortowane po `at`, a przy tej samej dacie w kolejności z tabeli niżej. Wynik jest deterministyczny.

Każde zdarzenie ma rodzaj czasu i jego pochodzenie:

- `time_kind`: `observed` to chwila, w której materiał zobaczyło narzędzie przechwytujące, analityk albo skan biblioteki. To moment obserwacji, a nie początek kampanii. `reported` to data podana przez źródło zewnętrzne o rzeczy, której nie obserwowaliśmy w tej chwili.
- `source`: `capture`, `manual`, `meta` i inne źródła reklam albo `rdap`, `crt.sh`, `cert_pl`.
- `precision`: `exact` albo `day` (start emisji z biblioteki Mety ma tylko dzień).

| `type` | `time_kind`, źródło daty | `value` | `detail` |
|---|---|---|---|
| `domain_registered` | `reported`, RDAP | domena | `registrar` |
| `cert_issued` | `reported`, `not_before` z crt.sh albo z certyfikatu w przechwyceniu (`dns_ssl.json`, źródło `capture`) | numer seryjny pierwszego certyfikatu | `issuer`, `count` (wystawienia w serii), `last_at` (ostatnie), `domains` (inne domeny z certyfikatu) |
| `ad_first_seen` | `observed` z chwili przechwycenia albo zgłoszenia; `reported` dla startu emisji z biblioteki | | |
| `trace_first_observed` | jak `ad_first_seen` najwcześniejszej reklamy grupy ze śladem | wartość śladu | `kind`, `kind_label`, `family`, `in_group` (reklamy grupy ze śladem), `undated_ads`, `tied` |
| `link_observable` | jak `ad_first_seen` późniejszej z dwóch reklam | identyfikator krawędzi | `relation`, `probability` |
| `snapshot` | `observed`, skan biblioteki | | `active` |
| `ad_last_seen` | `observed`, skan biblioteki | | |
| `cert_pl_added`, `cert_pl_removed` | `reported`, Lista Ostrzeżeń CERT Polska | domena | |

Zasady:

- `ads` to reklamy grupy, których dotyczy zdarzenie. Domena, certyfikat albo ślad mogą łączyć kilka.
- Odnowienia certyfikatu z tymi samymi reklamami i tymi samymi pozostałymi domenami to jedno zdarzenie `cert_issued` z `count`. Wspólny certyfikat kilku reklam to jedno zdarzenie z nimi wszystkimi.
- `trace_first_observed` dotyczy domen, adresów IP, identyfikatorów analityki, pikseli i lejka, kreacji, kontaktów i kont reklamowych. Gdy kilka reklam ma tę samą najwcześniejszą datę, wszystkie są w `ads`, a `tied` jest `true`: nie rozstrzygamy, która była pierwsza.
- `link_observable` to chwila, od której oba materiały były w ręku, a nie data, w której operator je połączył. Kampania pokazuje krawędzie `same_campaign`, operator także `same_operator`. Odrzucone przez analityka pomijamy.
- Oś nie twierdzi, że jedna domena zastąpiła drugą ani że operator zmienił taktykę. Pokazuje kolejność obserwacji.
- Ostatnie wystąpienie i migawki są tylko dla reklam z bibliotek, bo dla przechwyceń i zgłoszeń ręcznych to data importu. Z tego samego powodu pomijamy pierwsze wystąpienie przechwycenia, które w paczce nie miało daty.
- `undated` liczy to, czego nie da się umieścić w czasie: `ads` (reklamy bez daty), `traces` (ślady tylko w takich reklamach), `links` (krawędzie z taką reklamą), `certificates` (numery certyfikatów bez daty wystawienia, np. z `dns_ssl.json`).

## Pamięć sprzeciwu

Decyzja analityka (`POST /api/edges/{id}/verdict`) ma powód i notatkę. Zmienia tylko werdykt krawędzi: relacja, bity, dowody i grupy zostają takie, jakie policzył silnik. Każda decyzja to nowy, niezmienny wpis historii.

Powody (`reason`, lista z etykietami w `GET /api/kinds` jako `verdict_reasons`): `shared_tool` (wspólne narzędzie albo silnik), `shared_infrastructure` (współdzielona infrastruktura), `extraction_error` (błędna ekstrakcja), `no_independent_confirmation` (brak niezależnego potwierdzenia), `confirmed_by_analyst`, `other` (powód w notatce). Bez `reason` decyzja zapisuje się z powodem `unknown`, więc stary klient działa. `unknown` mają też wszystkie decyzje sprzed pamięci sprzeciwu, przeniesione z dziennika audytu jako `legacy` bez migawki. Uzasadnień nie wyciągamy z notatek.

`GET /api/edges/{id}/decisions` zwraca `{"edge": 12, "current": "rejected", "decisions": [EdgeDecision]}`. `EdgeDecision`: `id`, `edge` (null, gdy krawędź zniknęła przy przeliczeniu), `ad_a`, `ad_b`, `verdict`, `previous_verdict`, `reason`, `reason_label`, `note`, `legacy`, `user`, `created_at`, `has_snapshot`, `snapshot`.

`snapshot` to stan z chwili decyzji, bo dowody krawędzi są przebudowywane przy każdym przeliczeniu: `relation`, `bits`, `probability`, `decisive`, `duplicate`, `families`, `model_version`, `edge_version` (wersja dowodów, ta sama co w Laboratorium dowodów), `evidence` (rodzaj, rodzina, wartości po redakcji do 300 znaków, podobieństwo, `df`, `corpus_n`, wkład w bitach, `decisive`, `kit`, `motif`), `groups` (kampania i operator obu reklam), `ads` (źródło, sprawa, adres po redakcji).

### Precedensy

`GET /api/edges/{id}/precedents` szuka wcześniejszych decyzji o innych parach, które dotyczyły podobnych śladów. Wynik jest doradczy: wcześniejsza decyzja nie przesądza o tej krawędzi, a zapytanie niczego nie zmienia.

Reguły:

1. Kandydat to najnowsza decyzja o każdej innej parze, która ma migawkę. Decyzje bez migawki są liczone w `skipped_without_snapshot` i nie są pokazywane jako precedensy. Własna historia pary jest w `/decisions`.
2. Ślady obu stron są sprowadzane do grup z testu najsłabszego ogniwa (`kit`, `motif`, `infra`, `content`, `creative`, `template`, `kind:<typ>`). Liczą się tylko dowody z wkładem większym od zera.
3. Kandydat musi dzielić z krawędzią co najmniej jedną grupę inną niż `motif`.
4. `similarity` to Jaccard zbiorów grup. Kolejność: podobieństwo, ta sama relacja, nowsza decyzja, id.

`Precedents`: `edge`, `edge_version`, `relation`, `groups` (grupy tej krawędzi), `status` (`found` albo `none`), `considered` (pary z decyzjami), `matching` (spełniające reguły), `skipped_without_snapshot`, `limit`, `conflict` (wśród zwróconych są i potwierdzenia, i odrzucenia), `notice`, `precedents`.

Precedens: `decision`, `edge`, `ad_a`, `ad_b`, `verdict`, `reason`, `reason_label`, `reason_known` (`false` dla powodu `unknown`), `note` (po redakcji), `user`, `created_at`, `source`, `similarity`, `same_relation`, `relation_then`, `relation_now`, `model_then`, `shared_groups`, `only_now`, `only_then`, `new_independent` (grupy tylko w tej krawędzi, inne niż motywy i silnik lejka, czyli niezależne ślady, których wcześniejsza decyzja nie oceniała), `why` i `differences` (zdania z reguł, nie generowane), `evidence_then` (do 12 dowodów z migawki).

API nie ma uwierzytelniania, więc notatka jest widoczna dla każdego z dostępem do API, tak jak wcześniej `verdict_note`. Przed zapisem sekrety w notatce są zamieniane na skróty: parametry z tokenami w adresach i tokeny dostępu Mety pod dowolną nazwą. Danych osobowych notatka nie powinna zawierać, system ich nie wykrywa.

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
- `display_value`: wartość do pokazania. Dla osób (`person_mention`, `face_match`) to nazwisko z bazy referencyjnej zamiast `person:<id>`, dla pozostałych typów to samo co `value_a`. To samo pole mają markery w genomie reklamy (`AdDetail.genome[].markers[]`), markery rdzeniowe kampanii i operatora oraz `Simulation.excluded[]`.
- `id`: stały identyfikator dowodu w obrębie krawędzi. Zmienia się, gdy krawędź jest przeliczana na nowo (wtedy zmienia się też `Edge.updated_at`).

## Laboratorium dowodów (`Simulation`)

`POST /api/edges/{id}/simulate` przelicza parę tym samym silnikiem, raz ze wszystkimi zapisanymi dowodami krawędzi i raz bez wybranych. Niczego nie zapisuje: krawędź, decyzja analityka, dziennik audytu, kampanie i operatorzy zostają bez zmian. Nie wykonuje zapytań na zewnątrz.

Żądanie:

```json
{"exclude": [512, 513], "edge_version": "2026-11-21T14:58:45.826265+00:00"}
```

- `exclude`: identyfikatory dowodów z `EdgeDetail.evidence[].id`. Pusta lista zwraca sam wynik bazowy.
- `edge_version`: opcjonalne, `Edge.updated_at` z chwili wczytania, ISO 8601 ze strefą. Porównujemy chwile, nie napisy: `Z`, `+00:00` i `+01:00` dla tej samej chwili to ta sama wersja, mikrosekundy się liczą. Jeśli krawędź zmieniła się od tego czasu, odpowiedź to `409` z bieżącym `edge_version`, a interfejs odświeża wtedy dowody. Napis, który nie jest datą albo nie ma strefy: `400`. Tak samo w `weakest-link`.
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

## Dwie twarze jednego linku (`ObservationComparison`)

Porównanie dwóch przechwyconych stron, np. tego samego adresu widzianego dwa razy. Tylko do odczytu: nie zmienia krawędzi, grup ani decyzji i nie pobiera niczego z sieci. Opis audytu i progów: [dwie-twarze.md](dwie-twarze.md).

`GET /api/ads/{id}/observations`:

```json
{
  "ad": 12,
  "observation": {"ad": 12, "external_id": "nask/61/strona-2-...", "title": "...", "exact_url": "https://.../?utm_id=...",
                  "captured_at": "2026-10-20T12:03:42.174Z", "time_source": "har.entries",
                  "context": {"browser": "Microsoft Edge", "platform": "Windows", "mobile": false, "accept_language": "pl,en;q=0.9",
                              "cookies": false, "referer": false},
                  "hosts": ["..."], "sources": ["..."], "creatives": ["<sha256>"]},
  "artifacts": {"har": {"sha256": "...", "download": "/api/artifacts/<sha256>"}, "html": {"sha256": "...", "download": "/api/artifacts/<sha256>"},
                "page_screenshot": null, "ad_creatives": [{"sha256": "...", "image": "/api/artifacts/<sha256>/image"}]},
  "candidates": [{"ad": 13, "external_id": "...", "title": "...", "url_match": "exact", "url_match_label": "identyczny adres", "captured_at": "..."}],
  "message": ""
}
```

`GET /api/observations/compare?a=12&b=13`:

| Pole | Znaczenie |
|---|---|
| `a`, `b` | jak `observation` wyżej, plus `artifacts` |
| `url_match` | `exact`, `normalized` (ta sama po normalizacji: kolejność parametrów, wielkość liter, port, fragment), `domain`, `different`, `unknown` |
| `seconds_between` | odstęp między przechwyceniami albo `null`, gdy którejś daty nie znamy |
| `content` | podobieństwo z istniejących sygnatur: `page_text_minhash`, `dom_minhash`, `image_set`; `null`, gdy brak sygnatury |
| `trackers_only_a`, `trackers_only_b`, `hosts_only_a`, `hosts_only_b` | czego jedna strona używa, a druga nie |
| `verdict` | `identical`, `similar`, `different`, `insufficient`, z etykietą `verdict_label` |
| `differences` | konkretne zaobserwowane różnice zdaniami |
| `hypotheses` | tylko przy zgodnym adresie i różnej treści: cloaking, jednorazowy token wizyty, inny kontekst przeglądarki, zmiana w czasie |
| `limitations` | czego nie wiemy; zawsze zawiera zdanie, że kontekst odbiorcy jest nieznany |
| `edge` | krawędź między tymi reklamami (`id`, `relation`, `detail`) albo `null` |
| `graph` | adres grafu wokół reklamy A |
| `thresholds` | progi oceny (opis skali, nie pewność) |

- `context: null` i `captured_at: null` znaczą "nieznane". Reklamy zaimportowane przed tą funkcją nie mają zapisu obserwacji; ponowny import go uzupełnia.
- `text_excerpt`: do 300 znaków widocznego tekstu z zapisanego HTML strony, jako zwykły tekst bez znaczników, z adresami po redakcji. Pola `chars` (długość całego tekstu), `source` i `artifact` (skrót zapisu HTML) mówią, skąd pochodzi. `null`, gdy przy reklamie nie ma zapisu strony.
- `page_screenshot` jest zawsze `null`: zrzutów stron nie mamy, a zrzut reklamy (`ad_creatives`) to reklama, nie strona docelowa.
- HAR i HTML są tylko do pobrania (`/api/artifacts/{sha256}`), nigdy do renderowania. Odpowiedź nie zawiera HTML ani skryptów, adresy mają zredagowane sekrety.
- Błędy: brak albo zły parametr `400`, ta sama reklama dwa razy `400`, nieistniejąca reklama `404`.

## Test najsłabszego ogniwa (`WeakestLink`)

`POST /api/edges/{id}/weakest-link` szuka najmniejszych zestawów grup śladów, których wyłączenie zmienia relację krawędzi albo ją usuwa. Liczy tym samym silnikiem co `simulate`, niczego nie zapisuje, nie łączy się z siecią. To symulacja utraty obserwowalności jednej pary, nie przewidywanie działań oszusta i nie wniosek o grupie w grafie.

Parametry (wszystkie opcjonalne): `max_group_size` 1 albo 2 (domyślnie 2), `max_scenarios` 1 do 5000 (500), `time_limit_ms` 100 do 10000 (3000), `edge_version` jak w `simulate` (409 przy zmianie krawędzi).

Grupy śladów są stałe i wynikają z metodyki (opis: [laboratorium.md](laboratorium.md)): `kit` (ślady silnika lejka), `motif` (osoba, twarz, marka, tematyka), `infra` (domena, adres, certyfikat, rejestracja), `content` (tytuł i treść), `creative` (zrzut, kreacja, obrazy), `template` (struktura DOM), `kind:<typ>` (każdy inny typ osobno, np. `kind:funnel_id`), `unknown:<typ>` (typ spoza rejestru).

```json
{
  "edge": 3082, "edge_version": "...",
  "baseline": {"relation": "same_operator", "...": "jak Simulation.baseline"},
  "groups": [{"id": "kind:asset_host", "label": "Host zasobów lub trackera", "evidence_ids": [901], "weight_bits": 9.0}],
  "searched": {"max_group_size": 2, "scenarios_checked": 4, "scenario_limit": 500, "time_limit_ms": 3000,
               "complete": true, "stopped_reason": ""},
  "solutions": [{"groups": ["kind:asset_host"], "labels": ["Host zasobów lub trackera"], "excluded_evidence": [901],
                 "simulated": {"relation": "similar", "...": "jak Simulation.simulated"},
                 "change": "ten sam operator → podobna koncepcja"}],
  "minimal_size": 1,
  "message": "Najmniejszy zestaw zmieniający relację ma 1 grupę śladów (w sprawdzonym zakresie: pojedyncze grupy i pary, 4 scenariusze). Rozwiązań tego rozmiaru: 2."
}
```

- Kolejność: najpierw wszystkie pojedyncze grupy, potem pary, w porządku alfabetycznym identyfikatorów grup. Gdy znajdzie się rozwiązanie danego rozmiaru, większych nie szukamy (nie byłyby minimalne).
- `minimal_size` jest liczbą tylko wtedy, gdy przeszukiwanie jest pełne (`searched.complete`). Minimalność dotyczy liczby grup w sprawdzonym zakresie, nie kosztu ani prawdopodobieństwa czegokolwiek.
- Brak rozwiązania: `solutions: []` i komunikat "Nie znaleziono w sprawdzonych scenariuszach (...)". Przy przerwanym przeszukiwaniu komunikat mówi, że jest niepełne i dlaczego.
- `excluded_evidence` można podać wprost do `simulate`, żeby otworzyć scenariusz w ręcznej symulacji. Wynik jest ten sam.

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
