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
| GET | `/api/edges/{id}/assist` | | `EdgeAssist`: stan adaptera Jev i ostatnia zapisana sugestia przeglądu (opis niżej); nie wywołuje Jev |
| POST | `/api/edges/{id}/simulate` | `{"exclude":[<id dowodu>],"edge_version":"<Edge.updated_at>"}` | `Simulation`: krawędź przed i po wyłączeniu dowodów, nic nie zapisuje |
| GET | `/api/edges/{id}/suggestions` | | `Suggestions`: co sprawdzić dalej, z brakujących dowodów tej pary |
| POST | `/api/edges/{id}/weakest-link` | `{"max_group_size":2,"max_scenarios":500,"time_limit_ms":3000,"edge_version":"..."}` | `WeakestLink`: najmniejsze zestawy grup śladów, których utrata zmienia relację |
| GET | `/api/campaigns` | `?page=`, `?source=capture` (po przecinku kilka) | strona `GroupListItem`: grupy z `size`, `sources`, `cases`, `cert_pl` |
| GET | `/api/campaigns/{id}` | | reklamy, krawędzie, markery rdzeniowe |
| GET | `/api/operators` | `?page=`, `?source=capture` | strona `GroupListItem`, jak kampanie |
| GET | `/api/operators/{id}` | | jak kampania, plus lista `campaigns` operatora |
| GET | `/api/campaigns/{id}/timeline` | | `Timeline`: oś obserwacji kampanii (opis niżej) |
| GET | `/api/operators/{id}/timeline` | | `Timeline` operatora, ten sam kształt (opis niżej) |
| GET | `/api/alerts` | `?page=`, `?unseen=1` | strona `Alert`, najnowsze pierwsze: nowa reklama dołączyła do kampanii albo operatora, które były w korpusie wcześniej (opis niżej) |
| POST | `/api/alerts/{id}/seen` | `{"seen":true}` (opcjonalne, `false` cofa) | `Alert`; idempotentne; zapis chroniony jak inne (`API_WRITE_KEY`, Origin) |
| GET | `/api/graph` | `?campaign=` \| `?operator=` \| `?ad=`, `?relation=a,b`, `?limit=` | `{nodes, edges}` dla Sigma.js |
| GET | `/api/kinds` | | słownik 7 rodzin i typów markerów |
| GET | `/api/stats` | | liczby do paska stanu, w tym `alerts_unseen` (liczba nieprzejrzanych alertów) |
| GET | `/api/export/stix` | `?operator=ID` \| `?campaign=ID` (opcjonalnie) | bundle STIX 2.1 (`application/stix+json`): operator jako `intrusion-set`, kampania jako `campaign` z `attributed-to`, wskaźniki (`indicator`) dla domen, adresów IP, numerów certyfikatów i hostów zasobów z relacją `indicates`; identyfikatory trackerów i paneli lejka w `x_scamdna_identifiers`. Tylko grupy z materiałów zgłoszonych jako podejrzane (przechwycenia, zgłoszenia ręczne), bez reklam z bibliotek, osób i tokenów. Identyfikatory deterministyczne |
| GET | `/api/operators/{id}/package` | `?surowe=0` (opcjonalnie) | pakiet dowodowy operatora jako ZIP (`application/zip`, `Content-Disposition: attachment; filename="scamdna-pakiet-O-0001-RRRRMMDD.zip"`), zawartość w sekcji "Pakiet dowodowy" niżej; grupa bez reklam albo nieznana `404`, złe `surowe` `400`; każde pobranie trafia do dziennika audytu (`action=package`) |
| GET | `/api/campaigns/{id}/package` | `?surowe=0` (opcjonalnie) | to samo dla kampanii (relacje `same_campaign`) |
| GET | `/api/export` | `?source=capture` (opcjonalnie) | ZIP z wzbogaconym korpusem: `korpus/reklamy.jsonl` (reklamy z markerami), `korpus/krawedzie.jsonl` (krawędzie z dowodami), `korpus/grupy.csv`, `korpus/opis.json`; tokeny tylko jako skróty; nieznane źródło `400` |
| GET | `/api/artifacts/{sha256}` | | surowy dowód jako załącznik (nigdy się nie renderuje) |
| GET | `/api/artifacts/{sha256}/image` | | zrzut reklamy, zrzut strony z crawlera albo klatka poglądowa nagrania jako obraz (tylko artefakty obrazów) |
| GET | `/api/artifacts/{sha256}/video` | nagłówek `Range` (opcjonalny) | nagranie do odtworzenia (MP4, MOV, WebM po sygnaturze bajtów), `206` dla zakresu, `416` poza plikiem |

