# Prompt do Claude Design: SCAM DNA

Wklej całość poniżej jako jedno zlecenie, z podłączonym tym repozytorium.

---

## 0. Kontekst repo i zakres na teraz (MVP na jutro)

Pracujesz w repozytorium, w którym backend już działa. Buduj prawdziwy kod w `frontend/` (Next.js 16, React 19, TypeScript, Tailwind 4). Przeczytaj najpierw `frontend/AGENTS.md`, `docs/api.md` i `frontend/src/lib/api.ts`.

Zasady twarde:
- Wszystkie dane bierz z klienta `frontend/src/lib/api.ts`. Żadnych danych na sztywno ani udawanych. Dane przykładowe z sekcji 8 służą tylko do makiet ekranów, których API jeszcze nie obsługuje.
- Punkt wyjścia to działający ekran `frontend/src/components/discovery.tsx`. Zastąp go, nie psując przepływu: wysłanie, strumień SSE, lista powiązań, panel dowodów, decyzja analityka.
- Graf: Sigma.js + Graphology, dane z `GET /api/graph`.

**P0, ma działać jutro na prawdziwym API:**
1. Discovery: wejście (URL albo tekst), analiza w toku ze strumienia SSE (etapy `ingest, crawl, extract, enrich, fuse, cluster, end`), graf dorysowujący krawędź przy każdym zdarzeniu `fuse/info`, wynik z kampanią.
2. Investigation: graf kampanii albo sąsiedztwa reklamy, filtr po rodzinach i typie relacji, klik w krawędź.
3. Panel dowodów krawędzi (`GET /api/edges/{id}`): obie reklamy, pewność, dowody z `weight_bits`, `df` z `corpus_n`, znacznik `decisive`, przyciski decyzji (`POST /api/edges/{id}/verdict`).
4. Karta reklamy (`GET /api/ads/{id}`): genom w siedmiu pasmach.
5. Lista i karta kampanii (`GET /api/campaigns`, `GET /api/campaigns/{id}`): reklamy, krawędzie, markery rdzeniowe.
6. Archiwum reklam (`GET /api/ads?q=&source=&campaign=`).

**P1, tylko projekt ekranu, bez podpinania:** Evolution (oś czasu), źródła i skany, baza osób, kolejka etykietowania, alerty, piaskownica, raporty, jakość modelu, administracja. API dla nich jeszcze nie istnieje, więc oznacz je w interfejsie jako niedostępne zamiast pokazywać zmyślone liczby.

Poniżej pełna wizja produktu. Stosuj jej kierunek wizualny, kolory rodzin i komponenty już w P0.

---

Zaprojektuj kompletny interfejs aplikacji **SCAM DNA**. To platforma analityki śledczej, która łączy pozornie niezależne fałszywe reklamy w kampanie na podstawie wspólnych śladów cyfrowych. Nie jest to detektor pojedynczego fejka i nie jest to strona internetowa. Ma wyglądać i działać jak profesjonalne oprogramowanie do cyfrowego śledztwa.

## 1. Kto tego używa

- **Analityk CSIRT** (główny użytkownik). Pracuje w narzędziu 6 do 8 godzin dziennie, monitor 27 cali, często dwa. Zna pojęcia: domena, ASN, certyfikat, JARM, piksel śledzący, TDS, cloaking. Chce gęstości informacji, skrótów klawiszowych i zero ozdobników.
- **Kierownik zespołu**. Patrzy na kampanie, operatorów, trendy i jakość modelu.
- **Instytucja partnerska** (bank, regulator, platforma). Dostaje raporty i dostęp przez API.

## 2. Zasady, których nie wolno złamać

1. **Każda krawędź ma dowody.** Połączenie między dwiema reklamami zawsze da się kliknąć i zobaczyć, z czego wynika: typ markera, wartości po obu stronach, rzadkość markera w korpusie, wkład do wyniku, poziom pewności, artefakt źródłowy.
2. **Frontend pokazuje wyłącznie wyniki backendu.** Animacje odtwarzają prawdziwe zdarzenia analizy w kolejności, w jakiej zaszły. Nic nie jest udawane ani losowane dla efektu.
3. **Dwa typy relacji są zawsze rozróżnialne**: `SAME_CAMPAIGN` (to samo źródło, linia ciągła) i `SIMILAR_TO` (podobna koncepcja, inny operator, linia przerywana).
4. **Hierarchia jest zawsze widoczna** w okruszkach: rodzina narracji › operator › kampania › wariant kreacji › reklama.

## 3. Kierunek wizualny

Wzorce do naśladowania w układzie i gęstości: Maltego, i2 Analyst's Notebook, Wireshark, IDA Pro, DaVinci Resolve, Linear. Stanowisko pracy, nie produkt marketingowy.

