# Wymagania wyzwania i zgodność z regulaminem

Źródła: opis wyzwania NASK "Kolekcjoner fejków" (wersja z 21.11.2026, `docs/zrodla/`) i regulamin HackNation obowiązujący od 28.09.2026. Stan na 21.11.2026.

## Kryteria oceny (pkt 9 opisu wyzwania)

| Kryterium | Waga | Na czym się opieramy |
|---|---|---|
| Jakość metody korelacji i grupowania | 30% | model dowodowy par, trzy relacje, kampanie i operatorzy: [metodyka.md](metodyka.md), wyniki: [dane-organizatora.md](dane-organizatora.md) |
| Użyteczność i trafność cech oraz źródeł danych | 30% | 7 rodzin markerów, ok. 50 typów; lista CERT Polska, RDAP, biblioteki reklam |
| Kompletność demonstratora, proces end-to-end | 15% | wejście plikiem lub adresem, przebieg na żywo, wynik z dowodami |
| Czytelność i interpretowalność powiązań | 15% | każda krawędź ma listę dowodów z wkładem w bitach |
| Potencjał wdrożeniowy, skalowalność, przenośność | 10% | `docker compose up`, Temporal, wyszukiwanie kandydatów indeksem |

## Oczekiwany rezultat (pkt 3)

| Wymóg | Stan | Gdzie |
|---|---|---|
| Przyjmuje URL reklamy lub strony | jest | `POST /api/analyses` |
| Przyjmuje zrzut ekranu | jest | `POST /api/analyses/upload`, OCR |
| Przyjmuje log komunikacji | jest | HAR |
| Przyjmuje plik multimedialny | częściowo | obraz: tak; wideo: rejestrujemy plik i metadane, treści nie analizujemy |
| Przyjmuje dane z udostępnionego zbioru | jest | `manage.py import_bundle`, ZIP przez interfejs |
| Przyjmuje inną wskazówkę | jest | tekst, nazwa produktu |
| Tekst, słowa kluczowe, tematyka | jest | treść strony, OCR reklamy, `extractors/keywords.py` |
| Wizerunki osób | częściowo | wzmianka w tekście z odmianą, baza 30 osób; brak rozpoznawania twarzy |
| Logotypy | częściowo | podszycie pod markę po tekście; brak rozpoznawania logo na obrazie |
| Cechy wizualne | częściowo | hash percepcyjny zrzutu reklamy i obrazów strony; brak embeddingów obrazu |
| Domeny, przekierowania, linki, struktura stron | jest | URL, HAR, DOM |
| Publiczne metadane domen i infrastruktury | jest | RDAP, lista CERT Polska, DNS/ASN/certyfikat dla stron na żywo |
| Zestaw cech do porównywania | jest | markery twarde i miękkie |
| Duplikaty i warianty tego samego przekazu | jest | znacznik `duplicate`, relacja `same_campaign` |
| Metoda podobieństwa i grupowania w kampanie lub grupy podobnych kampanii | jest | kampania, operator, relacja `similar` |
| Analiza nowego materiału względem zbioru, wskazanie nowych kampanii | jest | ocena: `duplicate`, `known_campaign`, `known_operator`, `similar_only`, `new_pattern` |
| Prezentacja zależności w czytelnej formie | częściowo | lista powiązań i panel dowodów działają; graf jest w API (`/api/graph`), w interfejsie w budowie |
| Wskazanie cech i przesłanek powiązania | jest | `GET /api/edges/{id}` |
| Prosty interfejs graficzny | jest | Next.js, ekran Discovery |
| Udokumentowana metodyka | jest | [metodyka.md](metodyka.md) |
| Niekompletne dane | jest | strona niedostępna, brak HAR, brak adresu, sam zrzut: analiza się kończy, cech jest mniej |
| Dodatkowo: automatyczne wyszukiwanie w bibliotekach reklam, okresowa aktualizacja | częściowo | harmonogramy Temporal i konektor Microsoft działają; Meta wymaga tokenu |

## Wymagania formalne (pkt 4)

| Wymóg | Stan | Gdzie |
|---|---|---|
| Działający demonstrator z prostym interfejsem | jest | `frontend/`, http://localhost:3000 |
| Opis metodyki | jest | [metodyka.md](metodyka.md) |
| Instrukcja instalacji, konfiguracji i uruchomienia z zależnościami | jest | [README.md](../README.md) |
| Kod w repozytorium Git | jest | GitHub, repo prywatne: **trzeba nadać dostęp organizatorowi** |
| Środowisko skonteneryzowane | jest | `docker-compose.yml`, wszystkie usługi łącznie z interfejsem |
| Opis dostępu do usług wymagających autoryzacji | jest | [licencje.md](licencje.md): tylko Meta Ad Library, opcjonalna |
| Lista bibliotek, modeli i usług z licencjami i ograniczeniami | jest | [licencje.md](licencje.md) |