## Pakiet dowodowy

`GET /api/operators/{id}/package` i `GET /api/campaigns/{id}/package` zwracają jeden ZIP do przekazania prokuraturze albo innemu CERT. Wszystko leży w jednym katalogu o nazwie pliku (bez `.zip`):

| Plik | Zawartość |
|---|---|
| `raport.html` | samodzielny raport do druku (A4), bez zewnętrznych zasobów, z CSP `default-src 'none'`; obrazy osadzone jako miniatury JPEG. Streszczenie (reklamy, kampanie, okres obserwacji, domeny z datą rejestracji i wpisem CERT, reklamodawcy, osoby i marki), najmocniejsze dowody z wkładem w bitach i pewnością pary (agregat po całej grupie oraz 5 najmocniejszych par z dowodami), najsłabszy punkt (test najsłabszego ogniwa dla 3 najmocniejszych par i 2 najsłabszych powiązań grupy), oś czasu (do 80 zdarzeń), lista reklam, zrzuty (do 40), łańcuch dowodu i instrukcja weryfikacji, metoda z wersją modelu, ograniczenia. Treść stron oszustów nigdy nie trafia do raportu |
| `dowody/obrazy/{sha256}.{png,jpg,webp,gif}` | kreacje reklam, klatki nagrań, zrzuty stron (artefakty `creative_image`, `video_frame`, `page_screenshot`), bajt w bajt |
| `dowody/wideo/{sha256}.{mp4,mov,webm}` | nagrania reklam (`creative_video`) |
| `dowody/surowe/{sha256}.har`, `{sha256}.html.txt`, `OSTRZEZENIE.txt` | HAR i HTML stron oszustów wyłącznie jako pliki, bajt w bajt, niezredagowane (mogą zawierać tokeny z przechwycenia). HTML ma końcówkę `.html.txt`, żeby dwuklik nie otworzył go w przeglądarce. `?surowe=0` pomija cały katalog |
| `manifest.json` | `format`, `wygenerowano`, `grupa` (`typ`, `klucz`, `id`, `reklam`), `model`, `pliki[]` (`sciezka`, `sha256`, `rozmiar`, `rodzaj`, `typ_mime`, `zrodlo` po `redact_url`, `czas_pozyskania` = `Artifact.created_at` w UTC, `reklamy[]` z `id` i `external_id`), `pliki_pakietu[]` (sumy raportu, STIX, krawędzi, osi czasu i skryptu), `pominiete[]` (`sha256`, `rodzaj`, `rozmiar`, `powod`), `reklamy[]` (`id`, `external_id`, `zrodlo`, `adres` po redakcji, `pierwsza_obserwacja`, `rodzaj_czasu`) |
| `SHA256SUMS` | sumy wszystkich plików pakietu poza sobą, format `sha256sum -c` (`suma`, dwie spacje, ścieżka) |
| `weryfikuj.py` | sprawdzenie `SHA256SUMS` i `manifest.json` samym Pythonem (stdlib, 3.8+): `python weryfikuj.py`; kod wyjścia 0 zgodne, 1 niezgodności (zła suma, brak pliku, plik spoza listy, ścieżka poza pakietem), 2 brak pliku z sumami albo manifestu |
| `stix.json` | `GET /api/export/stix` zawężony do tej grupy |
| `krawedzie.jsonl` | krawędzie grupy (kształt jak w `export_corpus`, plus `raw_bits`, `artifact_a`, `artifact_b` i ścieżki plików w `dowody/` przy każdym dowodzie), także odrzucone (`verdict: rejected`), które nie liczą się w raporcie |
| `os-czasu.json` | pełna oś obserwacji (`Timeline`) |

Limity: artefakt większy niż 50 MB, ponad łączny limit 1 GiB, brakujący w magazynie albo z sumą niezgodną z zapisaną (uszkodzony) nie wchodzi do pakietu i ma wpis w `pominiete` z powodem. Surowe pliki nie są redagowane, bo redakcja zmieniłaby sumę i zerwała łańcuch dowodu; wszystko, co generujemy (raport, manifest, krawędzie, STIX, oś czasu), ma adresy po `redact_url`. Pakiet nie jest podpisany elektronicznie: sumy dowodzą niezmienności po utworzeniu, nie autentyczności oryginału.

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
| `link_observable` | jak `ad_first_seen` dołączającej reklamy | liczba powiązań | `count`, `relations` (liczba według relacji), `partners` i `edges` (do 50), `max_probability`, `truncated`, `tied` |
| `snapshot` | `observed`, skan biblioteki | | `active` |
| `ad_last_seen` | `observed`, skan biblioteki | | |
| `cert_pl_added`, `cert_pl_removed` | `reported`, Lista Ostrzeżeń CERT Polska | domena | |