- Panele dokowane z uchwytami do zmiany rozmiaru, zakładki w panelach, pasek stanu na dole, paleta poleceń pod Ctrl+K.
- Motyw ciemny jako domyślny, motyw jasny dla raportów i wydruku. Oba dopracowane, jasny nie może być prostą inwersją.
- Tło grafitowe z lekkim odchyleniem w stronę niebieskiego, nie czysta czerń. Powierzchnie rozróżniane jasnością, nie cieniem.
- Krój bezszeryfowy o wąskich proporcjach dla interfejsu (np. IBM Plex Sans), krój o stałej szerokości dla każdego identyfikatora, hasha, domeny, adresu IP i znacznika czasu (np. IBM Plex Mono lub JetBrains Mono). Cyfry tabelaryczne w tabelach.
- Rozmiar bazowy 13 px, wiersz tabeli 28 px, promień narożników 2 do 4 px.
- Ikony liniowe, jeden zestaw, 16 px.
- Ruch krótki i funkcjonalny: 120 do 200 ms dla paneli, dłuższe sekwencje tylko w trybie Evolution i przy dorysowywaniu grafu w Discovery. Szanuj `prefers-reduced-motion`.

Czego unikać: sekcji hero, gradientów fioletowo-niebieskich, zielonych znaków na czarnym tle w stylu Matrixa, szkła i rozmyć, dużych zaokrągleń, emoji, kart z kolorowym paskiem po lewej, wyśrodkowanych układów, ilustracji i haseł marketingowych.

## 4. Kolor niesie znaczenie

Kolor akcentu interfejsu jest jeden i stonowany. Reszta palety koduje dane.

**Siedem rodzin markerów**, każda ma własny kolor, ten sam w grafie, w pasmach genomu, w chipach i w panelu dowodów. Paleta musi być rozróżnialna dla osób z zaburzeniami widzenia barw i czytelna w obu motywach:

| Rodzina | Przykładowe markery |
|---|---|
| Infrastruktura | domena, łańcuch przekierowań, IP, ASN, serwery nazw, certyfikat TLS, JARM, hash favicony, rejestrator |
| Tracking i lejek | Google Analytics, GTM, Meta Pixel, Yandex Metrica, ID kampanii w TDS, endpoint formularza leadów |
| Szablon strony | hash struktury DOM, hash bundli JS i CSS, zrzut ekranu, "biała strona" cloakingu |
| Kreacja | hash pliku, hash percepcyjny, kopia po przeróbce, tekst z OCR, materiał źródłowy wideo |
| Narracja | rama oszustwa, obiecany zysk, presja czasu, telefon, e-mail, handle komunikatora, adres krypto |
| Osoby i marki | twarz, głos, wzmianka w tekście, logo, strona reklamodawcy, płatnik |
| Zachowanie | zbieżność czasowa startów, targetowanie, rotacja domen |

**Pewność** kodowana grubością i nasyceniem krawędzi oraz miernikiem 0 do 1 z dwoma miejscami po przecinku.

**Kolory stanu** (osobne od rodzin): potwierdzone przez analityka, niepewne, odrzucone, nowe.

**Kształt węzła koduje typ**: reklama, kreacja, strona reklamodawcy, domena, adres IP, certyfikat, identyfikator śledzący, osoba, marka, kampania, operator.

## 5. Szkielet aplikacji

- **Lewa szyna** (48 px): przełącznik trybów Discovery, Investigation, Evolution, niżej Archiwum, Osoby, Źródła, Etykietowanie, Alerty, Raporty, Administracja.
- **Górny pasek**: okruszki hierarchii, wyszukiwarka globalna, wskaźnik trwających analiz, przełącznik motywu, użytkownik i rola.
- **Obszar roboczy**: 2 do 4 paneli dokowanych, domyślnie płótno grafu po środku, inspektor po prawej, tabela lub oś czasu na dole.
- **Pasek stanu** (24 px): liczba reklam w korpusie, liczba kampanii, czas ostatniego skanu, długość kolejki, stan połączenia ze strumieniem zdarzeń.

## 6. Ekrany do zaprojektowania

Każdy ekran jako osobny artboard 1920×1080 w motywie ciemnym. Ekrany oznaczone gwiazdką także w motywie jasnym.

### Tryb Discovery (analiza nowego materiału)

