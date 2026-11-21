# Metodyka: jak pozyskujemy cechy, liczymy podobieństwo i grupujemy materiały

Dokument opisuje to, co działa w kodzie. Miejsca w kodzie są podane przy każdym kroku.

## 1. Założenie

Nie oceniamy, czy pojedyncza reklama jest oszustwem. Odpowiadamy na pytanie: **które materiały pochodzą z tego samego źródła i skąd to wiemy**. Każde połączenie ma listę dowodów z wkładem liczonym w bitach, więc da się je sprawdzić i podważyć.

## 2. Wejście

| Materiał | Jak trafia do systemu |
|---|---|
| adres URL reklamy lub strony | `POST /api/analyses` |
| tekst, nazwa produktu | `POST /api/analyses` |
| zrzut ekranu reklamy | `POST /api/analyses/upload` |
| log komunikacji (HAR) | `POST /api/analyses/upload` |
| zapisana strona, archiwum sprawy (ZIP), zrzut z `page-capture`, archiwum NASK | `POST /api/analyses/upload`, `manage.py import_bundle` |
| plik wideo z metadanymi yt-dlp | `POST /api/analyses/upload` (plik, numer reklamy, 8 klatek: hasze, tekst z OCR, twarze, oraz transkrypt mowy) |
| reklamy z bibliotek | konektory w `collectors/`, uruchamiane ręcznie albo z harmonogramu |

Jedna strona docelowa to jedna jednostka analizy. Zapisana strona i HAR tej samej domeny z jednego katalogu łączymy w jedną jednostkę. Zrzuty reklamy z katalogu sprawy dołączamy do każdej strony tej sprawy (`collectors/bundle.py`).

## 3. Potok analizy

Sześć etapów (`workflows/pipeline.py`). Każdy zapisuje wynik do bazy i zdarzenia postępu, więc orkiestrator (Temporal) może ponowić dowolny z nich, a interfejs pokazuje przebieg na żywo.

1. **Przyjęcie.** Utworzenie rekordu reklamy.
2. **Strona.** Dla materiału z przechwycenia bierzemy HTML i HAR z plików i niczego nie pobieramy z sieci. Dla adresu na żywo pobieramy stronę dwa razy, jako automat i jako ofiara z telefonu po kliknięciu w reklamę, i zapisujemy łańcuch przekierowań.
3. **Ekstrakcja cech.** Sekcja 4.
4. **Wzbogacanie.** Dane rejestrowe domeny (RDAP), obecność na Liście Ostrzeżeń CERT Polska, certyfikaty domeny z dzienników Certificate Transparency (crt.sh). Dla strony badanej na żywo także DNS, ASN, certyfikat i favicon.

   Z crt.sh bierzemy do 50 najnowszych certyfikatów domeny, także dawnych. Numer seryjny każdego trafia do markera `tls_serial`, tego samego co numer z `dns_ssl.json` w paczkach. Certyfikat wystawiony na kilka domen łączy je jako ślad jednego konta, a pozostałe domeny z pola SAN analiza wypisuje jako tropy. Certyfikat CDN na kilkanaście niezwiązanych domen (ponad 10 domen rejestrowych albo host `cloudflaressl.com`) pomijamy. Odpowiedź trzymamy w bazie przez 7 dni (pustej nie, bo crt.sh pod obciążeniem potrafi zwrócić pustą listę dla domeny z certyfikatami), zapytania idą po kolei co 3 sekundy z limitem 25 sekund. Brak odpowiedzi crt.sh pomija ten krok i analiza idzie dalej, a przez kolejne 10 minut crt.sh nie jest pytany wcale, żeby import wielu stron nie czekał na każdy limit czasu. Domeny, które zostały bez odpowiedzi, dociąga później `python manage.py fill_certs`: dopina certyfikaty do reklam tych domen i przelicza ich krawędzie i grupy bez ponownego importu.
5. **Łączenie.** Sekcje 5 i 6.
6. **Grupowanie.** Sekcja 7.

Brak danych nie zatrzymuje analizy. Strona niedostępna, sprawa bez HAR albo sam zrzut ekranu dają mniej cech, a nie błąd. Reklamy bez strony docelowej (np. formularze w Facebooku) łączymy po kreacji, narracji i osobach.

## 4. Cechy

