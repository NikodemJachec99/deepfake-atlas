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

28 stron z 25 spraw. Silnik nie dostał żadnej informacji, które sprawy do siebie pasują. Po ponownym imporcie 2026-11-21: 20 krawędzi `same_campaign`, 13 `same_operator`, 30 `similar`; 3 operatorów, 4 kampanie, 14 stron bez operatora.

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

### Cloaking w sprawie 61

Domena `glowpixel.org` zwraca dwie różne strony pod tym samym adresem: "portal analiz" dla moderacji (strona 3) i ofertę dla ofiary (strona 2). Nazwa reklamodawcy na zrzucie reklamy to `Glowpixel`, czyli nazwa domeny białej strony. OCR zrzutu i nazwa domeny dają ten sam marker `page_name`.

### Lista Ostrzeżeń CERT Polska

Część domen z obu paczek jest na liście (`civicdaybook.live`, `healthlinkq.pro`, `lundevra.live`, `smartcoved.pro`, `spiritualityinsports.org`). Pozostałe domeny tego samego operatora na liście nie figurują, mimo że stoją na tym samym zapleczu. To praktyczny pożytek z łączenia: jedna znana domena wskazuje resztę.

### Bez powiązań

nask/5 (sama reklama wideo), nask/10, nask/14, nask/36, nask/47, backup/p6, p8, p9, p10, p12, p13, p14. Każda stoi na innym zapleczu. Do tego nask/48 i backup/p11 opisane wyżej. Sprawa p8 ma relację `similar` z p11: ten sam tytuł strony i te same obrazy, ale inne zaplecze, więc silnik nie przypisał jej do operatora.

### Ślad językowy

W sprawach nask/14, nask/47 i backup/p9 nazwy zestawów reklam w parametrach adresu zawierają litery cyrylicy wmieszane w łaciński tekst (np. `сс`, `С4`). To słaby marker (`lang_trace`), ale spójny z tym, co o operatorach takich kampanii piszą raporty branżowe.

## Czego silnik jeszcze nie łapie na tych danych

- **Wizerunki.** Zrzuty reklam zawierają twarze i kadry wideo. Porównujemy obrazy hashem percepcyjnym (ten sam obraz po przeróbkach), ale nie rozpoznajemy twarzy ani głosu, więc spraw o tej samej osobie w różnych kadrach nie łączymy po obrazie.
- **Sprawa 48 i strona 1 sprawy 61** mają ten sam tytuł, lead i autora, a relacja wychodzi `similar`. Przegląd z 2026-11-21 pokazał, że to nie jest ten sam tekst z doklejoną sekcją: treść artykułu jest przepisana (w jednym bohaterem jest były premier, w drugim były minister finansów). Podobieństwo treści: Jaccard 0,31, zawieranie 0,50. Z 3464 słów sprawy 48 we wspólnych fragmentach od 8 słów wzwyż jest 708, z czego 589 to tekst formularza lejka, czyli ślad silnika, a nie artykułu. Miara treści odporna na doklejoną sekcję (model `fs-5`) tej pary więc nie zmienia i nie powinna: wspólny jest szablon artykułu, a nie tekst. Sprawa 48 i strona 2 sprawy 61 mają ten sam silnik lejka.
- **Zrzut reklamy dołączany do każdej strony sprawy** łączy strony jednej sprawy dowodem `creative_phash`. W sprawie 61 krawędź między stroną 1 a stroną 3 stoi tylko na tym zrzucie i nazwie reklamodawcy z OCR. Wynik zgadza się z resztą sprawy (ta sama domena, cloaking), ale sam dowód wynika z tego, jak organizator ułożył pliki.
- **Wideo.** Nagrania ekranu i reklamy wideo rejestrujemy (skrót pliku), ale ich nie analizujemy.
- **Sprawy bez HAR** (p6, p12, p14) mają tylko ślady z HTML, więc odcisk zaplecza jest dla nich niedostępny.

## Uwagi do pracy z paczkami

- Adres w sprawie 36 zawiera token dostępu do API Mety. Zapisujemy wyłącznie jego skrót.
- Plik HAR z `page-capture` jest oczyszczony przez organizatora, pozostałe pliki są surowe.
- Sprawy p1 i p2 z drugiej paczki to duplikat tego samego przechwycenia.
- Do demo warto zostawić jedną sprawę poza importem i wrzucić ją na żywo przez Discovery, żeby pokazać dołączenie do znanego operatora.
