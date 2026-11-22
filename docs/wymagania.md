# Wymagania wyzwania i zgodność z regulaminem

Źródła: opis wyzwania NASK "Kolekcjoner fejków" (pełna wersja z 21.11.2026: opis, kryteria, walidacja i zajawka "Follow the Fake", [docs/zrodla/opis-zadania.pdf](zrodla/opis-zadania.pdf)) regulamin zadania konkursowego "Kolekcjoner fejków" z wzorem umowy przeniesienia praw ([docs/zrodla/regulamin-zadania.pdf](zrodla/regulamin-zadania.pdf)) i regulamin HackNation obowiązujący od 28.09.2026. Stan na 22.11.2026.

## Kryteria oceny (pkt 9 opisu wyzwania)

| Kryterium | Waga | Na czym się opieramy |
|---|---|---|
| Jakość metody korelacji i grupowania | 30% | model dowodowy par, trzy relacje, kampanie i operatorzy: [metodyka.md](metodyka.md), wyniki: [dane-organizatora.md](dane-organizatora.md) |
| Użyteczność i trafność cech oraz źródeł danych | 30% | 7 rodzin markerów, 62 typy (57 niosących dowód, 5 kluczy wyszukiwania; 22 rozstrzygające), lista CERT Polska, RDAP, crt.sh, biblioteki reklam: [README, genom reklamy](../README.md#genom-reklamy) |
| Kompletność demonstratora, proces end-to-end | 15% | wejście plikiem lub adresem, przebieg na żywo, wynik z dowodami |
| Czytelność i interpretowalność powiązań | 15% | każda krawędź ma listę dowodów z wkładem w bitach |
| Potencjał wdrożeniowy, skalowalność, przenośność | 10% | `docker compose up`, Temporal, wyszukiwanie kandydatów indeksem |

## Oczekiwany rezultat (pkt 3)

| Wymóg | Stan | Gdzie |
|---|---|---|
| Przyjmuje URL reklamy lub strony | jest | `POST /api/analyses` |
| Przyjmuje zrzut ekranu | jest | `POST /api/analyses/upload`, OCR |
| Przyjmuje log komunikacji | jest | HAR |
| Przyjmuje plik multimedialny | jest | obraz: tak; wideo: metadane, klatka poglądowa, 8 klatek z hashem, OCR i twarzami (`extractors/video.py`) oraz mowa z nagrania zamieniona na tekst (`extractors/speech.py`, Whisper lokalnie) |
| Przyjmuje dane z udostępnionego zbioru | jest | `manage.py import_bundle`, ZIP przez interfejs |
| Przyjmuje inną wskazówkę | jest | tekst, nazwa produktu |
| Tekst, słowa kluczowe, tematyka | jest | treść strony, OCR reklamy, `extractors/keywords.py` |
| Wizerunki osób | jest, w zakresie bazy | wzmianka w tekście z odmianą (30 osób) i twarz na zrzucie reklamy porównana z bazą referencyjną ze zdjęć na wolnej licencji (`people/faces.py`); także na klatkach nagrań, oraz nazwisko wypowiedziane w nagraniu (transkrypt mowy); głosu mówcy nie porównujemy |
| Logotypy | częściowo | podszycie pod markę po tekście; brak rozpoznawania logo na obrazie |
| Cechy wizualne | częściowo | hash percepcyjny zrzutu reklamy i obrazów strony, wektor obrazu CLIP (podobne ujęcie); bez rozpoznawania logo |
| Domeny, przekierowania, linki, struktura stron | jest | URL, HAR, DOM |
| Publiczne metadane domen i infrastruktury | jest | RDAP, lista CERT Polska, certyfikaty z crt.sh, DNS/ASN/certyfikat dla stron na żywo |
| Zestaw cech do porównywania | jest | markery twarde i miękkie |
| Duplikaty i warianty tego samego przekazu | jest | znacznik `duplicate`, relacja `same_campaign` |
| Metoda podobieństwa i grupowania w kampanie lub grupy podobnych kampanii | jest | kampania, operator, relacja `similar` |
| Analiza nowego materiału względem zbioru, wskazanie nowych kampanii | jest | ocena: `duplicate`, `known_campaign`, `known_operator`, `similar_only`, `new_pattern` |
| Prezentacja zależności w czytelnej formie | tak | graf sąsiedztwa reklamy, kampanii i operatora w interfejsie (`/investigation`, z API `/api/graph`), lista powiązań, panel dowodów z wkładem rodzin, karta operatora, zrzuty z powiększeniem (lightbox), podsumowanie pliku HAR (`GET /api/artifacts/{sha}/har`) zamiast surowego odnośnika |
| Wskazanie cech i przesłanek powiązania | jest | `GET /api/edges/{id}` |
| Prosty interfejs graficzny | jest | Next.js 16: ekran Analiza (Discovery), kolejka „Do oceny”, graf, karty kampanii, operatorów i reklam, alerty, łowca domen, wagi, zakwestionowania. Tryb prosty (domyślny) i przełącznik „Szczegóły techniczne”. Układ responsywny z dolną nawigacją na telefonie. Własna marka: znak z pasmami genomu, granat i kobalt, pięć kolorów rodzin śladów |
| Zakwestionowanie przesłanki w całym korpusie | jest, dodatkowo | podgląd, zapis i przywrócenie: `POST /api/premises/preview`, `POST /api/premises`, `POST /api/premises/{id}/restore`, historia `GET /api/premises`; ekran „Zakwestionowania” |
| Kolejka par do oceny z powodem uwagi | jest, dodatkowo | `GET /api/review`, ekran „Do oceny”, decyzja przypięta do wersji dowodów |
| Laboratorium dowodów, najsłabsze ogniwo, dwie twarze jednego linku | jest, dodatkowo | `POST /api/edges/{id}/simulate`, `.../weakest-link`, `GET /api/observations/compare`; [laboratorium.md](laboratorium.md), [dwie-twarze.md](dwie-twarze.md) |
| Eksport dla analityków i zespołów CERT | jest, dodatkowo | pakiet dowodowy ZIP (raport, SHA-256, STIX 2.1, `weryfikuj.py`), `GET /api/export/stix`, `GET /api/export` |
| Łowca domen i alerty | jest, dodatkowo | `manage.py hunt`, `GET /api/hunt`, `GET /api/alerts`; [metodyka.md](metodyka.md) sekcja 8a |
| Udokumentowana metodyka | jest | [metodyka.md](metodyka.md) |
| Niekompletne dane | jest | strona niedostępna, brak HAR, brak adresu, sam zrzut: analiza się kończy, cech jest mniej |
| Dodatkowo: automatyczne wyszukiwanie w bibliotekach reklam, okresowa aktualizacja | częściowo | harmonogramy Temporal i konektor Microsoft działają; Meta wymaga tokenu |

## Wymagania formalne (pkt 4)

| Wymóg | Stan | Gdzie |
|---|---|---|
| Działający demonstrator z prostym interfejsem | jest | `frontend/`, http://localhost:3000 |
| Opis metodyki | jest | [metodyka.md](metodyka.md) |
| Instrukcja instalacji, konfiguracji i uruchomienia z zależnościami | jest | [README.md](../README.md) |
| Kod w repozytorium Git | jest | GitHub: https://github.com/NikodemJachec99/deepfake-atlas, do tego archiwum kodu w zgłoszeniu |
| Środowisko skonteneryzowane | jest | `docker-compose.yml`, wszystkie usługi łącznie z interfejsem |
| Opis dostępu do usług wymagających autoryzacji | jest | [licencje.md](licencje.md): tylko Meta Ad Library, opcjonalna |
| Lista bibliotek, modeli i usług z licencjami i ograniczeniami | jest | [licencje.md](licencje.md) |

## Walidacja (pkt 6)

Organizator przetestuje rozwiązanie na nieudostępnionym zbiorze z nowymi wariantami znanych kampanii i z innymi kampaniami.

| Co sprawdzi | Jak się do tego mamy |
|---|---|
| Identyfikowanie podobnych materiałów i wariantów | 6 stron jednej kampanii na 5 domenach połączone |
| Przypisywanie nowych materiałów do istniejących grup | sprawy z drugiej paczki dołączyły do kampanii i operatora z pierwszej |
| Niełączenie tego, co nie powinno być połączone | 14 stron bez operatora; kopia treści na innym zapleczu i ten sam silnik lejka bez śladu operatora to tylko `similar`; każda krawędź między sprawami przejrzana ręcznie ([dane-organizatora.md](dane-organizatora.md)) |
| Przydatność i różnorodność cech | 7 rodzin |
| Odporność na duplikaty, niekompletne dane, różne formaty | duplikat oznaczony; obsługa zapisanych stron, HAR, `page-capture`, archiwum NASK, zrzutów, wideo; pomiar: bez HAR zostaje 18 z 32 połączeń, bez zapisu strony 30, bez zrzutów 32, w żadnym wariancie zero fałszywych połączeń ([dane-organizatora.md](dane-organizatora.md)) |
| Interpretowalność | dowody przy każdej krawędzi |
| Kompletność od wczytania do wyniku | `import_bundle` albo upload w interfejsie |

Nie mamy zbioru z oznaczonymi kampaniami, więc **nie podajemy liczbowej skuteczności**. Wyniki z dwóch paczek sprawdziliśmy ręcznie, przeglądając dowody.

## Czego organizator oczekuje poza demonstratorem (pkt 10)

| Oczekiwanie | Stan | Gdzie |
|---|---|---|
| Wzbogacony i uporządkowany zbiór danych | jest | `GET /api/export` (ZIP, `?source=capture` dla materiałów spraw) albo `manage.py export_corpus <katalog> [--source capture]`: reklamy z markerami (JSONL), krawędzie z dowodami (JSONL), przypisanie do kampanii i operatorów (CSV), tokeny tylko jako skróty; także przez API, Neo4j i OpenSearch |
| Opis zidentyfikowanych wzorców kampanii | jest | [dane-organizatora.md](dane-organizatora.md): silnik lejka z nagrywaniem sesji, cloaking, ślad językowy, pokrycie listą CERT |
| Metodyka łączenia cech | jest | [metodyka.md](metodyka.md) |
| Wskazanie użytecznych źródeł metadanych | jest | [metodyka.md](metodyka.md) pkt 10; które ślady rozstrzygały na danych organizatora: [dane-organizatora.md](dane-organizatora.md) |
| Rozpoznawanie nowych wariantów znanych kampanii | jest | ocena nowego materiału: `known_campaign`, `known_operator` |

## Zasady korzystania z danych (pkt 8)

| Zasada | Jak jej dotrzymujemy |
|---|---|
| Materiały organizatora tylko na potrzeby wyzwania | używane wyłącznie lokalnie do rozwoju i testów |
| Zakaz publicznego rozpowszechniania | `data/raw/` poza gitem; testy na zmyślonych wartościach; w repo tylko wyniki i domeny ze spraw w `docs/dane-organizatora.md` |
| Dodatkowe dane dozwolone po wskazaniu pochodzenia | źródła wymienione w [metodyka.md](metodyka.md) pkt 10 i [licencje.md](licencje.md) |

Do pilnowania:

- `docs/dane-organizatora.md` wymienia domeny ze spraw. Surowe materiały zostają poza gitem.
- Zrzuty ekranu aplikacji z danymi organizatora w prezentacji są pokazywane jury, nie publikowane.
- Druga paczka pochodzi z archiwum ukrytego w zagadce organizatora. Traktujemy ją tak samo jak pierwszą.

## Regulamin HackNation

| Punkt | Treść | Stan |
|---|---|---|
| 4.3 | rozwiązania przesyła się 21.11 11:00 do 22.11 11:00 | **do zrobienia przez zespół** |
| 4.6 | zespół do 6 osób | zespół dwuosobowy: Nikodem i Sokół |
| 5.6 | etap I: ocena zgłoszeń na platformie HackTribe, 5 najlepszych zespołów do etapu II; etap II: 5 minut prezentacji i 5 minut pytań | slajdy i scenariusz w [prezentacja.md](prezentacja.md), PDF generowany do `data/zgloszenie/prezentacja.pdf` (poza gitem, zawiera dane organizatora) |
| 5.9 | po terminie zakaz zmian w rozwiązaniu | po 22.11 11:00 nie ruszamy repo |
| 6.1, 6.2 | uczestnik oświadcza, że jest twórcą swojego wkładu i że rozwiązanie nie narusza praw osób trzecich | biblioteki na licencjach otwartych, lista w [licencje.md](licencje.md); użycie asystenta AI ujawnione tamże |
| 6.3 | regulamin konkursu może przewidywać przeniesienie praw do rozwiązania | regulamin zadania NASK §4 ust. 3 wymaga od zwycięzców zawarcia umowy przeniesienia praw do utworów wytworzonych w ramach zadania; §3 ust. 6–7 wiąże jej podpisanie z nagrodą. Wzór umowy jest w [regulaminie zadania](zrodla/regulamin-zadania.pdf), szczegóły niżej |

## Regulamin zadania "Kolekcjoner fejków"

Regulamin zadania ma pierwszeństwo przed regulaminem wydarzenia (§5 ust. 2). Przyrzekającym nagrodę i stroną umowy jest NASK-PIB.

| Punkt | Treść | Jak spełniamy |
|---|---|---|
| §1 ust. 5 | udział tylko osób fizycznych zarejestrowanych na HackNation 2026 | Nikodem i Sokół, oboje zarejestrowani |
| §2 | ocena jury według kryteriów z opisu zadania, decyzja ostateczna | kryteria i nasz stan: sekcja wyżej |
| §3 ust. 5 | nagroda pieniężna dzielona po równo między członków zespołu, chyba że wspólne oświadczenie mówi inaczej | sprawa zespołu, bez wpływu na kod |
| §3 ust. 6–7 | nagroda po podpisaniu umowy przeniesienia praw, na podpis 7 dni | sprawa zespołu po ogłoszeniu wyników |
| §4 ust. 1 | każdy uczestnik jest twórcą swojego wkładu i ma do niego pełne prawa majątkowe | kod pisał zespół z asystentem Claude Code (Anthropic), co jest ujawnione w [licencje.md](licencje.md); kodu z innych projektów nie kopiowaliśmy, poza bibliotekami jako zależnościami |
| §4 ust. 2, umowa §5 | rozwiązanie wolne od wad prawnych, bez naruszania praw osób trzecich, prawa nieobciążone | repozytorium **nie ma pliku licencji**: nie udzieliliśmy nikomu licencji (np. MIT), więc wyłączne prawa da się przenieść bez obciążeń. Zależności tylko na licencjach otwartych ([licencje.md](licencje.md)). Usługi na licencjach z warunkami (Neo4j GPL-3.0, ffmpeg LGPL/GPL) działają jako osobne procesy i nie są częścią naszego kodu. Redis (RSALv2/SSPLv1) usunięty 22.11, bo nie był używany. Modele: MIT (Whisper, CLIP), licencje modeli w licencje.md. Zdjęć osób w repo nie ma, są tylko wektory z plików Commons na wolnej licencji z autorem i licencją |
| §4 ust. 3–8 | zwycięzcy przenoszą autorskie prawa majątkowe na NASK-PIB (art. 74 ust. 4 i art. 50 ustawy), wszyscy współtwórcy podpisują wspólnie | kod, dokumentacja i skrypty są w jednym repozytorium; po przeniesieniu NASK-PIB może je zmieniać, łączyć i wdrażać bez naszej zgody (umowa §1 ust. 3–5) |
| umowa §1 ust. 1 pkt 4 | autor zamieszcza na platformie konkursowej kod źródłowy z dokumentacją w formie pozwalającej na jego wykorzystanie | zrobione: link do repozytorium w zgłoszeniu na HackTribe i archiwum kodu; instalacja jednym poleceniem `python scripts/start.py`, dokumentacja w `README.md` i `docs/` |
| umowa §6 ust. 3 | zgoda na korzystanie z utworu bez oznaczenia autorstwa | w kodzie i interfejsie nie ma wymaganych oznaczeń autorstwa |
| §5 ust. 5 | organizator może zmienić regulamin, informując mailem | przy zmianie podmieniamy PDF w `docs/zrodla/` i tę tabelę |

Zasady dla dalszej pracy są w `CLAUDE.md`, sekcja "Regulamin zadania".

Z przewodnika uczestnika i FAQ (strona hacknation.pl, odczyt 21.11):

- **Szkic projektu na HackTribe do 21.11 godz. 20:00**, z repozytorium i wstępnym opisem. Po tej godzinie nie da się utworzyć projektu ani zmienić zadania.
- **Zgłoszenie końcowe do 22.11 godz. 11:00**: wymagane pola, prezentacja i materiały pozwalające sprawdzić projekt. Zalecane krótkie demo, do 2 minut.
- Zasoby zewnętrzne i przygotowane wcześniej trzeba wymienić. Zrobione w [licencje.md](licencje.md).
- Wątpliwości co do użycia AI i wcześniej przygotowanego kodu trzeba wyjaśnić z organizatorem przed zgłoszeniem.

## Otwarte sprawy dla zespołu

1. Założyć szkic na HackTribe przed 20:00 i podpiąć repozytorium.
2. Link do repozytorium w zgłoszeniu i archiwum kodu.
3. Zapytać mentorów NASK o dwie rzeczy: zasady użycia asystenta AI do pisania kodu, warunki przeniesienia praw oraz dopuszczalność przekazania materiałów organizatora dostawcy API.
4. Przygotować prezentację na 5 minut i demo do 2 minut.