Każdą cechę zapisujemy jako marker: typ i znormalizowana wartość. Markery dzielą się na twarde (porównywane dokładnie) i miękkie (porównywane przez podobieństwo). Rejestr typów z parametrami: `evidence/kinds.py`.

### Siedem rodzin

| Rodzina | Markery | Skąd |
|---|---|---|
| Infrastruktura | domena rejestrowa, domeny w łańcuchu przekierowań, IP, ASN, serwery nazw, certyfikat (skrót albo numer seryjny), hash favicony, rejestrator, dzień rejestracji, szablon ścieżki URL, zestaw nazw parametrów, sieć CDN, sygnatura serwera | URL, HAR, RDAP, DNS, `dns_ssl.json` |
| Tracking i lejek | Google Analytics, GTM, Google Ads, Meta Pixel, Yandex Metrica, TikTok Pixel, skrót tokenu Conversions API, identyfikatory z żądań POST, klucze afiliacyjne z parametrów, hosty zasobów i trackerów, endpoint formularza, hosty skryptów | HTML, treść skryptów i żądań w HAR, URL |
| Szablon strony | ścieżki zaplecza strony, hash struktury DOM, podobieństwo struktury DOM, hash strony pokazywanej automatom | HAR, HTML |
| Kreacja | hash percepcyjny zrzutu reklamy, zbiór haszy percepcyjnych obrazów strony, skrót pliku | zrzuty, obrazy z HAR i z katalogu `_files` |
| Narracja | tytuł strony, podobieństwo treści strony, podobieństwo tekstu reklamy, telefon, e-mail, Telegram, WhatsApp, adresy krypto, IBAN, tematyka | HTML, OCR zrzutu |
| Osoby i marki | wzmianka o osobie z bazy referencyjnej, podszycie pod markę, nazwa reklamodawcy lub strony, identyfikator reklamy Meta, strona reklamodawcy, płatnik | tekst, OCR, URL, biblioteki reklam |
| Zachowanie | nazewnictwo reklam i zestawów reklam, ślad językowy operatora | parametry URL, źródło strony |

### Jak powstają cechy mniej oczywiste

