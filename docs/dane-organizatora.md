# Dane organizatora: co w nich jest i co znalazł silnik

Stan na 2026-11-21. Dane leżą lokalnie w `data/raw/` i nie trafiają do gita: zawierają żywe adresy oszustów i tokeny.

## Dwie paczki

| Paczka | Skąd | Zawartość |
|---|---|---|
| `nask` | `DANE.zip` od organizatora | 10 spraw, 13 stron |
| `nask-backup` | archiwum ukryte w zagadce ze strony z zajawką | 15 spraw, 15 stron |

Import i analiza obu:

```bash
python manage.py import_bundle /data/raw/nask --name nask
python manage.py import_bundle /data/raw/nask-backup --name nask-backup
```

## Format sprawy

Jeden katalog to jedna sprawa. W środku w dowolnej kombinacji:

| Plik | Co to jest | Co z niego bierzemy |
|---|---|---|
| `Tytuł strony.html` + `Tytuł strony_files/` | strona zapisana z przeglądarki, adres w komentarzu `saved from url` | DOM po wykonaniu skryptów, tekst, tytuł, identyfikatory |
| `domena.har` | ruch sieciowy z narzędzi deweloperskich | łańcuch przekierowań, ścieżki zaplecza, hosty zasobów, żądania POST, adres IP |
| `Zrzut ekranu *.png`, `IMG_*.PNG`, `reklama_*.png` | reklama w kanale albo jej karta w Bibliotece Reklam Mety | OCR: reklamodawca, tekst, numer biblioteki |
| `*.mp4` + `*.info.json` | wideo reklamy pobrane yt-dlp | numer reklamy w Bibliotece Reklam |
| `katalog/manifest.json` + `page.har` + `dom.html` | zrzut z narzędzia `page-capture 0.1.0` | jak HAR i HTML |
| `archive_<domena>_<czas>/` | archiwum z narzędzia NASK: `archive_info.json`, `dns_ssl.json`, `network.har`, `html/` | adres IP i numer seryjny certyfikatu; reszta tylko gdy brak zapisu z przeglądarki |
| `strona_N/` | osobna strona tej samej sprawy | osobna reklama w korpusie |

Jeden HAR albo jedna zapisana strona to jedna reklama w korpusie. Zapis HTML i HAR tej samej domeny w jednym katalogu łączymy w jedną. Zrzuty reklamy z katalogu sprawy dołączamy do każdej strony tej sprawy.

## Wynik łączenia

28 stron z 25 spraw. Silnik nie dostał żadnej informacji, które sprawy do siebie pasują. Po ponownym imporcie 2026-11-22 (model `fs-5.1`): 19 krawędzi `same_campaign`, 13 `same_operator`, 35 `similar`; 3 operatorów, 4 kampanie, 14 stron bez operatora. Wcześniej (21.11, `fs-5`) było 20 i 34: jedna para z nask/61 przeszła z kampanii na podobieństwo po #267.

### Operator A: 8 stron, 7 domen, 2 kampanie

| Sprawa | Domena | Co udaje | Kampania |
|---|---|---|---|
| nask/1 | civicdaybook.live | artykuł Gazeta.pl, narracja A | A |
| nask/2 | acrosscommunities.live | ten sam artykuł | A |
| backup/p1, p2 | dorquesio.click | ten sam artykuł | A |
| backup/p7 | wernulio.live | ten sam artykuł | A |
| backup/p15 | lundevra.live | ten sam artykuł | A |
| backup/p3 | falmurek.live | artykuł "PILNE", narracja B, osoba 1 | B |
| backup/p4 | grentavo.click | ten sam szablon artykułu, osoba 2 | B |

Co je łączy, mimo różnych domen, adresów IP i treści:

- **Identyfikatory strony w panelu lejka** (`funnel_id`) z treści żądań POST: te same UUID na różnych domenach. To obiekt na koncie operatora w panelu, nie cecha programu. Każda krawędź operatora A ma taki identyfikator.
- **Piksel Meta** wspólny dla części stron, w tym między kampaniami A i B.
- **Ścieżki zaplecza** (`kit_path`): `GET /aio-static/sdk/main.js`, `POST /api/v1/trigger/field/{id}/`, `POST /api/v1/agent/persist-session-record/{id}/{id}`, zasoby pod `/_cdn/production/landing-cdn/`. To ten sam silnik lejka. Drugie z żądań wysyła nagranie sesji ofiary.
- **Zestaw parametrów** (`url_param_keys`): `utm_campaign, utm_content, utm_id, utm_medium, utm_visit`. Nazwy wyglądają jak zwykłe UTM, ale `utm_visit` nim nie jest, a wartości to losowe tokeny. Ten zestaw ustawia silnik lejka, więc razem ze ścieżkami zaplecza liczy się jako jedno potwierdzenie.

Sześć stron z narracją A to jedna kampania: tekst zgodny w 100%, te same obrazy, a sprawy p1 i p2 to duplikat (to samo przechwycenie dwa razy). Strony z narracją B to druga kampania: ten sam szablon artykułu z podmienioną osobą.

### Ten sam silnik lejka, bez śladu operatora: sprawy 48, 61 i p11

