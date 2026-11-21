# Plan rozwoju SCAM DNA na rok

Plan ułożony tak, jakby projekt miał rok na rozwój u analityków NASK. Cztery etapy po kwartale, każdy z celem i miarą sukcesu. Kolumna "do 22.11" mówi, co z danego etapu powstało w czasie hackathonu, a "dalej" to, co zostaje na resztę roku. Stan na 22.11.2026, zadania w GitHub Issues.

## Punkt wyjścia

Działa całość od wczytania materiału do wyniku: import przechwyceń i uploadów, ok. 50 typów markerów w 7 rodzinach, model par Fellegi-Sunter z ważeniem rzadkością i regułą niezależnych potwierdzeń, kampanie i operatorzy, interfejs z grafem i panelem dowodów, laboratorium dowodów, porównanie przechwyceń, twarze, nagrania, znaczenie treści, eksport ZIP i STIX 2.1. Szczegóły: [metodyka.md](metodyka.md), wyniki: [dane-organizatora.md](dane-organizatora.md).

## Etap 1: zbieranie (kwartał 1)

**Cel.** Strona badana na żywo daje te same ślady co przechwycenie z narzędzi deweloperskich: ścieżki zaplecza, identyfikatory z panelu lejka, hosty zasobów. Dziś pełny zestaw cech dają tylko przechwycenia z HAR.

**Miara.** Dla stron z paczki organizatora, które jeszcze działają, crawler daje co najmniej 80% markerów z HAR organizatora. Zero połączeń kontenera crawlera z bazą i magazynem dowodów.

| Do 22.11 | Dalej |
|---|---|
| crawler z Chromium w osobnym kontenerze i sieci, HAR i zrzut strony z renderu, cloaking z porównania renderu ofiary i automatu ([#206](https://github.com/NikodemJachec99/deepfake-atlas/issues/206)) | proxy z polskim adresem domowym i mobilnym (oszuści blokują centra danych), profile urządzeń, nagrywanie interakcji z formularzem |
| skany Microsoft Ad Library z harmonogramu, wstrzymywane na demo | Meta Ad Library na żywym tokenie (wymaga weryfikacji tożsamości), Google Ads Transparency, TikTok |
| import paczek organizatora i archiwów NASK | stały kanał przechwyceń od analityków NASK, zgłoszenia z formularza CERT |

## Etap 2: metoda (kwartał 2)

**Cel.** Wagi z danych zamiast eksperckich, bez pogorszenia wyników i z mierzalną jakością.

**Miara.** Uczone wagi nie zmieniają rdzenia znanych operatorów i nie tworzą fałszywych połączeń w pomiarze odporności. Po zebraniu 300 decyzji analityków: precyzja połączeń wspólnego źródła co najmniej 0,95 przy czułości co najmniej 0,8 na odłożonym zbiorze.

| Do 22.11 | Dalej |
|---|---|
| pomiar odporności na brak materiału i wrażliwości na wagi ([dane-organizatora.md](dane-organizatora.md)) | ten sam pomiar co miesiąc na rosnącym korpusie |
| EM Fellegi-Sunter bez etykiet, przełącznik wag eksperckie i uczone, kalibracja na decyzjach analityka, gdy są ([#207](https://github.com/NikodemJachec99/deepfake-atlas/issues/207)) | kolejka etykietowania par granicznych (aktywne uczenie), model uczony na decyzjach, precyzja i czułość |
| laboratorium dowodów, test najsłabszego ogniwa, wskazówki, pamięć decyzji analityka | precedensy decyzji jako cecha modelu, przegląd krawędzi przez drugi zespół |

## Etap 3: analiza wizualna i dźwięk (kwartał 3)

**Cel.** Łączenie po podobnym ujęciu, logo i mowie, a nie tylko po identycznym obrazie i tekście.

**Miara.** Każda z nowych cech daje co najmniej jedno połączenie na danych organizatora, którego nie dawały wcześniejsze, i żadnego połączenia wspólnego źródła samodzielnie (to zawsze opowieść, nie zaplecze).

| Do 22.11 | Dalej |
|---|---|
| twarze z bazy referencyjnej 10 osób, także na klatkach nagrań; 8 klatek z każdego nagrania (OCR, hash) | baza osób z zespołem NASK, rozpoznawanie deepfake'ów (cechy generowanego obrazu i głosu) |
| znaczenie treści lokalnym modelem wielojęzycznym (przepisany artykuł 0,98 przy MinHash 0,39) | model dostrojony na polskich artykułach oszustów |
| podobne ujęcie z embeddingu obrazu CLIP ([#209](https://github.com/NikodemJachec99/deepfake-atlas/issues/209)); logo zero-shot sprawdzone i odrzucone (przewaga nad drugą marką do 0,03), transkrypcja mowy ([#210](https://github.com/NikodemJachec99/deepfake-atlas/issues/210)): Whisper `small` lokalnie na CPU, 120 s dźwięku w ok. 12 s, wynik w tekście reklamy i `Ad.raw["videos"]` | logo przez detekcję i wycinek wokół znaku, klon głosu (porównanie mówcy), ruch w nagraniu |

## Etap 4: wdrożenie i wymiana (kwartał 4)

**Cel.** System sam pilnuje znanych operatorów i oddaje wiedzę zespołom CERT bez ręcznego przepisywania.

**Miara.** Czas od pojawienia się nowej odsłony znanej kampanii w bibliotece reklam do alertu krótszy niż jeden cykl skanu (6 godzin). Wskaźniki trafiają do MISP NASK automatycznie.

| Do 22.11 | Dalej |
|---|---|
| alerty o nowych materiałach znanych kampanii i operatorów ([#208](https://github.com/NikodemJachec99/deepfake-atlas/issues/208)) | powiadomienia (e-mail, komunikator), reguły per operator |
| eksport STIX 2.1 i ZIP z wzbogaconym korpusem | serwer TAXII, synchronizacja z MISP, wpisy na Listę Ostrzeżeń CERT Polska po decyzji analityka |
| klucz API dla zapisu (domyślnie wyłączony), kontrola Origin, ochrona przed SSRF | konta i role (analityk, przeglądający), dziennik audytu w interfejsie, wdrożenie w sieci NASK |
| `docker compose up`, sprawdzone na Windowsie i Linuksie | Kubernetes, kopie zapasowe, monitoring kolejek Temporala |

## Ryzyka

- **Prawo.** Twarze to dane biometryczne (RODO art. 9). Przed użyciem poza konkursem potrzebna podstawa prawna, dziś porównujemy tylko z małą bazą osób publicznych.
- **Blokady.** Oszuści pokazują białe strony automatom i centrom danych, więc bez proxy domowego część stron na żywo da mniej śladów.
- **Etykiety.** Bez decyzji analityków nie da się podać precyzji ani czułości. Dlatego kolejka etykietowania jest na początku etapu 2.
- **Koszt modeli.** Wszystkie modele działają lokalnie na CPU. Większe modele obrazu i mowy mogą wymagać GPU.