- **Ścieżki zaplecza** (`kit_path`, `extractors/har.py`). Z HAR bierzemy żądania do własnej domeny strony, zamieniamy liczby i identyfikatory w ścieżkach na `{n}` i `{id}`, odrzucamy ścieżki, które ma każda strona. Zostaje odcisk silnika, który stronę obsługuje, np. `POST /api/v1/trigger/field/{id}/`. Ten sam silnik na innej domenie daje te same ścieżki.
- **Identyfikatory lejka** (`funnel_id`). Z treści żądań POST do własnej domeny wyciągamy pola z UUID. Identyfikator wizyty odrzucamy, bo jest jednorazowy. Zostają identyfikatory obiektów w panelu operatora.
- **Hosty zasobów** (`asset_host`). Hosty spoza domeny strony, z pominięciem publicznych CDN-ów. Na platformach wielu najemców (b-cdn.net, netlify.app, on.aws) bierzemy pełną nazwę hosta, bo dopiero ona wskazuje właściciela.
- **Parametry URL** (`extractors/url.py`). Zestaw nazw parametrów jest markerem tylko wtedy, gdy zawiera coś spoza standardowych `utm_*`. Z wartości wyciągamy piksele (`pxl`, `fbpx`), klucze afiliacyjne (`key`, `acc`), identyfikatory reklam Meta i nazwy zestawów reklam.
- **Szablon strony.** Ciąg znaczników HTML z klasami CSS. Jego skrót wykrywa identyczny szablon, a MinHash z trójek kolejnych znaczników mierzy podobieństwo szablonów po drobnych zmianach.
- **Znaczenie treści** (`extractors/embedding.py`). Wielojęzyczny model zdaniowy (paraphrase-multilingual-MiniLM-L12-v2, lokalnie) liczy wektor z początku treści strony, gdzie stoi artykuł (do 8 fragmentów po 128 tokenów), a bez strony z tekstu reklamy. Kandydatów daje indeks HNSW w Postgresie. Marker miękki `text_embedding` łapie ten sam artykuł przepisany innymi słowami: w sprawie 48 i na stronie 1 sprawy 61 podobieństwo znaczenia wynosi 0,98 przy MinHash 0,39. Różne artykuły z tego samego gatunku oszustw mają 0,51 do 0,68, więc wagę daje dopiero podobieństwo powyżej 0,75 (pełną od 0,92). Znaczenie to opowieść, nie zaplecze: samo nigdy nie daje wspólnego źródła.
- **Podobne ujęcie** (`extractors/image_embedding.py`). Model CLIP ViT-B/32 (część obrazowa, ONNX int8, lokalnie na CPU) liczy wektor 512 liczb jednego obrazu reklamy: pierwszego zrzutu, a bez niego klatki poglądowej nagrania, a bez niej zrzutu strony z crawlera. Obraz idzie do modelu w całości, ściśnięty do kwadratu, bo środkowy wycinek gubiłby nazwę reklamodawcy i przycisk. Kandydatów daje indeks HNSW (`Ad.image_embedding`), marker miękki `image_embedding` w rodzinie Kreacja jest opowieścią, nie zaplecze. Wektor jednego obrazu, nie średnia: średnia kilku zrzutów interfejsu Facebooka dawała 0,92 między niezwiązanymi sprawami. Wektory brakujące uzupełnia `manage.py embed_images [--all] [--link]`.
  Progi z danych organizatora (39 obrazów z 25 reklam, 741 par, odczyt ze stosu): wersje jednego ujęcia (kawalkada "WTOREK, 20:10, WARSZAWA" w trzech reklamach z różnych spraw, ten sam prezenter w dwóch kadrach, ta sama strona zastępcza w dwóch rozmiarach) mają 0,85 do 0,95. Niezwiązane zrzuty (głównie ten sam interfejs Facebooka) mają medianę 0,56, 95. percentyl 0,75, 99. percentyl 0,79, a najwyższa para nieujęciowa 0,80. Wagę daje dopiero podobieństwo powyżej 0,82 (pełną od 0,95, cap 5 bitów). Próbka jest mała: progi są ostrożne po stronie precyzji i trzeba je sprawdzić na większym korpusie. Samo ujęcie daje najwyżej relację "podobne", nigdy wspólne źródło.
  Logo zero-shot (opis "logo MARKA" tym samym modelem, marki z `html.BRANDS`) sprawdziliśmy na tych samych 39 obrazach i **nie wdrożyliśmy**: podobieństwo do najlepszej marki 0,24 do 0,30, a przewaga nad drugą marką najwyżej 0,027 (mediana 0,006). Obraz ze znakiem stacji w rogu (Polsat News) dostał trafną markę z przewagą 0,012, czyli tyle co obrazy bez logo, którym model przypisywał marki losowo (ten sam wynik "Polsat News" dostały kadry z kawalkady i z innych reklam). Logo jest małe względem całego zrzutu, więc potrzebny byłby wycinek wokół logo albo model z detekcją, nie sam CLIP na całym obrazie. Markery `brand_impersonated` zostają z tytułu i treści strony.