| Sprawa | Domena | Co ją wiąże z operatorem A |
|---|---|---|
| nask/48 | novumfy.com | ścieżki zaplecza, zestaw parametrów, osoby i marka TVN24 |
| nask/61 | glowpixel.org (3 strony) | ścieżki zaplecza, zestaw parametrów |
| backup/p11 | sfuxd.com | ścieżki zaplecza, zestaw parametrów |

Te strony stoją na tym samym silniku lejka co operator A, ale nie dzielą z nim żadnego śladu konta ani infrastruktury: identyfikatora w panelu, piksela, konta reklamowego, hosta zasobów, adresu IP, certyfikatu. Silnik lejka mógł kupić każdy, więc system pokazuje te pary jako `similar` z dowodem "ścieżka zaplecza strony" i nie dopisuje ich do operatora. Sprawa 61 sama jest kampanią: trzy strony spięte kontem Google Ads, domeną i zrzutem reklamy.

Do 2026-11-21 te sprawy wisiały przy operatorze A (13 stron, 3 kampanie). Przegląd krawędzi pokazał, że jedynym drugim potwierdzeniem był zestaw parametrów, który generuje ten sam silnik. Poprawka w `similarity/fusion.py` (model `fs-4`): ślady programu (`kit_path`, `url_param_keys`, `url_path_tpl`) to jedno potwierdzenie, a wspólne motywy (osoba, marka, tematyka) nie są potwierdzeniem w ogóle.

### Operator B: 3 strony, 2 domeny

| Sprawa | Domena |
|---|---|
| nask/2 (drugi HAR), nask/3 | healthlinkq.pro |
| backup/p5 | smartcoved.pro |

HAR sprawy 3 leżał w katalogu sprawy 2. Silnik połączył je po domenie i treści. Sprawę p5 z drugiej paczki dołączył po wspólnym hoście zasobów (`crimsonbase.pro`), który jest własną domeną operatora, a nie publicznym CDN-em. Ścieżka zaplecza `/include/events-stat.js` i zestaw parametrów `clickid, key, pixel_fb` to drugie, niezależne potwierdzenie. Krawędź do p5 ma tylko strona z HAR-em (drugi HAR w katalogu sprawy 2). Strona z samego zapisu HTML w sprawie 3 ma z p5 relację `similar` i trafia do operatora przez duplikat.

### Dwie strony pod jednym adresem w sprawie 61

Ten sam pełny adres na `glowpixel.org` (z tym samym tokenem `utm_visit`) dał w odstępie 2 min 41 s dwie różne strony: ofertę z pikselem konwersji Google Ads (strona 2) i neutralny "portal analiz" bez trackerów (strona 3). Najprostsze wyjaśnienia to cloaking albo jednorazowy token wizyty. Kto i skąd przechwytywał, nie wiemy, więc nie twierdzimy, że strona 3 jest "dla moderacji". Szczegóły: [dwie-twarze.md](dwie-twarze.md). Nazwa reklamodawcy na zrzucie reklamy to `Glowpixel`, czyli nazwa domeny białej strony. OCR zrzutu i nazwa domeny dają ten sam marker `page_name`.

### Lista Ostrzeżeń CERT Polska

Część domen z obu paczek jest na liście (`civicdaybook.live`, `healthlinkq.pro`, `lundevra.live`, `smartcoved.pro`, `spiritualityinsports.org`). Pozostałe domeny tego samego operatora na liście nie figurują, mimo że stoją na tym samym zapleczu. To praktyczny pożytek z łączenia: jedna znana domena wskazuje resztę.

### Bez powiązań

nask/5 (sama reklama wideo), nask/10, nask/14, nask/36, nask/47, backup/p6, p8, p9, p10, p12, p13, p14. Każda stoi na innym zapleczu. Do tego nask/48 i backup/p11 opisane wyżej. Sprawa p8 ma relację `similar` z p11: ten sam tytuł strony i te same obrazy, ale inne zaplecze, więc silnik nie przypisał jej do operatora.

### Certyfikaty z crt.sh

Sprawdzone 2026-11-21 dla 23 domen z obu paczek. crt.sh odpowiedział dla 18, dla 5 nie (`konbjk.com`, `lundevra.live`, `meroporepufulo.life`, `move-fitlum.top`, `zenithlab.ink`). Żadne dwie domeny z paczek nie dzielą certyfikatu, więc ten ślad nie dokłada krawędzi w korpusie. Daje za to tropy poza korpusem:

- certyfikat `sfuxd.com` (sprawa p11) obejmuje też `zixips.com`,
- certyfikat `spiritualityinsports.org` obejmuje też `spiritualityinsports.com`, `spiritualityandsports.org` i `spiritualityandsports.com`.

Analiza wypisuje takie domeny w zdarzeniu etapu `enrich`. Domeny `abundancecaller.com` i `glowpixel.org` mają ponad 50 certyfikatów, bierzemy 50 najnowszych.

### Łowca domen na stosie (22.11.2026)

Przebieg `manage.py hunt --days 30 --max-queries 12 --max-crawl 20` na 34 operatorach korpusu (327 reklam), z kontenera `worker`, crawler `BrowserFetcher` w piaskownicy:

| | Liczba |
|---|---|
| tokeny do zapytań (najlepsze 3 na operatora, bez słów ogólnych) | 38 |
| zapytania do crt.sh (limit 12, przebieg przerwał się po 11) | 11: 9 odpowiedzi z 0 certyfikatów, 2 bez odpowiedzi (`acrosscommunities`, `neonica`) |
| kandydaci z crt.sh | 0 |
| domeny z Listy CERT pasujące do tokenów (okno 30 dni) | 11, z nich 10 kandydatów powyżej progu 0,45 |
| sprawdzone crawlerem | 10: 4 odrzucone (0 bitów wspólnych śladów), 6 niedostępnych, 0 potwierdzonych |

Kandydaci pochodzą z listy CERT, nie z crt.sh: 8 domen `ceneo-*.shop` (operator O-0021, token `ceneo`) i 2 domeny `.info` z tokenem `linea` (O-0012). Operator O-0021 to dwie reklamy prowadzące na prawdziwe `ceneo.pl`, więc strony `ceneo-*.shop` to podszycia pod markę, a nie to samo zaplecze. Trzy z nich działały i dostały 0 bitów (żaden wspólny marker z reklamami operatora), co jest właściwym wynikiem: łowca nie przypisuje podszywacza do operatora, którego marka jest podszywana. Z niedostępnych pięć nie rozwiązało się w DNS (w tym jedna domena `.info`), jedna odpowiedziała 403. "Odrzucony" znaczy brak śladów operatora, nie że domena jest bezpieczna: wszystkie są na liście CERT.

Drugi przebieg, `--operator O-0001 --days 90 --max-queries 3`: 1 zapytanie bez certyfikatów, 2 bez odpowiedzi, lista CERT dała 1 domenę, ale ta jest już w korpusie i została odfiltrowana.

Samokontrola potwierdzenia na prawdziwych stronach: po dwie domeny sześciu operatorów (z korpusu, więc wspólny jest też marker domeny, którego prawdziwy kandydat mieć nie może) przeszły przez `observe` i `evaluate`. 5 z 10 nie odpowiedziało crawlerowi (403, 404, 522), z pięciu pozostałych cztery wyszły jako `confirmed` (21,9 do 77,7 bita, rzadkie markery: GTM, e-mail) i jedna jako `candidate` (13,7 bita, bez markera rozstrzygającego). Bez markera domeny operator O-0008 zostałby `candidate` (sam GTM, 8,9 bita). To sprawdza tor oceny, a nie skuteczność wyszukiwania nowych domen.

Czego ten pomiar nie pokazuje: ani jednego potwierdzenia nowej domeny z certyfikatu. Powody:
- crt.sh dla naszych tokenów (nazwy własne z bibliotek reklam, np. `freecash`, `bookinghost`) nie ma w ostatnich 30 dniach certyfikatów, więc nie było z czego wybierać. Sprawdzone ręcznie, `curl` na te same tokeny, też bez `exclude=expired`: pusta lista.
- crt.sh bywa przeciążony: z 14 zapytań tego dnia 4 skończyły się 502 albo brakiem odpowiedzi, a po dwóch porażkach z rzędu przebieg się przerywa. Ten sam token wracał potem z poprawną (pustą) odpowiedzią.
- Tokeny z korpusu Microsoft Ad Library to w większości jedna domena na operatora i nazwa marki, a nie konwencja nazewnictwa (`inwestycje-12`), po której da się szukać świeżych domen. Najlepszy materiał do łowcy to operatorzy z wieloma domenami o wspólnym wzorcu, takich jak operator A z paczki organizatora.
- Limit 12 zapytań objął 11 z 34 operatorów. Pozostali czekają na kolejne przebiegi (harmonogram jest założony wstrzymany).

### Odporność na brak materiału