1. **Wejście.** Strefa upuszczania z czterema ścieżkami: adres URL, zrzut ekranu z linkiem, plik z reklamą (obraz lub wideo), wskazówka tekstowa (nazwa produktu). Pod spodem ostatnie analizy. Stan pusty ma pokazywać, co się wydarzy po wrzuceniu, bez samouczka.
2. **Analiza w toku.** Lewy panel: oś etapów na żywo ze stanem i czasem każdego kroku: pobranie, łańcuch przekierowań, zrzuty strony, ekstrakcja per rodzina markerów, wzbogacanie, kandydaci, fuzja dowodów. Środek: graf dorysowujący węzły i krawędzie w miarę napływu zdarzeń. Dół: dziennik zdarzeń w mono. Pokaż ten ekran w trzech klatkach: 15%, 60%, 100%.
3. **Wynik.** ★ Werdykt przypisania, np. "dołączono do kampanii K-0142, pewność 0,94" albo "nowa kampania, brak powiązań powyżej progu". Pięć najsilniejszych dowodów z wkładem. Genom reklamy jako siedem poziomych pasm. Przyciski: otwórz w Investigation, pokaż w Evolution, zgłoś.

### Tryb Investigation (praca na grafie)

4. **Graf główny.** ★ Płótno z kilkuset węzłami, widoczne skupiska kampanii. Panel filtrów: rodziny markerów, typ relacji, próg pewności, zakres dat. Legenda kształtów i kolorów, minimapa, licznik zaznaczenia. Menu kontekstowe węzła z akcją "pivot": znajdź wszystko, co dzieli ten marker.
5. **Panel dowodów krawędzi.** ★ Najważniejszy ekran. Po kliknięciu krawędzi inspektor pokazuje: obie reklamy obok siebie, łączną pewność, listę dowodów posortowaną według wkładu. Każdy dowód to karta: rodzina, nazwa markera, wartość po lewej i prawej stronie w mono, rzadkość ("występuje w 3 z 1 284 006 reklam"), wkład w bitach, link do artefaktu. Rozwinięcie karty pokazuje porównanie: dwie kreacje z nałożoną różnicą, dwa fragmenty DOM, dwie klatki wideo, dwa łańcuchy przekierowań. Na dole decyzja analityka: potwierdź, odrzuć, niepewne, z polem na uzasadnienie.
6. **Karta reklamy.** Kreacja, tekst z OCR, transkrypt z ASR ze znacznikami czasu, łańcuch przekierowań jako diagram skoków z kodami HTTP, zrzuty landing page w dwóch wersjach (to, co widzi bot, i to, co widzi ofiara), pełna lista markerów w siedmiu pasmach, historia migawek.
7. **Karta kampanii.** ★ Nagłówek z liczbami: reklamy, warianty kreacji, domeny, strony reklamodawców, okres aktywności. Siatka wariantów kreacji. Tabela domen z paskiem życia. Użyte wizerunki. Rama narracyjna. Markery rdzeniowe, czyli te, które spinają kampanię.
8. **Karta operatora.** Kilka kampanii jednego źródła, wspólna infrastruktura i narzędzia, mapa hostingu według ASN i kraju.
9. **Rodzina narracji.** Kampanie podobne koncepcyjnie, ale od różnych operatorów. Pokaż, czym się różnią mimo podobieństwa.

### Tryb Evolution (czas)

10. **Oś czasu kampanii.** ★ Tory poziome: reklamy, kreacje, domeny, certyfikaty, strony reklamodawców. Suwak czasu, odtwarzanie, prędkość. Widać, kiedy reklama powstała, zmieniła się i zniknęła ze źródła. Znaczniki zdarzeń: rejestracja domeny, wydanie certyfikatu, wpis na listę ostrzeżeń, usunięcie reklamy.
11. **Graf w czasie.** Ten sam graf co w Investigation, ale stan zależy od pozycji suwaka. Pokaż trzy klatki: narodziny kampanii, szczyt, wygaszanie i przeniesienie na nowe domeny.
12. **Rekonstrukcja przestrzenna.** Widok 3D: kampania jako struktura warstwowa, warstwy to rodziny markerów, wysokość to czas. Ma służyć prezentacji i orientacji, nie zastępuje grafu 2D.

### Zaplecze