Zasady:

- `ads` to reklamy grupy, których dotyczy zdarzenie. Domena, certyfikat albo ślad mogą łączyć kilka.
- Odnowienia certyfikatu z tymi samymi reklamami i tymi samymi pozostałymi domenami to jedno zdarzenie `cert_issued` z `count`. Wspólny certyfikat kilku reklam to jedno zdarzenie z nimi wszystkimi.
- `trace_first_observed` dotyczy domen, adresów IP, identyfikatorów analityki, pikseli i lejka, kreacji, kontaktów i kont reklamowych. Gdy kilka reklam ma tę samą najwcześniejszą datę, wszystkie są w `ads`, a `tied` jest `true`: nie rozstrzygamy, która była pierwsza.
- `link_observable` to chwila, od której dołączająca reklama i wcześniej widziane reklamy grupy były w ręku, a nie data, w której operator je połączył. Jedno zdarzenie na reklamę, która dołącza, z liczbą powiązań, zamiast jednego na parę (grupa 49 reklam miała 1175 zdarzeń par). Przy tej samej chwili obu reklam para trafia do reklamy o wyższym numerze z `tied: true`. Kampania pokazuje krawędzie `same_campaign`, operator także `same_operator`. Odrzucone przez analityka pomijamy.
- Oś nie twierdzi, że jedna domena zastąpiła drugą ani że operator zmienił taktykę. Pokazuje kolejność obserwacji.
- Ostatnie wystąpienie i migawki są tylko dla reklam z bibliotek, bo dla przechwyceń i zgłoszeń ręcznych to data importu. Z tego samego powodu pomijamy pierwsze wystąpienie przechwycenia, które w paczce nie miało daty.
- `undated` liczy to, czego nie da się umieścić w czasie: `ads` (reklamy bez daty), `traces` (ślady tylko w takich reklamach), `links` (krawędzie z taką reklamą), `certificates` (numery certyfikatów bez daty wystawienia, np. z `dns_ssl.json`).

## Pamięć sprzeciwu

Decyzja analityka (`POST /api/edges/{id}/verdict`) ma powód i notatkę. Zmienia tylko werdykt krawędzi: relacja, bity, dowody i grupy zostają takie, jakie policzył silnik. Każda decyzja to nowy, niezmienny wpis historii.

Powody (`reason`, lista z etykietami w `GET /api/kinds` jako `verdict_reasons`): `shared_tool` (wspólne narzędzie albo silnik), `shared_infrastructure` (współdzielona infrastruktura), `extraction_error` (błędna ekstrakcja), `no_independent_confirmation` (brak niezależnego potwierdzenia), `confirmed_by_analyst`, `other` (powód w notatce). Bez `reason` decyzja zapisuje się z powodem `unknown`, więc stary klient działa. `unknown` mają też wszystkie decyzje sprzed pamięci sprzeciwu, przeniesione z dziennika audytu jako `legacy` bez migawki. Uzasadnień nie wyciągamy z notatek.

`GET /api/edges/{id}/decisions` zwraca `{"edge": 12, "current": "rejected", "decisions": [EdgeDecision]}`. `EdgeDecision`: `id`, `edge` (null, gdy krawędź zniknęła przy przeliczeniu), `ad_a`, `ad_b`, `verdict`, `previous_verdict`, `reason`, `reason_label`, `note`, `legacy`, `user`, `created_at`, `has_snapshot`, `snapshot`.

`snapshot` to stan z chwili decyzji, bo dowody krawędzi są przebudowywane przy każdym przeliczeniu: `relation`, `bits`, `probability`, `decisive`, `duplicate`, `families`, `model_version`, `edge_version` (wersja dowodów, ta sama co w Laboratorium dowodów), `evidence` (rodzaj, rodzina, wartości po redakcji do 300 znaków, podobieństwo, `df`, `corpus_n`, wkład w bitach, `decisive`, `kit`, `motif`), `groups` (kampania i operator obu reklam), `ads` (źródło, sprawa, adres po redakcji).

#### Nagrania w karcie reklamy

`AdDetail.videos` to lista `VideoMaterial`: `sha256`, `name`, `size`, `playable`, `url` (`/api/artifacts/{sha}/video`, gdy plik jest w magazynie), `duration_s`, `fps`, `frames`, `width`, `height`, `poster`, `original`, `speech`, `missing`.