Obie paczki zaimportowaliśmy od zera w czterech wariantach, na osobnym stosie (2026-11-22, model `fs-5.1`, `scripts/odpornosc.py`): pełny, bez plików HAR (także `network.har` z archiwów NASK), bez zapisów stron z przeglądarki (HTML i katalogi `_files`) i bez zrzutów reklam. Liczymy połączenia wspólnego źródła (`same_campaign`, `same_operator`) między stronami z pełnego importu, których jest 32 (było 33: jedna para z nask/61 nie jest już wspólnym źródłem po #267).

| Wariant | Stron | Zostało | Zniknęło razem ze stroną | Zniknęło przez utratę śladów | Nowe połączenia wspólnego źródła |
|---|---|---|---|---|---|
| bez HAR | 27 z 28 | 18 | 2 | 12 | 0 |
| bez zapisu strony | 26 z 28 | 30 | 2 | 0 | 0 |
| bez zrzutów reklam | 28 z 28 | 32 | 0 | 0 | 0 |

Co z tego wynika:

- **Brak materiału nie tworzy fałszywych połączeń.** W żadnym wariancie nie powstało połączenie wspólnego źródła, którego nie było w pełnym imporcie. Mniej danych daje mniej powiązań, a nie złe powiązania.
- **HAR niesie ślady operatora.** Identyfikatory strony w panelu lejka i hosty zasobów są tylko w ruchu sieciowym, więc bez HAR odpada 12 połączeń operatora A między kampaniami. Zostają połączenia, które stoją na treści, pikselu z kodu strony i domenie. Strona `healthlinkq.pro` z drugiego HAR w sprawie 2 znika w całości, bo była tylko w HAR.
- **Zapis strony jest zastępowalny.** Gdy brakuje HTML z przeglądarki, dokument strony jest w HAR, więc żadne połączenie nie ginie przez utratę śladów. Giną tylko strony, które miały wyłącznie zapis HTML.
- **Zrzut reklamy nie rozstrzyga.** Bez zrzutów żadne połączenie nie znika (32 z 32). Wcześniej znikało jedno, między stronami sprawy 61, spięte zrzutem reklamy i nazwą reklamodawcy z OCR, ale po #267 ta para jest tylko `similar`.

Odtworzenie (czyści korpus, więc tylko na osobnym stosie): `python scripts/odpornosc.py --paczki data/raw/nask data/raw/nask-backup`.

### Wrażliwość na wagi modelu

Wagi są eksperckie, więc sprawdziliśmy, jak bardzo wynik od nich zależy (2026-11-22, model `fs-5.1`, `python manage.py weight_sensitivity`, tylko odczyt). Na 67 krawędziach między stronami z obu paczek (32 wspólnego źródła) przeliczyliśmy relacje tym samym silnikiem przy zmienionych wagach i progach.

| Zmiana | Krawędzie ze zmienioną relacją | Utrata wspólnego źródła | Nowe wspólne źródło |
|---|---|---|---|
| szansa wstępna ×0,1 albo ×10 | 0 | 0 | 0 |
| próg pewności 0,8 albo 0,95 zamiast 0,9 | 0 | 0 | 0 |
| niezależne potwierdzenie od 5 bitów zamiast 4 | 0 | 0 | 0 |
| niezależne potwierdzenie od 3 bitów | 2 | 0 | 2 |
| siła wszystkich dowodów ×0,5 | 6 | 1 | 0 |
| siła wszystkich dowodów ×1,5 | 4 | 0 | 3 |
| siła jednego typu ×0,5 albo ×1,5 (31 typów po kolei) | najwyżej 4 | 0 | najwyżej 1 |

- **Rdzeń operatora A nie zależy od wag.** Połączenia spięte identyfikatorami z panelu lejka i pikselem Meta nie zmieniają się w żadnym scenariuszu.
- **Ruszają się 4 pary graniczne, zawsze te same.** Drugi HAR sprawy 2 z p5 (operator B na jednym hoście zasobów), sprawa 3 z p5, sprawa 48 ze sprawą 61 i p11 z p8 (ta sama treść albo ten sam silnik na innym zapleczu). To dokładnie pary, które laboratorium dowodów i przegląd krawędzi opisują jako kruche albo celowo tylko "podobne".
- **Słabsze wagi niczego nie sklejają, mocniejsze sklejają tylko pary graniczne.** Przy wagach ×1,5 albo progu 3 bitów kopie treści stałyby się kampaniami, dlatego zostawiamy próg 4 bity i obecne wagi.

### Kopia kreacji przestała być markerem rozstrzygającym (22.11.2026)

`creative_phash` ma `decisive=False`: sama kopia zrzutu reklamy plus podobny tekst to pokrewieństwo treści, więc najwyżej `similar`. Uzasadnienie w [metodyka.md](metodyka.md), sekcja 6. Kontakty zostają rozstrzygające.

Pomiar na stosie 8010, tylko odczyt: zapisane dowody wszystkich 3121 krawędzi przeliczone `fusion.score_pair` z `decisive` True (stan zapisany, zgodny z bazą w 3121 z 3121 krawędzi) i False.

| Zbiór | Krawędzi | Zmienione relacje | Grupy operatorów przed i po | Grupy kampanii przed i po |
|---|---|---|---|---|
| wszystkie | 3121 | 1 (`same_campaign` na `similar`) | 34 i 34, wszystkie bez zmian | 33 i 33, wszystkie bez zmian |
| materiały spraw (`capture`) | 67 | 1 (ta sama) | 3 i 3, bez zmian | 4 i 4, bez zmian |
| pozostałe źródła | 3054 | 0 | 31 i 31 | 29 i 29 |

Relacje w materiałach spraw przed: 20 `same_campaign`, 13 `same_operator`, 34 `similar`. Po: 19, 13, 35. Rdzeń operatora A (8 reklam z 8 w jednej grupie operatora) zostaje w całości, żadna grupa się nie rozpada.

Jedyna zmieniona krawędź to para wewnątrz sprawy nask/61 (reklamy 11 i 13, oferta i neutralna strona "portal analiz"). Łączyły je wyłącznie zrzut reklamy dołączony do każdej strony sprawy (`creative_phash`, 12 bitów), nazwa reklamodawcy z tego samego zrzutu (`page_name`, 8 bitów) i embedding obrazu, bez żadnego śladu zaplecza. Po zmianie to `similar`. To trafiona pułapka: kopia zrzutu i nazwa z jego OCR to ta sama treść, nie wspólne zaplecze. Skład grup się nie zmienia, bo reklamy zostają w jednej kampanii przez krawędzie z reklamą 12 (strona sprawy 61 z kontem Google Ads). Wersja modelu: `fs-5.1`.

### Próba jury: "Spróbuj zgubić kampanię" (22.11.2026)

Eksperyment na osobnym stosie (świeży import obu paczek: 28 reklam, 4 kampanie, 3 operatorów, model `fs-5.1`), przez prawdziwy `POST /api/analyses/upload` (ZIP jednej sprawy) i `GET /api/analyses/{id}`. Skrypt `scripts/proba_jury.py` zapisuje wynik do pliku, dopiero potem czyta plik etykiet (które sprawy analityk uznał za jedną grupę). Sprawy i etykiety to argumenty, w skrypcie nie ma danych organizatora. Polecenie (venv backendu, bo potrzebny Pillow):

```bash
python scripts/proba_jury.py --api http://localhost:8300 --paczki data/raw \
  --sprawy nask/1 nask-backup/p7 nask-backup/p15 nask/3 --pulapka nask/1 \
  --etykiety <etykiety.json> --wynik <wynik.json> --robocze <katalog poza repo>
```

Ocena samego zapisanego wyniku bez wysyłania: dodaj `--tylko-ocena`. Etykiety: `{"grupy": {"A": ["nask/1", ...], "B": ["nask/3", "nask-backup/p5"]}}`. Przebieg: ok. 3 do 4 s na analizę wariantu (pierwsza ok. 30 s, rozgrzanie modeli).

**Próba 1: przebranie.** Trzy sprawy operatora A (nask/1, backup/p7, backup/p15) i nask/3 z operatora B (sprawa bez HAR). Zrzut reklamy przycięty o 10% (po 5% z każdego boku) i zapisany jako JPEG q=60, w zapisanej stronie podmienione 3 zdania na zmyślone, adres i domena zamienione na zmyśloną domenę `.example` (zestaw parametrów adresu zostaje), katalog `_files` bez zmian. Dwa warianty sprawy z HAR: bez HAR oraz z HAR, w którym podmieniono tylko domenę (jak przy przeniesieniu tego samego lejka na nową domenę).

| Wariant | Grupa wariantu | Do oryginału | Markery wspólne z oryginałem | Co przetrwało (rodzaje) |
|---|---|---|---|---|
| nask/1, bez HAR | K-0001, O-0001 jak oryginał | `same_campaign`, 52 bity | 11 z 51 | treść, szablon, osoby, twarz, tytuł |
| nask/1, HAR z nową domeną | K-0001, O-0001 | `same_campaign`, 87 bitów, marker rozstrzygający | 41 z 51 | wszystko oprócz domeny i rejestracji |
| backup/p7, bez HAR | K-0001, O-0001 | `same_campaign`, 52 bity | 11 z 46 | jak wyżej |
| backup/p7, HAR z nową domeną | K-0001, O-0001 | `same_campaign`, 84 bity, rozstrzygający | 42 z 46 | wszystko oprócz domeny |
| backup/p15, bez HAR | K-0001, O-0001 | `same_campaign`, 58 bitów | 12 z 49 | jak wyżej |
| backup/p15, HAR z nową domeną | K-0001, O-0001 | `same_campaign`, 93 bity, rozstrzygający | 42 z 49 | wszystko oprócz domeny |
| nask/3, brak HAR w sprawie | K-0002, O-0002 jak oryginał | `same_campaign`, 60 bitów | 12 z 20 | treść, szablon, tytuł, osoby |

Wynik: 7 z 7 wariantów wróciło do kampanii i operatora swojego oryginału, żaden nie trafił do obcej grupy. Co zniknęło zawsze: domena, rejestracja i serwery nazw, `page_name` i `creative_phash` (przycięcie i JPEG zmieniają skrót kreacji, a OCR przyciętego zrzutu czyta nazwę inaczej). Co zniknęło po usunięciu HAR: identyfikator panelu lejka, ścieżki zaplecza, piksel Meta, host zasobów, serwer, certyfikat. Bez HAR połączenie z kampanią stoi na tym, czego nie ruszyliśmy: 97% tekstu artykułu (narracja 13 bitów), struktura DOM (`dom_hash`), osoby i twarz (`face_match` przeżył przycięcie i JPEG q=60), tytuł i zestaw parametrów adresu. Nie ma wtedy markera rozstrzygającego (do 58 bitów, `same_campaign` z dwóch niezależnych potwierdzeń i zgodnej narracji), a przy HAR z podmienioną domeną jest (87 do 93 bitów), bo identyfikatory panelu lejka przenoszą się razem z lejkiem. Wariant nask/3 dołączył do kampanii przez nask/3 i nask/2 (60 i 46 bitów), a do backup/p5 ma tylko `similar` (15 bitów): p5 jest przy operatorze B wyłącznie przez host zasobów z HAR, którego wariant nie ma, choć wariant jest w O-0002, w którym p5 już jest.

To słaby przeciwnik: zmieniliśmy 3 zdania i domenę, a szablon i resztę tekstu zostawiliśmy. Nie sprawdzaliśmy przepisania całego artykułu ani innego szablonu strony. Pułapka niżej pokazuje, co zostaje, gdy z oryginału zostaje tylko treść.

**Próba 2: pułapka.** Oryginalny zrzut (bajt w bajt) i cały widoczny tekst nask/1, ale strona bez skryptów, zasobów i identyfikatorów, bez HAR, pod domeną `.example`. Wynik: bez kampanii i bez operatora. Relacja `similar` z nask/1 (39 bitów: kreacja 14,5, narracja 13,7, osoby 10,6) i z pozostałymi pięcioma sprawami operatora A (18 do 25 bitów), ani jednej krawędzi `same_campaign` lub `same_operator`. 13 markerów, 9 wspólnych z oryginałem (kreacja, tytuł, nazwa strony, osoby, twarz, marka, temat). Ślady zaplecza (funnel_id, kit_path, piksel, host, domena) nie istnieją. To zachowanie z #267: `creative_phash` nie rozstrzyga, więc kopia zrzutu i tekstu daje pokrewieństwo treści, a nie wspólne źródło. Tej samej pary nie puszczaliśmy na modelu sprzed #267.

**Próba 3: zakwestionowanie mostu.** Skrypt sprawdził podgląd (`POST /api/premises/preview`) dla wszystkich 104 śladów występujących na co najmniej dwóch reklamach. Grupę rozdzielają dwa:

| Ślad | Krawędzi | Co się rozdziela |
|---|---|---|
| `asset_host` (`crimsonbase.pro`) | 1 (backup/p5 do nask/2, `same_operator` 33 bity, po wyłączeniu `similar` 24 bity, pewność 0,999) | operator O-0002 (nask/2, nask/3, backup/p5): backup/p5 wychodzi z grupy, kampania K-0002 zostaje (domena 18 bitów, parametr lejka 12, nazwa strony 8) |
| `google_ads` | 1 | kampania K-0003 i operator O-0003 (trzy strony sprawy 61): jedna strona wychodzi z obu grup |

Cykl dla `asset_host`: `POST /api/premises` odłączył backup/p5 od O-0002 (operator `null`, 2 reklamy zostały), `POST /api/premises/{id}/restore` przywrócił 3 reklamy w O-0002, stan grup identyczny jak przed zakwestionowaniem (sprawdzone odczytem operatora każdej z 3 reklam w trzech chwilach). Odpowiedź przywrócenia ma puste `regroup`, bo ten opis listuje tylko rozdzielenia, więc scalenie widać dopiero po odczycie reklam. Pozostałe 102 ślady nie są jedynym mostem żadnej grupy: grupy trzymają się na kilku niezależnych śladach. To zgadza się z laboratorium dowodów (nask/2 do backup/p5 spada do `similar` bez hosta `crimsonbase.pro`).

Czego nie sprawdziliśmy: ekranów interfejsu (tylko API), strumienia SSE (skrypt odpytuje `GET /api/analyses/{id}`), mocniejszych przebrań (przepisany cały tekst, inny szablon, inne zrzuty obrazów w `_files`), spraw spoza czterech wybranych, powtórzenia przebiegu. Warianty zostają w korpusie stosu, więc późniejsze widzą wcześniejsze (wyniki liczone względem oryginałów z paczek), a pułapka szła pierwsza, na korpusie bez wariantów.

### Wagi uczone (EM) zamiast eksperckich

Zadanie #207, 2026-11-21, `python manage.py estimate_weights` (tylko odczyt bazy, wynik w `data/models/wagi.json`, poza gitem). EM Fellegi-Sunter bez etykiet na parach kandydatów, tych samych, które ocenia `link_ad`. Start z wag eksperckich. Powtórzenie pomiaru: ta sama komenda, `--source capture --bootstrap 30 --seed 7`.

**Dane.** 28 reklam z materiałów spraw (`source=capture`), 151 par kandydatów, 150 ze zgodnością na jakimś markerze. Typów markerów 57, z czego 23 miało zgodność w co najmniej 5 parach i tylko te zostały uczone. Pozostałe 34 (m.in. `domain`, `tls_serial`, `google_ads`, `dom_hash`, `creative_phash`, `ad_naming`) zostają przy wartościach eksperckich, bo 0 do 4 par to za mało. Uczone są więc głównie markery o średniej i niskiej wadze oraz treść, a rzadkie markery rozstrzygające nie.

**Dwie klasy ukryte, nie jedna.** Pierwsza wersja miała jedną klasę "ta sama grupa" na wszystkie typy. EM dopasował ją do wspólnej opowieści (16 par zgodnej treści), a pary operatora A, który ma różne kampanie i różną treść, uznał w większości za niepasujące: `funnel_id` spadł z 18 do 5 bitów, a `kit_path` z 8 do 3,3. To skutek założenia niezależności typów: operator z inną treścią płaci karę za niezgodność na treści. Dlatego szacujemy osobno klasę zaplecza (infrastruktura, tracking, szablon, zachowanie: 31,4 oczekiwanej pary pasującej, 18 iteracji) i klasę opowieści (narracja, kreacja, osoby: 18,0 pary, 11 iteracji). Obie zbiegły się.

**Porównanie na tych samych 151 parach (expert `fs-5` i learned `fs-6`).**

| | expert | learned |
|---|---|---|
| pary z relacją | 67 | 63 |
| wspólne źródło (`same_campaign`, `same_operator`) | 33 | 33 |
| grupy wspólnego źródła | 3 | 3 |

- Relacja zmienia się w 4 parach, zawsze `similar` na brak relacji: nask/2 z nask/48, nask/3 z nask/48, nask/2 z backup/p4 i nask/3 z backup/p4. Wszystkie 4 miały pewność poniżej 0,02 i stały na samych motywach (podszycie pod markę, tematyka, ślad językowy) plus podobieństwie znaczenia treści.
- Utrata wspólnego źródła: 0. Nowe wspólne źródło: 0, czyli bez fałszywych połączeń. Żadna grupa się nie rozpadła i żadne dwie się nie scaliły.
- **Rdzeń operatora A zostaje:** 28 z 28 par spiętych `funnel_id` lub `meta_pixel` zachowuje relację. Oba typy zostają przy 18 bitach, bo w próbie żadna para niepasująca ich nie dzieli (u bliskie 0).
- Pary graniczne (pewność od 0,5 do 0,99 w którymkolwiek zestawie albo zmiana relacji): 17. Najmocniej tracą pary tylko `similar`: nask/48 z backup/p11 oraz p11 z p3 i p4 (silnik lejka bez śladu operatora) z pewności 0,986 na 0,122, nask/48 z backup/p4 z 0,999 na 0,693 i nask/3 z backup/p5 z 0,834 na 0,544. Relacja `similar` zostaje, bo opiera się na regułach (ścieżki zaplecza, zgodna treść), nie na progu pewności.

**Typy z największą zmianą wagi (bity, ekspercka do uczonej).** `kit_path` 8,0 do 3,95, `page_name` 8,0 do 4,93 (6 par), `asset_host` 9,0 do 7,36, `url_param_keys` 4,0 do 2,80, `lang_trace` 1,5 do 0,50, `topic` 1,5 do 0,59, `url_path_tpl` 4,0 do 3,39. Kierunek zgadza się z przeglądem krawędzi: ślady silnika lejka (`kit_path`, `url_param_keys`) są słabsze, niż zakładaliśmy, bo zgadzają się też na parach niepasujących (u 0,06 i 0,14).

**Stabilność.** Bootstrap po reklamach (30 prób) daje odchylenie wagi powyżej 3 bitów dla 1 z 23 uczonych typów: `funnel_id` (5,8 bita, m 0,89). Ocena komendy: stabilne. To nie dowód, że wagi są dobre: 28 reklam i 151 par to mało, m typów rzadkich (`page_name`, `url_path_tpl`: po 6 par) opiera się na garści par, a operatorów w próbie jest 3.

**Ten sam EM na całym korpusie (327 reklam, 7474 pary, w tym ok. 300 reklam Microsoft; 10 prób bootstrapu).** Kontrola przenoszenia, nie wynik do użycia: 68 zmian relacji, wspólne źródło 3024 do 2987 (utrata 37, nowe 0), rdzeń operatora A 89 z 101 par, grup wspólnego źródła 34 do 36 i 5 rozpadniętych. `funnel_id` spada do 0,7 bita, `kit_path` do 0, `advertiser_id` z 18 do 7,9. Powód: reklamy Microsoft tworzą ok. 3000 par o tym samym `advertiser_id` i EM dopasowuje klasy do tej struktury, a nie do operatorów z materiałów spraw. Metoda jest wrażliwa na skład korpusu.

**Decyzja.** Domyślnie zostają wagi eksperckie (`MODEL_WEIGHTS=expert`, `fs-5`). Uczone dają to samo grupowanie na danych organizatora i nie łączą niczego nowego, ale na 28 reklamach nie ma dowodu, że są lepsze, a na korpusie z Microsoftem łamią rdzeń operatora A. Włączenie (`MODEL_WEIGHTS=learned`) ma sens po zebraniu kilkuset decyzji analityków. **Kalibracja: brak, 0 decyzji** w bazie, więc skalibrowanej pewności nie ma. Po zebraniu decyzji (min. 20, po 5 z każdej klasy) ta sama komenda dopasuje regresję logistyczną na bitach i rodzinach i zapisze współczynniki w tym samym pliku.

### Ślad językowy

W sprawach nask/14, nask/47 i backup/p9 nazwy zestawów reklam w parametrach adresu zawierają litery cyrylicy wmieszane w łaciński tekst (np. `сс`, `С4`). To słaby marker (`lang_trace`), ale spójny z tym, co o operatorach takich kampanii piszą raporty branżowe.

## Czego silnik jeszcze nie łapie na tych danych

- **Wizerunki.** Twarze na zrzutach reklam porównujemy z małą bazą referencyjną (YuNet i SFace, szczegóły w [licencje.md](licencje.md)). Na zrzutach z obu paczek wykryto twarze w 21 plikach. Baza ma 10 osób wymienianych w tekstach tych reklam (Rafał Brzoska, Mateusz Morawiecki, Adam Glapiński, Krzysztof Stanowski, Tomasz Sekielski, Donald Tusk, Radosław Sikorski, Andrzej Domański, Anna Lewandowska, Karol Nawrocki). Zdjęcie Karola Nawrockiego z Wikidata nie ma wolnej licencji, więc builder wziął portret z jego kategorii na Commons (CC BY 4.0), potwierdzony zgodnością z drugim, niezależnym zdjęciem. Moniki Olejnik nie ma: jej zdjęcie z Wikidata (P18, GFDL 1.2, licencja wolna) Commons wydaje z kodem 429 dla zapytań bez kontaktu osobowego w User-Agencie, sprawdzone 21.11 wieczorem i ponownie o 22:40. Kontaktu nie dopisujemy, więc twarz dochodzi poleceniem `build_face_refs --names "Monika Olejnik"`, gdy limit puści. System rozpoznał twarz w 8 zrzutach: Brzoska w nask/1, Morawiecki w nask/48, backup/p1, p2, p7 i p15, Glapiński w nask/3, Sikorski w backup/p11, z podobieństwem od 0,43 do 0,74 przy progu 0,363. Nazwiska z tych trafień padają w tekstach reklam z paczek, więc oba kanały się potwierdzają. Twarz jest motywem (`face_match`), jak wzmianka w tekście: dodaje bity, ale nie łączy różnych operatorów. Twarze sprawdzamy też na klatkach nagrań. Mowę z nagrań zamieniamy na tekst (Whisper small, wyniki niżej), barwy głosu i klonów głosu nie porównujemy.
- **Sprawa 48 i strona 1 sprawy 61** mają ten sam tytuł, lead i autora, a relacja wychodzi `similar`. Przegląd z 2026-11-21 pokazał, że to nie jest ten sam tekst z doklejoną sekcją: treść artykułu jest przepisana (w jednym bohaterem jest były premier, w drugim były minister finansów). Podobieństwo treści: Jaccard 0,31, zawieranie 0,50. Z 3464 słów sprawy 48 we wspólnych fragmentach od 8 słów wzwyż jest 708, z czego 589 to tekst formularza lejka, czyli ślad silnika, a nie artykułu. Miara treści odporna na doklejoną sekcję (model `fs-5`) tej pary więc nie zmienia i nie powinna: wspólny jest szablon artykułu, a nie tekst. Sprawa 48 i strona 2 sprawy 61 mają ten sam silnik lejka.
- **Zrzut reklamy dołączany do każdej strony sprawy** łączy strony jednej sprawy dowodem `creative_phash`. W sprawie 61 krawędź między stroną 1 a stroną 3 stoi tylko na tym zrzucie i nazwie reklamodawcy z OCR. Wynik zgadza się z resztą sprawy (ta sama domena, cloaking), ale sam dowód wynika z tego, jak organizator ułożył pliki.
- **Wideo.** Nagrania ekranu i reklamy wideo rejestrujemy (skrót pliku) i odczytujemy z nich długość, rozdzielczość i klatkę poglądową, a z 8 klatek bierzemy hasze, tekst z OCR i twarze. Sprawa 5 (sama reklama wideo, wcześniej bez żadnych cech z treści) dostaje tekst reklamy z podszyciem pod lekarza i obietnicą dopłaty z "Programu Państwowego". Sprawa 47 dostaje tekst karty reklamy i nazwę reklamodawcy przy "Sponsorowane" jako marker. Twarzy z bazy na tych klatkach nie ma. Mowa z nagrań (Whisper `small`, CPU, pierwsze 120 s): sprawa 5 dała ok. 1750 znaków czytelnego polskiego tekstu reklamy (o bólu pleców, z drobnymi pomyłkami typu "Trzepukliny" zamiast "przepukliny") w 12,0 s, sprawa 14 ok. 1050 znaków w 11,8 s, czyli około 10 razy szybciej niż czas nagrania. Sprawa 47 ma ścieżkę dźwiękową, ale to cisza cyfrowa (średnia głośność -91 dB), więc transkryptu nie ma. Wzmianki o osobach z bazy (30 osób) w tych transkryptach nie padły, więc `person_mention` z mowy na danych organizatora nie wykryliśmy, a działanie ścieżki sprawdza test z atrapą. Model `base` jest 2,5 razy szybszy (ok. 5 s), ale przekręca słowa wyraźnie częściej. Na stosie głównym `transcribe_videos --reanalyze` przeliczył sprawy 5 i 14 (17,5 s i 15,9 s w kontenerze), liczby kampanii i operatorów się nie zmieniły (33 i 34). Sprawa 5: reklama wideo 198 s, a jej metadane z Biblioteki Reklam nie podają długości oryginału. Sprawa 47: nagranie ekranu 166 s. Sprawa 14: nagranie ekranu 249 s i 339 MB, ponad limit magazynu, więc jest opisane, ale nie da się go odtworzyć w interfejsie.
- **Sprawy bez HAR** (p6, p12, p14) mają tylko ślady z HTML, więc odcisk zaplecza jest dla nich niedostępny.

## Uwagi do pracy z paczkami

- Adres w sprawie 36 zawiera token dostępu do API Mety. Zapisujemy wyłącznie jego skrót.
- Plik HAR z `page-capture` jest oczyszczony przez organizatora, pozostałe pliki są surowe.
- Sprawy p1 i p2 z drugiej paczki to duplikat tego samego przechwycenia.
- Do demo warto zostawić jedną sprawę poza importem i wrzucić ją na żywo przez Discovery, żeby pokazać dołączenie do znanego operatora.
