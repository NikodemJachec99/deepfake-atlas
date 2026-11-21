# Laboratorium dowodów i odporność hipotez

Analityk widzi hipotezę połączenia (krawędź), jej dowody i ich pochodzenie. Może na próbę wyłączyć wybrane ślady i zobaczyć, czy połączenie się utrzymuje, bez zmiany prawdziwej sprawy. Drugi kierunek to oś obserwacji: fakty z dat przechwyceń i źródeł, nie domniemana historia przestępcy.

Stan na 2026-11-21.

## Zadania i kolejność

| Krok | Zadanie | Strefa | Priorytet | Stan |
|---|---|---|---|---|
| 1b | [#56](https://github.com/NikodemJachec99/deepfake-atlas/issues/56) test najsłabszego ogniwa | backend | p1 | w `main`: `POST /api/edges/{id}/weakest-link` |
| 1 | [#48](https://github.com/NikodemJachec99/deepfake-atlas/issues/48) czysta symulacja i kontrakt API | backend | p0 | w `main`: `POST /api/edges/{id}/simulate`, opis w [api.md](api.md) |
| 2 | [#49](https://github.com/NikodemJachec99/deepfake-atlas/issues/49) interaktywny panel co-jeśli w widoku powiązania | frontend | p0 | czeka na koder |
| 3 | [#50](https://github.com/NikodemJachec99/deepfake-atlas/issues/50) co sprawdzić dalej: wskazówki z brakujących dowodów | backend | p1 | w `main`: `GET /api/edges/{id}/suggestions` |
| 3 | [#51](https://github.com/NikodemJachec99/deepfake-atlas/issues/51) karta działań analityka | frontend | p1 | zależy od #50 |
| 4 | [#52](https://github.com/NikodemJachec99/deepfake-atlas/issues/52) walidacja i scenariusz demo laboratorium | docs | p1 | zależy od #48 i #49 |
| 5 | [#53](https://github.com/NikodemJachec99/deepfake-atlas/issues/53) oś obserwacji: ewolucja śladów kampanii | backend | p1 | opcjonalne, po MVP |
| 5 | [#54](https://github.com/NikodemJachec99/deepfake-atlas/issues/54) przewijanie rozwoju sprawy | frontend | p1 | zależy od #53 |

P0 to minimalny pionowy przepływ na demo: symulacja w API i panel w interfejsie. P1 dopiero wtedy, gdy zgłoszenie i niezawodność są zabezpieczone (termin 22.11 godz. 11:00).

## Zasady

- **Wynik to hipoteza analityczna.** Krawędź mówi, że dwa materiały mają wspólne źródło albo są podobne. Nie identyfikuje osoby i niczego nie zarzuca.
- **Symulacja niczego nie zapisuje** i nie wysyła zapytań na zewnątrz. Krawędź, decyzja analityka, dziennik audytu i grupy zostają bez zmian. Pilnuje tego test `test_simulation_has_no_side_effects`.
- **Brak danych nie jest dowodem braku powiązania.** Sprawa bez HAR nie ma śladów zaplecza, więc słabe połączenie może wynikać z braku materiału, a nie z różnych źródeł. Wskazówki z #50 mają to mówić wprost.
- **Bity to wkład w skali logarytmicznej, nie prawdopodobieństwo i nie procent.** Pewność krawędzi to osobne pole.
- **Kilka śladów jednego mechanizmu to jedno potwierdzenie.** Ścieżki zaplecza, zestaw parametrów i szablon ścieżki ustawia ten sam silnik lejka, więc symulacja liczy je razem (`independent: ["kit", ...]`), tak samo jak produkcyjny silnik.
- **Wpływ na grupę tylko tam, gdzie da się go policzyć dokładnie.** Symulacja sprawdza, czy obie reklamy łączy inna ścieżka z krawędzi tego samego rodzaju (bez odrzuconych). Nie przelicza innych par i nie twierdzi, że rozpadnie się cała grupa.
- **Pochodzenie i prywatność.** Każdy dowód wskazuje plik źródłowy (`artifact_a`, `artifact_b`). Dane organizatora zostają w prywatnym repo i w `data/raw/`.

## Co już widać na danych organizatora

Symulacja na krawędziach z obu paczek (model `fs-5`, odczyt z bazy, bez zapisu):

| Krawędź | Wyłączone | Wynik |
|---|---|---|
| backup/p3 do backup/p7 (operator A) | najsilniejszy identyfikator w panelu lejka, potem piksel Meta, potem ścieżka zaplecza | zostaje `same_operator` (56 → 36 bitów): para ma kilka identyfikatorów z panelu, więc hipoteza jest odporna |
| nask/2 (drugi HAR) do backup/p5 (operator B) | host zasobów `crimsonbase.pro` | spada do `similar` (30 → 21 bitów); obie reklamy nie łączą się inną ścieżką, więc grupa rozpadłaby się w tym miejscu |

Wniosek dla analityka: połączenie operatora B wisi na jednym śladzie. Warto go potwierdzić czymś niezależnym (np. HAR-em strony p5 z innego dnia), zanim się na nim oprze. To jest materiał na scenariusz z #52.

## Test najsłabszego ogniwa

`POST /api/edges/{id}/weakest-link` (#56) sam szuka, utrata których śladów zmieniłaby relację. Ślady są zgrupowane według przyczyny, żeby jedna przyczyna nie udawała kilku niezależnych dowodów:

| Grupa | Co zawiera | Dlaczego razem |
|---|---|---|
| `kit` | ścieżki zaplecza, zestaw parametrów, szablon ścieżki | ustawia je jeden silnik lejka |
| `motif` | wzmianka o osobie, twarz, podszycie pod markę, tematyka | wspólne motywy różnych operatorów |
| `infra` | domena, adres IP, certyfikat, serwery nazw, rejestracja | ta sama domena pociąga za sobą ten sam adres i certyfikat |
| `content` | tytuł, treść strony, tekst reklamy | kopiowane razem |
| `creative` | zrzut reklamy, plik kreacji, obrazy strony | kopiowane razem |
| `template` | struktura DOM strony i białej strony | jeden szablon |
| `kind:<typ>` | każdy inny typ, np. identyfikator w panelu lejka, piksel, konto Google Ads | osobne konta i ślady; kilka wartości tego samego typu to jedna grupa |

Przeszukiwanie jest wyczerpujące: wszystkie pojedyncze grupy, potem wszystkie pary, do limitu 500 scenariuszy i 3 sekund (oba do zmiany w żądaniu). **Minimalność** znaczy tyle: nie ma mniejszego zestawu grup w sprawdzonym zakresie, a przeszukiwanie się skończyło. Nie mówi nic o koszcie ani prawdopodobieństwie, że ktoś te ślady usunie.

Na danych organizatora (odczyt z bazy):

| Krawędź | Najmniejszy zestaw | Zmiana |
|---|---|---|
| nask/2 (drugi HAR) do backup/p5, operator B | 1 grupa: host zasobów albo ślady silnika (2 rozwiązania) | ten sam operator → podobna koncepcja |
| nask/1 do nask/2, kampania A | 2 grupy: treść i obrazy | ta sama kampania → ten sam operator |
| backup/p3 do backup/p7, operator A | nie znaleziono wśród pojedynczych grup i par (21 scenariuszy) | relacja się utrzymuje |

## Scenariusz pokazu laboratorium (#52)

**Dane i wersja.** Obie paczki organizatora zaimportowane od nowa 2026-11-21 (import 16:26 UTC), model `fs-5`, kod `main` po #63. Identyfikatory krawędzi zmieniają się przy każdym imporcie, więc krawędzie wskazujemy po sprawach. Aktualne id: `GET /api/ads/{id}/edges` dla reklamy ze sprawy 2.

**Czas.** Ok. 40 sekund na oba kroki.

| Krok | Co robimy | Oczekiwane | Zaobserwowane 2026-11-21 |
|---|---|---|---|
| 1 | Investigation, reklama sprawy 2 (`acrosscommunities.live`), krawędź do sprawy 1, "Laboratorium dowodów" | lista dowodów z polami wyboru, napis "Symulacja bez zapisu" | tak; krawędź "ta sama kampania", 78,5 bitu, 43 dowody |
| 2 | "Sprawdź najsłabszy punkt" | najmniejszy zestaw ma 2 grupy: treść strony i kreacja | tak: "2 grupy śladów, 45 scenariuszy, przeszukano cały zakres" |
| 3 | rozwinąć "Scenariusz 1", "Otwórz w ręcznej symulacji" | ta sama kampania → ten sam operator; zostają ślady silnika i trackingu | tak; powód: "za mało zgodnej opowieści (0 bitów z wymaganych 4)" |
| 4 | dla kontrastu: odznaczyć tylko treść strony | relacja zostaje ("ta sama kampania"), bo obrazy nadal potwierdzają opowieść | API: 68,7 bitu, "ta sama kampania", krawędź nadal spina grupę |
| 5 | krawędź operatora B: drugi HAR sprawy 2 (`healthlinkq.pro`) do sprawy p5, "Sprawdź najsłabszy punkt" | 1 grupa wystarcza: host zasobów albo ślady silnika | tak, 2 rozwiązania po 1 grupie; bez hosta "podobna koncepcja", a grupa rozpadłaby się w tym miejscu (brak innej ścieżki) |
| 6 | "Przywróć wszystkie dowody", pasek stanu | nic się nie zmieniło | pasek: 28 reklam, 4 kampanie, 3 operatorów; w bazie 0 decyzji, 0 wpisów audytu, `updated_at` krawędzi sprzed pokazu |

**Co mówimy.** "System sam wskazuje, na czym trzyma się hipoteza. Kampania A ma zapas: trzeba stracić i treść, i obrazy, żeby zostało tylko wspólne zaplecze. Operator B trzyma się na jednym hoście zasobów, więc zanim ktoś na nim oprze decyzję, warto zdobyć drugi ślad." Nie mówimy "odporna w X procentach", "dowód tożsamości" ani "grupa się rozpadnie": symulacja liczy jedną parę, a wpływ na grupę tylko jako brak innej ścieżki.

**Ścieżka alternatywna.** Dla kampanii A krawędź nadal spina grupę po każdym pojedynczym wyłączeniu. Dla operatora B obie reklamy nie mają innej ścieżki w grafie, co pokazuje `group_impact.operator.pair_still_connected: false`.

**Plan awaryjny.** Gdy interfejs nie działa:

```bash
curl -s localhost:8000/api/ads/<id reklamy sprawy 2>/edges          # id krawędzi do sprawy 1
curl -s -X POST localhost:8000/api/edges/<id>/weakest-link -H "Content-Type: application/json" -d '{}'
curl -s -X POST localhost:8000/api/edges/<id>/simulate -H "Content-Type: application/json" -d '{"exclude":[<excluded_evidence z wyniku>]}'
```

**Ograniczenia.** Symulacja korzysta z dowodów zapisanych przy krawędzi i rzadkości z chwili importu. Grupy śladów to reguły metodyki, nie wyuczony model. Przy krawędzi policzonej starszym modelem odpowiedź ostrzega o różnicy.

## Relacja do prezentacji i demo

Główne demo z [prezentacja.md](prezentacja.md) (#15) zostaje bez zmian: nowa sprawa dołącza do znanego operatora. Laboratorium wchodzi jako dodatek, gdy panel z #49 będzie w `main`: na krawędzi operatora B wyłączamy host zasobów i pokazujemy, że system sam mówi, które połączenie jest kruche. Scenariusz z czasami i planem awaryjnym przygotowuje #52.

## Ograniczenia

- Symulacja pracuje na dowodach zapisanych przy krawędzi. Marker o zerowym wkładzie nie jest zapisywany, więc nie da się go wyłączyć (i niczego by to nie zmieniło).
- Rzadkość (`df`) zostaje z chwili liczenia krawędzi. Symulacja nie przelicza korpusu.
- Gdy krawędź policzono starszą wersją modelu, wynik bazowy jest przeliczany bieżącą i odpowiedź zawiera ostrzeżenie.
- Oś obserwacji (#53) zależy od dat w źródłach. Przechwycenia z paczek często nie mają daty, a pierwsza obserwacja to nie początek kampanii.

## Pamięć sprzeciwu

Decyzję analityka można uzasadnić wybranym powodem i notatką. System zachowuje historię oraz migawkę przesłanek z chwili decyzji: bieżące dowody krawędzi mogą się zmienić przy jej ponownym przeliczeniu. Przy kolejnej sprawie pokaże podobne wcześniejsze rozstrzygnięcia, powód podobieństwa i istotne różnice. Precedens jest kontekstem do oceny, nie automatycznym werdyktem; sam nie zmienia wag ani grup.

Kolejność: [#67 historia i migawka](https://github.com/NikodemJachec99/deepfake-atlas/issues/67) → [#68 wyszukiwanie precedensów](https://github.com/NikodemJachec99/deepfake-atlas/issues/68) → [#69 panel analityka](https://github.com/NikodemJachec99/deepfake-atlas/issues/69). Stare decyzje bez zapisanego powodu pozostają oznaczone jako nieznane. Notatki i źródła wymagają ochrony oraz redakcji; obecne API nie ma uwierzytelniania.

## Basal jako pomoc analityka

[Basal](https://github.com/rkinas/basal) przyjmuje kontekst, pytanie i listę odpowiedzi; zwraca typowaną decyzję, nie generuje uzasadnienia. W planie wykorzystujemy go do wskazywania istniejących powiązań do przeglądu oraz, po osobnej ocenie, porządkowania kandydatów precedensów. Ewentualne klasyfikowanie narracji wymaga osobnej walidacji. Wyjaśnienia w interfejsie muszą pochodzić z rzeczywistych danych i reguł.

Kolejność: [#70 plan i wybór modelu](https://github.com/NikodemJachec99/deepfake-atlas/issues/70) → [#71 opcjonalny lokalny adapter](https://github.com/NikodemJachec99/deepfake-atlas/issues/71) → [#72 ocena na danych projektu](https://github.com/NikodemJachec99/deepfake-atlas/issues/72) → [#73 API sugestii](https://github.com/NikodemJachec99/deepfake-atlas/issues/73) → [#74 panel analityka](https://github.com/NikodemJachec99/deepfake-atlas/issues/74). Sugestie precedensów zależą również od #68. Wspólny [scenariusz demo #75](https://github.com/NikodemJachec99/deepfake-atlas/issues/75) zależy od gotowości interfejsu i oceny.

Model jest opcjonalny, lokalny i domyślnie wyłączony; awaria nie przerywa analizy. Przekazujemy minimalne, zredagowane dane, traktując treści stron jako nieufne. Wynik modelu jest sugestią, nie dowodem ani podstawą automatycznego przypisania operatora. Nie zastępuje modelu dowodowego w analizie lub symulacji. Zapisujemy wersję modelu, pytania i wariantu uruchomienia; nie interpretujemy jego wyniku jako prawdopodobieństwa winy. Jakość i progi wymagają własnej oceny na oddzielonych sprawach, bez przecieku duplikatów.

Na 21.11.2026 najnowsze wydanie silnika to [basal 2.8.1](https://github.com/rkinas/basal/releases/tag/v2.8.1), a rodzina tekstowych wag to basal-2.0. Wybór konkretnego modelu i wariantu na podstawie pomiarów, wersje oraz licencje są przedmiotem #70; możliwości eksperymentalnego wariantu multimodalnego nie oznaczają wykrywania deepfake. Dokumentacja: [API basal](https://github.com/rkinas/basal/blob/main/docs/API.md) i [kalibracja](https://github.com/rkinas/basal/blob/main/docs/CALIBRATION.md). Plan z wersjami, licencjami, budżetem sprzętu i ewaluacją: [basal.md](basal.md).
