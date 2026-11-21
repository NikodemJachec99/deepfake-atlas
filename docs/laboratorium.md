# Laboratorium dowodów i odporność hipotez

Analityk widzi hipotezę połączenia (krawędź), jej dowody i ich pochodzenie. Może na próbę wyłączyć wybrane ślady i zobaczyć, czy połączenie się utrzymuje, bez zmiany prawdziwej sprawy. Drugi kierunek to oś obserwacji: fakty z dat przechwyceń i źródeł, nie domniemana historia przestępcy.

Stan na 2026-11-21.

## Zadania i kolejność

| Krok | Zadanie | Strefa | Priorytet | Stan |
|---|---|---|---|---|
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

Na 21.11.2026 najnowsze wydanie silnika to [basal 2.8.1](https://github.com/rkinas/basal/releases/tag/v2.8.1), a rodzina tekstowych wag to basal-2.0. Wybór konkretnego modelu i wariantu na podstawie pomiarów, wersje oraz licencje są przedmiotem #70; możliwości eksperymentalnego wariantu multimodalnego nie oznaczają wykrywania deepfake. Dokumentacja: [API basal](https://github.com/rkinas/basal/blob/main/docs/API.md) i [kalibracja](https://github.com/rkinas/basal/blob/main/docs/CALIBRATION.md).