- `poster`: klatka poglądowa z pierwszej sekundy (dla krótszych nagrań 10% długości). `at_s` to sekunda według dekodera, bo przewijanie trafia w najbliższą klatkę kluczową. `position` to `at_s / duration_s`, `url` prowadzi do obrazu.
- `original`: `duration_s` to długość oryginału z metadanych pobrania (`.info.json` z yt-dlp), jeśli tam jest. `clip` mówi, czy plik jest krótszym wycinkiem oryginału. `null` oznacza, że nie wiadomo.
- `missing`: powody braków po polsku, np. plik ponad limit 60 MB magazynu (`playable: false`), brak długości oryginału w metadanych albo nagranie zaimportowane przed odczytem metadanych.
- `speech`: mowa z nagrania zamieniona na tekst albo `null` (nagranie bez dźwięku, cisza, kanał wyłączony przez `TRANSCRIBE=off`, brak modelu, nagranie jeszcze nie przetworzone). Pola: `source` (zawsze "mowa z nagrania"), `text` (adresy po redakcji, ten sam tekst trafia do tekstu reklamy), `language`, `model`, `audio_s` (ile sekund dźwięku rozpoznano), `truncated` (nagranie dłuższe niż limit 120 s albo przerwane limitem czasu). To tekst z modelu rozpoznającego mowę: może zawierać pomyłki.
- Z nagrania odczytujemy metadane kontenera, jedną klatkę poglądową, 8 klatek do analizy i mowę. Uzupełnienie metadanych dla zaimportowanych spraw: `python manage.py probe_videos --root /data/raw`. Uzupełnienie mowy: `python manage.py transcribe_videos [--root /data/raw] [--all] [--ad ID] [--reanalyze]`.

## Sugestia Jev

`GET /api/edges/{id}/assist` tylko czyta: nie wywołuje Jev i niczego nie zapisuje. Sugestie liczy polecenie `jev_review` ([jev.md](jev.md)).

`EdgeAssist`: `edge`, `mode` (`off`, `shadow`, `on`), `model`, `question_version`, `question` (treść pytania), `case_data_allowed`, `visible`, `status`, `suggestion`, `premises`, `analyst`, `precedent_ranking`, `notice`.

| Sytuacja | `status` | `suggestion` | `visible` |
|---|---|---|---|
| `JEV_MODE=off` | `disabled` | `null` | `false` |
| tryb `shadow` i jest zapisana sugestia | `shadow` (plus `shadow.recorded_at`, `shadow.status` bez odpowiedzi) | `null` | `false` |
| brak zapisanej sugestii | `none` | `null` | `false` |
| tryb `on`, odpowiedź | `ok` albo `abstain` | odpowiedź | `true` |
| tryb `on`, błąd usługi | `unavailable`, `timeout`, `error`, `unauthorized`, `payment`, `rate_limited` | metadane bez odpowiedzi | `false` |

`suggestion`: `status`, `answer` (`przeglad` albo `spojne`, `null` bez odpowiedzi), `label`, `probabilities`, `confidence`, `uncertain` (`abstain` albo `confidence` poniżej 0,7), `model`, `served_model`, `question_version`, `created_at`, `stale` (od wysłania zmieniły się dowody albo przesłanki), `error` (sam kod, bez treści odpowiedzi usługi).