- **Treść.** Tekst widoczny na stronie bez skryptów, stylów i list wyboru (`select`, `option`, `datalist`, elementy z rolą `listbox` i `option`). Lista krajów w polu numeru telefonu to nie treść, a w formularzach lejka zajmowała do 7 tys. znaków. MinHash z pięcioznakowych wycinków znormalizowanego tekstu: małe litery, cyfry zamienione na zera, bez interpunkcji. Podmiana kwoty albo daty nie zmienia wyniku. Gdy krótszy tekst prawie cały (od 85%) siedzi w dłuższym, podobieństwem jest to zawieranie, a nie Jaccard. Zawieranie wylicza się z Jaccarda i liczności obu zbiorów, które sygnatura niesie na końcu. Dzięki temu zapis strony z doklejonymi komentarzami albo stopką dalej jest tym samym artykułem. Zawierania nie liczymy dla krótkich tekstów (poniżej 300 wycinków), gdy dłuższy tekst jest ponad trzy razy większy (baner zawarty w każdej stronie robiłby z różnych stron ten sam tekst) i gdy rozmiary różnią się o mniej niż 10% (wtedy pełne zawieranie i tak daje wysoki Jaccard, a częściowe tylko by go zawyżało).
- **Obrazy** (`extractors/images.py`). Hash różnicowy (dHash, 64 bity) odporny na zmianę rozmiaru i kompresję. Dwa obrazy są tym samym obrazem, gdy hasze różnią się o najwyżej 6 bitów. Stronę opisuje zbiór haszy jej obrazów, pomijamy obrazy mniejsze niż 160 pikseli.
- **OCR** (`extractors/ocr.py`). Ze zrzutu reklamy wyciągamy nazwę reklamodawcy (wiersz przy "Sponsorowane"), tekst reklamy i numer z Biblioteki Reklam Mety.
- **Osoby** (`people/matching.py`). Baza referencyjna 30 osób publicznych. Dopasowanie po imieniu i nazwisku z tolerancją na odmianę: "Jana Kowalskiego" to Jan Kowalski.
- **Twarze** (`people/faces.py`). Na zrzucie reklamy YuNet wykrywa twarze (pomijamy mniejsze niż 40 pikseli), SFace liczy wektor 128 liczb, porównujemy podobieństwem kosinusowym z wektorami osób z bazy referencyjnej (`people/face_refs.json`, zdjęcia z Wikidata i Wikimedia Commons na wolnej licencji). Od 0,363 (próg autorów SFace) powstaje marker `face_match` z nazwiskiem i wynikiem. Wektorów twarzy spoza bazy nie zapisujemy. Twarz jest motywem, tak jak wzmianka: różni operatorzy używają tych samych twarzy.
- **Podszycie pod markę.** Nazwa redakcji albo marki w tytule lub na początku strony, przy domenie, która do tej marki nie należy.
- **Słowa kluczowe i tematyka** (`extractors/keywords.py`). Najczęstsze znaczące wyrazy oraz regułowa klasyfikacja motywu: inwestycje, zdrowie, hazard, sensacja, sklep.
- **Cloaking.** Gdy automat dostaje inną stronę niż ofiara, struktura tej "białej strony" jest osobnym markerem.

Tokeny dostępu znalezione w adresach zapisujemy wyłącznie jako skrót SHA-256.

## 5. Podobieństwo pary

Model Fellegi-Sunter z ważeniem rzadkością (`similarity/fusion.py`). Dla każdego wspólnego markera liczymy, o ile bardziej prawdopodobne jest, że dwie reklamy go dzielą, bo mają wspólne źródło, niż przez przypadek.

**Marker twardy.** Waga w bitach:

```
waga = log2( m / f ),  ograniczona do przedziału [0, cap]
f = (źródła_z_tą_wartością - 2 + α·f0) / (wszystkie_źródła - 2 + α)
```

- `m`: jak często dwie reklamy tej samej kampanii zgadzają się na tym typie markera,
- `f`: jak często wartość występuje w korpusie, wygładzone częstością bazową typu `f0` z siłą `α = 1000`,
- `cap`: maksymalne zaufanie do jednego śladu.

Skutek: adres z puli Cloudflare jest wart ułamek bita, a identyfikator strony w panelu lejka 18 bitów. W małym korpusie częstość z danych nic nie mówi, więc działa częstość bazowa typu. W dużym przejmują ją dane.

**Rzadkość liczymy po niezależnych źródłach, nie po reklamach.** Źródłem jest kampania albo reklama bez kampanii. Inaczej identyfikator dużej kampanii wyglądałby na pospolity i kolejne jej odsłony przestałyby się do niej przyklejać (`similarity/service.py`).

**Marker miękki.** Waga rośnie liniowo od zera przy progu `lo` do `cap` przy progu `hi`. Dla treści strony progi to 0,5 i 0,9.

**Korelacja w rodzinie.** Markery jednej rodziny zwykle idą w parze (ta sama domena to ten sam adres i certyfikat). W obrębie rodziny pełną wagę dostaje najsilniejszy marker, drugi połowę, trzeci ćwierć.

**Pewność.** Suma bitów po rodzinach plus szansa wstępna 1 do 10 000, przeliczone na prawdopodobieństwo.

### Wagi uczone

`manage.py estimate_weights` (`similarity/learning.py`) szacuje `m` i `u` z par kandydatów algorytmem EM bez etykiet. Para ma wektor zgodności: dla każdego typu markera 1, gdy dzieli wartość (marker miękki: podobieństwo co najmniej `hi`). Klasa ukryta to "ta sama grupa". Szacujemy `m` (zgodność przy tej samej grupie), `u` (zgodność przy różnych) i udział par pasujących, z inicjalizacją z wag eksperckich, wygładzaniem ku wartości eksperckiej (żeby `u` nie było 0), limitem 500 iteracji i progiem zbieżności 1e-7. Wynik to JSON: `m`, `u`, bity `log2(m/u)` obcięte do `cap`, liczba par ze zgodnością i metadane (liczba par, iteracje, data, wersja modelu).