13. **Archiwum.** Wyszukiwarka pełnotekstowa z fasetami: źródło, data, język, osoba, marka, kampania, stan. Gęsta tabela z miniaturami, zapisane zapytania, eksport.
14. **Baza referencyjna osób.** Lista osób publicznych, których wizerunek jest nadużywany. Dla każdej: liczba kampanii, kanały rozpoznania (twarz, głos, wzmianka), materiały źródłowe, z których zrobiono deepfake, oś czasu nadużyć.
15. **Źródła danych i skany.** Tabela konektorów: biblioteki reklam, listy ostrzeżeń, logi certyfikatów, RDAP, pasywny DNS, skanery URL. Dla każdego: stan, ostatnia synchronizacja, liczba rekordów, wykorzystanie limitu, błędy. Niżej harmonogram skanów i historia przebiegów workflow z możliwością ponowienia kroku.
16. **Kolejka etykietowania.** Pary o niepewnym wyniku do szybkiej oceny klawiaturą: ta sama kampania, podobna, niezwiązane. Licznik postępu i wpływ na model.
17. **Alerty.** Nowa odsłona znanej kampanii, nowa domena pasująca do wzorca, powrót wizerunku. Czas od pierwszego wykrycia.
18. **Piaskownica.** Bezpieczny podgląd złośliwej strony: zrzut, drzewo zasobów, żądania sieciowe, skrypty, ciasteczka. Wyraźne oznaczenie, że strona nie jest ładowana w przeglądarce analityka.
19. **Raport i eksport.** Podgląd raportu kampanii dla instytucji w motywie jasnym, format A4. Eksport STIX i MISP. Formularz zgłoszenia do platformy.
20. **Jakość modelu.** Metryki łączenia: precision, recall i F1 par, B-cubed, liczba kampanii. Wkład każdej rodziny markerów (ablacja). Macierz pomyłek decyzji analityków względem modelu.
21. **Administracja.** Role i uprawnienia, klucze API z zakresami, dziennik audytu każdej akcji z filtrem po użytkowniku i obiekcie.

## 7. Komponenty do systemu projektowego

- **Pasmo genomu**: siedem torów, każdy to rodzina markerów, znaczniki na torze to konkretne markery. Dwa genomy jeden pod drugim pokazują zgodne pozycje.
- **Chip markera**: kolor rodziny, nazwa, wartość w mono, rzadkość.
- **Karta dowodu**: zwinięta i rozwinięta.
- **Miernik pewności**: liczba i pasek, trzy progi.
- **Węzły i krawędzie grafu**: wszystkie typy, stany domyślny, najechany, zaznaczony, przygaszony, potwierdzony, odrzucony.
- **Diagram łańcucha przekierowań**: skoki z kodem HTTP, domeną i czasem.
- **Tor osi czasu i znacznik zdarzenia.**
- **Gęsta tabela**: sortowanie, fasety, zaznaczanie wielu wierszy, kolumna z miniaturą.
- **Oś etapów analizy**: oczekuje, trwa, zakończony, błąd, ponawiany.
- **Paleta poleceń, menu kontekstowe, powiadomienie, okno potwierdzenia.**
- **Stany puste, ładowania i błędu** dla grafu, tabeli i panelu dowodów.

## 8. Dane przykładowe

Używaj realistycznych danych, nigdy lorem ipsum. Wszystko fikcyjne:

- Domeny tylko w strefie `.example`, np. `zysk-dla-polakow.example`, `inwest-portal24.example`.
- Osoby jako "Osoba publiczna A", "Osoba publiczna B". Żadnych prawdziwych nazwisk ani twarzy, w miejscu twarzy neutralny zastępnik.
- Marki fikcyjne. Żadnych logotypów prawdziwych firm i mediów.
- Identyfikatory w prawdziwych formatach: `G-7K2QX9LM4T`, `GTM-N4R8ZP`, SHA-256 skrócone do 12 znaków, hash favicony jako liczba całkowita ze znakiem, JARM jako 62 znaki, numer AS z nazwą.
- Kampania wzorcowa do pokazania wszędzie: **K-0142 "Platforma inwestycyjna z wizerunkiem Osoby publicznej A"**, 214 reklam, 37 wariantów kreacji, 58 domen, 12 stron reklamodawców, aktywna 96 dni. Druga kampania K-0177 podobna narracyjnie, inny operator.

## 9. Język i teksty

Interfejs po polsku. Nazwy trybów zostają po angielsku: Discovery, Investigation, Evolution. Etykiety krótkie i rzeczowe, czasownik na przycisku mówi, co się stanie. Komunikaty błędów mówią, co się nie udało i co zrobić. Bez wykrzykników.

## 10. Co dostarczyć

1. System projektowy: tokeny kolorów dla obu motywów, skala typografii, odstępy, wszystkie komponenty z sekcji 7.
2. Szkielet aplikacji z dokowanymi panelami.
3. 21 ekranów z sekcji 6 w motywie ciemnym, ekrany z gwiazdką także w jasnym.
4. Klikalny prototyp głównej ścieżki: Discovery wejście → analiza w toku → wynik → klik w krawędź → panel dowodów → karta kampanii → Evolution.
5. Krótka specyfikacja ruchu: dorysowywanie grafu w Discovery, otwieranie panelu dowodów, odtwarzanie osi czasu.

Zacznij od systemu projektowego i ekranu 5 (panel dowodów krawędzi). Od niego zależy reszta.
