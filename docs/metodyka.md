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
| plik wideo z metadanymi yt-dlp | `POST /api/analyses/upload` (rejestrujemy plik i numer reklamy, treści wideo nie analizujemy) |
| reklamy z bibliotek | konektory w `collectors/`, uruchamiane ręcznie albo z harmonogramu |

Jedna strona docelowa to jedna jednostka analizy. Zapisana strona i HAR tej samej domeny z jednego katalogu łączymy w jedną jednostkę. Zrzuty reklamy z katalogu sprawy dołączamy do każdej strony tej sprawy (`collectors/bundle.py`).

## 3. Potok analizy

Sześć etapów (`workflows/pipeline.py`). Każdy zapisuje wynik do bazy i zdarzenia postępu, więc orkiestrator (Temporal) może ponowić dowolny z nich, a interfejs pokazuje przebieg na żywo.

1. **Przyjęcie.** Utworzenie rekordu reklamy.
2. **Strona.** Dla materiału z przechwycenia bierzemy HTML i HAR z plików i niczego nie pobieramy z sieci. Dla adresu na żywo pobieramy stronę dwa razy, jako automat i jako ofiara z telefonu po kliknięciu w reklamę, i zapisujemy łańcuch przekierowań.
3. **Ekstrakcja cech.** Sekcja 4.
4. **Wzbogacanie.** Dane rejestrowe domeny (RDAP), obecność na Liście Ostrzeżeń CERT Polska, certyfikaty domeny z dzienników Certificate Transparency (crt.sh). Dla strony badanej na żywo także DNS, ASN, certyfikat i favicon.

   Z crt.sh bierzemy do 50 najnowszych certyfikatów domeny, także dawnych. Numer seryjny każdego trafia do markera `tls_serial`, tego samego co numer z `dns_ssl.json` w paczkach. Certyfikat wystawiony na kilka domen łączy je jako ślad jednego konta, a pozostałe domeny z pola SAN analiza wypisuje jako tropy. Certyfikat CDN na kilkanaście niezwiązanych domen (ponad 10 domen rejestrowych albo host `cloudflaressl.com`) pomijamy. Odpowiedź trzymamy w bazie przez 7 dni, zapytania idą po kolei co 3 sekundy z limitem 25 sekund. Brak odpowiedzi crt.sh pomija ten krok i analiza idzie dalej, a przez kolejne 10 minut crt.sh nie jest pytany wcale, żeby import wielu stron nie czekał na każdy limit czasu.
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
- **Treść.** MinHash z pięcioznakowych wycinków znormalizowanego tekstu: małe litery, cyfry zamienione na zera, bez interpunkcji. Podmiana kwoty albo daty nie zmienia wyniku. Gdy krótszy tekst prawie cały (od 85%) siedzi w dłuższym, podobieństwem jest to zawieranie, a nie Jaccard. Zawieranie wylicza się z Jaccarda i liczności obu zbiorów, które sygnatura niesie na końcu. Dzięki temu zapis strony z doklejonymi komentarzami albo stopką dalej jest tym samym artykułem. Zawierania nie liczymy dla krótkich tekstów (poniżej 300 wycinków), gdy dłuższy tekst jest ponad trzy razy większy (baner zawarty w każdej stronie robiłby z różnych stron ten sam tekst) i gdy rozmiary różnią się o mniej niż 10% (wtedy pełne zawieranie i tak daje wysoki Jaccard, a częściowe tylko by go zawyżało).
- **Obrazy** (`extractors/images.py`). Hash różnicowy (dHash, 64 bity) odporny na zmianę rozmiaru i kompresję. Dwa obrazy są tym samym obrazem, gdy hasze różnią się o najwyżej 6 bitów. Stronę opisuje zbiór haszy jej obrazów, pomijamy obrazy mniejsze niż 160 pikseli.
- **OCR** (`extractors/ocr.py`). Ze zrzutu reklamy wyciągamy nazwę reklamodawcy (wiersz przy "Sponsorowane"), tekst reklamy i numer z Biblioteki Reklam Mety.
- **Osoby** (`people/matching.py`). Baza referencyjna 30 osób publicznych. Dopasowanie po imieniu i nazwisku z tolerancją na odmianę: "Jana Kowalskiego" to Jan Kowalski.
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

## 9. Interpretowalność

Każda krawędź ma w bazie listę dowodów (`EdgeEvidence`): rodzina, typ, wartości po obu stronach, liczba źródeł z tą wartością, wkład w bitach, znacznik rozstrzygania i odnośniki do plików, z których cecha pochodzi. Krawędź bez dowodów nie powstaje. Decyzja analityka (potwierdź, odrzuć, niepewne) zapisuje się w dzienniku audytu.

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

- **Wagi są eksperckie.** Parametry `m`, `f0`, `cap` dobraliśmy ręcznie. Nie mamy zbioru z oznaczonymi kampaniami, więc nie podajemy precyzji ani czułości. Etap dalszy: model uczony na parach oznaczonych przez analityków.
- **Brak twarzy i głosu.** Osoby rozpoznajemy po tekście. Deepfake z osobą, której nazwisko nie pada w tekście, pozostaje nierozpoznany.
- **Wideo.** Rejestrujemy plik, nie analizujemy treści.
- **Strony na żywo.** Pobieramy HTML bez wykonywania JavaScriptu i bez obrazów. Pełny zestaw cech dają dopiero przechwycenia z HAR.
- **Hash obrazu** wykrywa ten sam obraz po przeróbkach, nie podobne ujęcie tej samej sceny.
- **Mały korpus.** Rzadkość opiera się głównie na częstościach bazowych typów. Z czasem zastąpią je częstości z danych.