- **Dwie klasy, nie jedna.** Zaplecze (infrastruktura, tracking, szablon, zachowanie) i opowieść (narracja, kreacja, osoby) uczymy osobno. Jedna klasa mylnie uznaje operatora z różnymi kampaniami za niepasującego, bo jego strony różnią się treścią.
- **`u` względem wszystkich par.** Po typach kandydackich szukamy kandydatów, więc wśród kandydatów zgodność jest zawyżona. Dla nich `u` liczymy względem N(N-1)/2 par. Dla pozostałych jest warunkowe (pole `u_basis`).
- **Typ z mniej niż 5 parami zgodności** zostaje przy wadze eksperckiej (`source: expert`).
- **Przełącznik.** `MODEL_WEIGHTS=expert|learned` (domyślnie `expert`, wersja `fs-5`) i `MODEL_WEIGHTS_PATH` (domyślnie `data/models/wagi.json`). Przy `learned` wersja to `fs-6`: typy twarde liczą `log2(m/f)` z uczonym `m` i `f0=u`, nadal z rzadkością po źródłach, typy miękkie dostają uczony limit zamiast `cap`. Rodziny, rabat w rodzinie, grupy niezależności, reguły relacji i limit zostają. Brak pliku przy `learned` to błąd `WeightsError` z poleceniem, co uruchomić, a nie ciche wrócenie do wag eksperckich, bo wersja `fs-6` na krawędzi musi znaczyć to, co znaczy.
- **Rozrzut.** Bootstrap po reklamach (nie po parach, bo pary jednej reklamy są zależne) daje odchylenie wagi każdego typu. Raport oznacza zestaw jako niestabilny, gdy ponad 25% typów ma odchylenie powyżej 3 bitów.
- **Kalibracja.** Gdy w bazie jest co najmniej 20 decyzji analityka (potwierdzone i odrzucone, po 5 z klasy), regresja logistyczna z regularyzacją L2 na bitach i bitach rodzin (metoda Newtona, bez bibliotek) daje skalibrowaną pewność, a współczynniki trafiają do tego samego JSON. Bez decyzji raport mówi "brak kalibracji: 0 decyzji".
- **`GET /api/weights`** zwraca wagę ekspercką i uczoną każdego typu.

Wynik na danych organizatora i ocena stabilności: [dane-organizatora.md](dane-organizatora.md). Krótko: grupowanie takie samo, rdzeń operatora A zostaje, ale 28 reklam to za mało, żeby zmienić domyślne wagi.

## 6. Od pewności do relacji

Sama wysoka suma nie wystarcza. Reguły:

| Relacja | Warunek |
|---|---|
| wspólne źródło | pewność co najmniej 0,9 **oraz** rzadki marker rozstrzygający albo dwa niezależne silne potwierdzenia, z których co najmniej jedno dotyczy zaplecza |
| `same_campaign` | wspólne źródło i ta sama opowieść: zgodna treść, obrazy albo kontakt |
| `same_operator` | wspólne źródło, inna opowieść |
| `similar` | brak dowodu wspólnego źródła, ale zgodna treść lub obrazy, kilka zgodnych motywów naraz (osoba, marka, tematyka) albo te same ścieżki zaplecza bez śladu operatora |
| duplikat | `same_campaign` oraz treść i struktura zgodne w co najmniej 97% |

Dlaczego tak:

- **Treść i obrazy da się skopiować.** Dwie strony z tym samym artykułem na różnych zapleczach to `similar`, nie wspólne źródło.
- **Wspólny motyw to nie wspólna opowieść.** Różni operatorzy używają tych samych nazwisk i udają te same redakcje, więc osoba, marka i tematyka nie robią z operatora kampanii.
- **Silnik lejka to program, nie operator.** Ścieżki zaplecza, szablon ścieżki i zestaw parametrów ustawia ten sam silnik, więc przy liczeniu niezależnych potwierdzeń są jednym, choć należą do dwóch rodzin. Silnik mógł kupić każdy. Operatora wskazuje dopiero ślad jego konta albo infrastruktury: identyfikator w panelu, piksel, konto reklamowe, własny host zasobów, adres, certyfikat.
- **Motyw nie potwierdza źródła.** Wzmianka o osobie, podszycie pod markę i tematyka dodają bity, ale nie liczą się jako niezależne potwierdzenie, nawet kilka naraz.
- **Huby.** Marker obecny w ponad 1% źródeł (minimum 100) nie służy do szukania kandydatów, a jego waga i tak jest bliska zera.