`premises` to bieżąca struktura przesłanek w tym samym kształcie, który trafia do modelu: relacja, bity, grupy śladów, bez wartości. `analyst` to werdykt, powód i data ostatniej decyzji z pamięci sprzeciwu. Rozumowania modelu nie ma i interfejs go nie wymyśla. `precedent_ranking` ma wartość `not_validated`, bo kolejności precedensów model nie ustala ([ewaluacja #72](jev.md#ewaluacja-72-21112026)). Wynik nie zmienia krawędzi, grup, decyzji ani zwykłego potoku analizy.

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
Zdarzenie `crawl/info` niesie łańcuch przekierowań (`payload.chain`, `via`: `http`, `meta_refresh` albo `js`), silnik (`payload.engine`: `browser` albo `http`), skrót zrzutu strony (`payload.screenshot`, obraz pod `GET /api/artifacts/{sha}/image`, albo `null`), `payload.har` (czy był ruch z przeglądarki) i `payload.notes` (zablokowane żądania, powrót do HTTP), `extract/info` liczbę markerów per rodzina, `cluster/done` kampanię i operatora.

## Relacje

| Relacja | Znaczenie | Warunek |
|---|---|---|
| `same_campaign` | to samo źródło i ta sama opowieść | pewność co najmniej 0,9, marker rozstrzygający albo dwa niezależne potwierdzenia, zgodna narracja |
| `same_operator` | to samo zaplecze, inna opowieść | jak wyżej, bez zgodnej narracji |
| `similar` | podobna koncepcja | zgodna narracja, kreacja albo osoby, albo ten sam silnik lejka bez śladu operatora; brak dowodu wspólnego zaplecza |

Na listach grup `sources` to liczba reklam według źródła (`capture` to materiały spraw, `microsoft` i inne to biblioteki reklam), `cases` to liczba różnych spraw, a `cert_pl` to liczba reklam z domeną na Liście Ostrzeżeń CERT Polska. `?source=capture` zostawia grupy, w których jest choć jedna reklama z materiałów spraw. Rozmiar i skład grupy są zawsze pełne, a kolejność to dalej od największej.

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
- `page_screenshot` to zrzut wyrenderowanej strony docelowej z crawlera z przeglądarką (`{sha256, image}`), dla materiałów z przechwycenia `null`. Zrzut reklamy (`ad_creatives`) to reklama, nie strona docelowa.
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

## Wagi modelu (`Weights`)

`GET /api/weights`: wagi eksperckie i uczone (EM, `manage.py estimate_weights`) każdego typu markera obok siebie. Tylko odczyt. Plik z wagami to `MODEL_WEIGHTS_PATH` (domyślnie `data/models/wagi.json`).

| Pole | Znaczenie |
|---|---|
| `active` | `expert` albo `learned`: wagi, którymi silnik liczy teraz (ustawienie `MODEL_WEIGHTS`) |
| `model_version` | `fs-5` przy `expert`, `fs-6` przy `learned` |
| `learned_available` | czy jest czytelny plik z wagami uczonymi |
| `learned_error` | `null` albo powód: plik nieczytelny, albo `learned` bez pliku |
| `meta` | `null` albo metadane uczenia: `ads`, `pairs`, `iterations`, `converged`, `created`, `stable`, `unstable_kinds`, `classes` (osobno `source` i `story`: `match_share`, `expected_matches`) |
| `calibration` | `null` albo `{fitted, decisions, confirmed, rejected, note, coefficients?}`. Bez decyzji `fitted: false` i `note: "brak kalibracji: 0 decyzji"` |
| `kinds[]` | `{code, label, family, family_label, soft, decisive, cap, expert, learned}` |
| `kinds[].expert` | `{m, f0, bits}` z `evidence/kinds.py`. `m` i `f0` są `null` dla typów miękkich. `bits` to `min(cap, log2(m/f0))` albo `cap` |
| `kinds[].learned` | `null` bez pliku, inaczej `{source, m, u, u_basis, bits, pairs_agree, bits_std}`. `source`: `em` albo `expert` (za mało par, wartość ekspercka). `u_basis`: `population` albo `candidates`. `bits_std`: odchylenie z bootstrapu po reklamach, `null` dla `expert` |

## Alerty (`Alert`)

Alert powstaje w etapie `cluster`, gdy reklama (import paczki, upload, skan biblioteki, zgłoszenie URL) dołącza do grupy, która istniała przed nią i miała już inne reklamy. Pierwsza reklama nowej kampanii alertu nie daje, a kampania powstała z dwóch dotąd niepowiązanych reklam nie jest "znana". Ponowne uruchomienie etapów nie dubluje alertów (unikalność: reklama i rodzaj).

| Pole | Znaczenie |
|---|---|
| `id`, `created_at` | identyfikator i czas zapisu |
| `kind` | `joined_campaign` (nowa odsłona znanej kampanii), `new_campaign_known_operator` (reklama bez kampanii albo z nową, ale ze znanym operatorem; ta sama sytuacja co ocena `known_operator`), `joined_operator` (reklama dołączyła do znanej kampanii i scaliła dwie grupy operatora) |
| `kind_label` | polski opis rodzaju |
| `ad`, `ad_title` | reklama, która wywołała alert |
| `campaign`, `campaign_id` | klucz `K-0001` i identyfikator kampanii; `null`, gdy reklama nie ma kampanii |
| `operator`, `operator_id` | klucz `O-0001` i identyfikator operatora; `null`, gdy go nie ma |
| `description` | jedno zdanie po polsku |
| `evidence` | najwyżej 3 najmocniejsze typy markerów łączące reklamę z grupą: `{kind, label, family, bits, value}`, malejąco po `bits` |
| `seen`, `seen_at` | czy przejrzany i kiedy |

Lista jest stronicowana jak inne (`count`, `next`, `previous`, `results`). `?unseen=1` zostawia nieprzejrzane.

## Czego API jeszcze nie ma

Stan źródeł i skanów, przegląd bazy osób, kolejka etykietowania, raporty, role i klucze. Interfejs nie powinien udawać tych danych.