## Walidacja (pkt 6)

Organizator przetestuje rozwiązanie na nieudostępnionym zbiorze z nowymi wariantami znanych kampanii i z innymi kampaniami.

| Co sprawdzi | Jak się do tego mamy |
|---|---|
| Identyfikowanie podobnych materiałów i wariantów | 6 stron jednej kampanii na 5 domenach połączone |
| Przypisywanie nowych materiałów do istniejących grup | sprawy z drugiej paczki dołączyły do kampanii i operatora z pierwszej |
| Niełączenie tego, co nie powinno być połączone | 12 stron na innych zapleczach zostało osobno; kopia treści na innym zapleczu to tylko `similar` |
| Przydatność i różnorodność cech | 7 rodzin |
| Odporność na duplikaty, niekompletne dane, różne formaty | duplikat oznaczony; obsługa zapisanych stron, HAR, `page-capture`, archiwum NASK, zrzutów, wideo |
| Interpretowalność | dowody przy każdej krawędzi |
| Kompletność od wczytania do wyniku | `import_bundle` albo upload w interfejsie |

Nie mamy zbioru z oznaczonymi kampaniami, więc **nie podajemy liczbowej skuteczności**. Wyniki z dwóch paczek sprawdziliśmy ręcznie, przeglądając dowody.

## Zasady korzystania z danych (pkt 8)

| Zasada | Jak jej dotrzymujemy |
|---|---|
| Materiały organizatora tylko na potrzeby wyzwania | używane wyłącznie lokalnie do rozwoju i testów |
| Zakaz publicznego rozpowszechniania | `data/raw/` poza gitem; testy na zmyślonych wartościach; repo prywatne |
| Dodatkowe dane dozwolone po wskazaniu pochodzenia | źródła wymienione w [metodyka.md](metodyka.md) pkt 10 i [licencje.md](licencje.md) |

Do pilnowania:

- Repozytorium ma pozostać prywatne. `docs/dane-organizatora.md` wymienia domeny ze spraw.
- Zrzuty ekranu aplikacji z danymi organizatora w prezentacji są pokazywane jury, nie publikowane.
- Druga paczka pochodzi z archiwum ukrytego w zagadce organizatora. Traktujemy ją tak samo jak pierwszą.

## Regulamin HackNation

| Punkt | Treść | Stan |
|---|---|---|
| 4.3 | rozwiązania przesyła się 21.11 11:00 do 22.11 11:00 | **do zrobienia przez zespół** |
| 4.6 | zespół do 6 osób | do potwierdzenia przez zespół |
| 5.6 | etap I: ocena zgłoszeń na platformie HackTribe, 5 najlepszych zespołów do etapu II; etap II: 5 minut prezentacji i 5 minut pytań | prezentacja do przygotowania |
| 5.9 | po terminie zakaz zmian w rozwiązaniu | po 22.11 11:00 nie ruszamy repo |
| 6.1, 6.2 | uczestnik oświadcza, że jest twórcą swojego wkładu i że rozwiązanie nie narusza praw osób trzecich | biblioteki na licencjach otwartych, lista w [licencje.md](licencje.md); użycie asystenta AI ujawnione tamże |
| 6.3 | regulamin konkursu może przewidywać przeniesienie praw do rozwiązania | opis wyzwania NASK tego nie określa: **do wyjaśnienia z organizatorem** |

Z przewodnika uczestnika i FAQ (strona hacknation.pl, odczyt 21.11):

- **Szkic projektu na HackTribe do 21.11 godz. 20:00**, z repozytorium i wstępnym opisem. Po tej godzinie nie da się utworzyć projektu ani zmienić zadania.
- **Zgłoszenie końcowe do 22.11 godz. 11:00**: wymagane pola, prezentacja i materiały pozwalające sprawdzić projekt. Zalecane krótkie demo, do 2 minut.
- Zasoby zewnętrzne i przygotowane wcześniej trzeba wymienić. Zrobione w [licencje.md](licencje.md).
- Wątpliwości co do użycia AI i wcześniej przygotowanego kodu trzeba wyjaśnić z organizatorem przed zgłoszeniem.

## Otwarte sprawy dla zespołu

1. Założyć szkic na HackTribe przed 20:00 i podpiąć repozytorium.
2. Nadać organizatorowi dostęp do prywatnego repo albo ustalić inną formę przekazania kodu.
3. Zapytać mentorów NASK o dwie rzeczy: zasady użycia asystenta AI do pisania kodu oraz prawa do rozwiązania po konkursie.
4. Przygotować prezentację na 5 minut i demo do 2 minut.