## 7. Grupowanie

- **Kampania:** składowa spójna grafu po krawędziach `same_campaign`.
- **Operator:** składowa spójna po krawędziach `same_campaign` i `same_operator`. Operator ma zwykle kilka kampanii.
- Krawędź odrzucona przez analityka niczego nie spina.

Zwykłe składowe spójne wystarczają, bo każda krawędź przeszła regułę z sekcji 6. Nie ma tu łączenia po samym progu podobieństwa, więc nie ma efektu łańcucha.

## 8. Nowy materiał

Nowa reklama nie jest porównywana z całym korpusem. Kandydatów znajdujemy indeksem po markerach twardych i po pasmach LSH markerów miękkich, najwyżej 500. Dla każdego liczymy parę i zapisujemy krawędź z dowodami. Wynik:

| Ocena | Znaczenie |
|---|---|
| `duplicate` | ten materiał już jest w korpusie |
| `known_campaign` | nowa odsłona znanej kampanii |
| `known_operator` | nowa kampania znanego operatora |
| `similar_only` | podobna koncepcja, brak dowodu wspólnego źródła |
| `new_pattern` | brak powiązań, potencjalnie nowa kampania |

Gdy reklama dołącza do kampanii albo operatora, które były w korpusie wcześniej, etap `cluster` zapisuje alert (`Alert`, `similarity/alerts.py`, `GET /api/alerts`) z trzema najmocniejszymi dowodami.

## 9. Interpretowalność

Każda krawędź ma w bazie listę dowodów (`EdgeEvidence`): rodzina, typ, wartości po obu stronach, liczba źródeł z tą wartością, wkład w bitach, znacznik rozstrzygania i odnośniki do plików, z których cecha pochodzi. Krawędź bez dowodów nie powstaje. Decyzja analityka (potwierdź, odrzuć, niepewne) zapisuje się w dzienniku audytu.

### Pakiet dowodowy i łańcuch dowodu

Operator albo kampanię można pobrać jako jeden ZIP (`/api/operators/{id}/package`, `/api/campaigns/{id}/package`, `similarity/package.py`): raport HTML do druku, artefakty, manifest i sumy SHA-256, STIX, krawędzie z dowodami. Łańcuch dowodu jest prosty i sprawdzalny bez naszego systemu: artefakt w magazynie jest adresowany swoim SHA-256, pakiet zapisuje go pod tą samą nazwą, a `manifest.json` i `SHA256SUMS` podają sumę, rozmiar, rodzaj, źródło (adres po redakcji tokenów), czas pozyskania do systemu i reklamy, z których plik pochodzi. Przy pakowaniu liczymy sumę odczytanych bajtów ponownie: plik, którego suma nie zgadza się z zapisaną, nie trafia do pakietu, tylko do listy pominiętych z powodem. `weryfikuj.py` (sam Python) sprawdza sumy, brakujące i nadmiarowe pliki.

Co to dowodzi, a czego nie: pakiet pokazuje, że pliki nie zmieniły się po jego utworzeniu i skąd każdy pochodzi w systemie. Nie dowodzi, kiedy powstał oryginał (czas pozyskania to chwila zapisu w SCAM DNA) ani kto go wytworzył, i nie jest podpisany elektronicznie. Raport nie renderuje stron oszustów: HTML i HAR są tylko plikami (`.html.txt`), niezredagowanymi, z ostrzeżeniem. Argumentem za jednym operatorem są najmocniejsze dowody z wkładem w bitach tak jak w interfejsie (`EdgeEvidence`), a test najsłabszego ogniwa pokazuje, co by się stało bez wybranych śladów, dla pojedynczych par (3 najmocniejszych i 2 najsłabszych powiązań grupy), nie dla całej grupy. Raport nie ma wersji PDF: HTML ma układ do druku (A4), a PDF z polskimi znakami wymagałby nowej biblioteki i osadzonej czcionki, więc analityk drukuje do PDF z przeglądarki.

## 10. Źródła danych

| Źródło | Do czego | Pochodzenie |
|---|---|---|
| materiały organizatora | korpus | paczka `DANE.zip` i archiwum ze strony z zajawką |
| Lista Ostrzeżeń CERT Polska | etykieta domeny, daty wpisu | https://hole.cert.pl/domains/v2/ |
| RDAP rejestru .pl i rdap.org | data rejestracji, rejestrator, serwery nazw | https://rdap.dns.pl, https://rdap.org |
| crt.sh | certyfikaty domeny z dzienników Certificate Transparency, domeny z pola SAN | https://crt.sh (`output=json`) |
| Team Cymru | numer AS dla adresu IP | zapytania DNS do `origin.asn.cymru.com` |
| Microsoft Ad Library API | reklamy z adresem docelowym, tło z reklam legalnych | https://adlibrary.api.bingads.microsoft.com |
| Meta Ad Library API | reklamy z UE (wymaga tokenu) | https://graph.facebook.com (`ads_archive`) |

## 11. Wynik na danych organizatora

Szczegóły: [dane-organizatora.md](dane-organizatora.md). W skrócie: 28 stron z 25 spraw. Operator A: 8 stron na 7 domenach w 2 kampaniach, spięte identyfikatorami z panelu lejka i pikselem. Operator B: 3 strony na 2 domenach. Sprawa 61: jedna kampania na 3 stronach. 14 stron bez operatora, w tym sprawy 48 i p11, które dzielą z operatorem A tylko silnik lejka i mają z nim relację `similar`.

## 12. Ograniczenia

- **Wagi są eksperckie.** Parametry `m`, `f0`, `cap` dobraliśmy ręcznie. Wrażliwość sprawdziliśmy na danych organizatora: szansa wstępna ×0,1 albo ×10 i próg pewności 0,8 albo 0,95 nie zmieniają żadnej relacji, a zmiana siły dowodów o ±50% rusza tylko 4 pary graniczne ([dane-organizatora.md](dane-organizatora.md)). Nie mamy zbioru z oznaczonymi kampaniami, więc nie podajemy precyzji ani czułości. Etap dalszy: model uczony na parach oznaczonych przez analityków.
- **Twarze tylko z bazy referencyjnej, bez głosu.** Twarz na zrzucie reklamy rozpoznajemy, gdy osoba jest w małej bazie zbudowanej ze zdjęć na wolnej licencji. Deepfake z osobą spoza bazy i bez nazwiska w tekście pozostaje nierozpoznany. Głosu jako cechy mówcy nie analizujemy.
- **Wideo z klatek i mowy.** Z nagrania bierzemy 8 klatek rozłożonych równomiernie, bez jednolitych plansz. Każda daje hash percepcyjny (miękki marker `video_frames`: ten sam materiał po ponownym zakodowaniu albo przycięciu), tekst z OCR (dołączony do tekstu reklamy, z reklamodawcą przy "Sponsorowane") i twarze z bazy referencyjnej. Z dźwięku bierzemy mowę: ffmpeg wyciąga pierwsze 120 s do 16 kHz mono, a lokalny model Whisper `small` (faster-whisper, CPU, język polski, `extractors/speech.py`) zamienia ją na tekst. Transkrypt dołączamy do tekstu reklamy po redakcji adresów, więc działają na nim te same ekstraktory (kontakty, słowa kluczowe, wzmianki o osobach, wektor znaczenia), a osobno zapisujemy go w opisie nagrania z oznaczeniem "mowa z nagrania". Segmenty uznane przez model za brak mowy odrzucamy. Nagranie bez dźwięku albo z samą ciszą nie daje transkryptu. Rozpoznaje mowę, a nie mówcę: nie porównujemy głosów, nie wykrywamy klonów głosu ani ruchu.
- **Strony na żywo.** Pobieramy HTML bez wykonywania JavaScriptu i bez obrazów. Pełny zestaw cech dają dopiero przechwycenia z HAR.
- **Hash obrazu** wykrywa ten sam obraz po przeróbkach, nie podobne ujęcie tej samej sceny.
- **Mały korpus.** Rzadkość opiera się głównie na częstościach bazowych typów. Z czasem zastąpią je częstości z danych.
