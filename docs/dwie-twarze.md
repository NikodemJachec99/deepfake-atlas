# Dwie twarze jednego linku: audyt przechwyceń sprawy 61

Audyt do zadania #61, stan na 2026-11-21. Materiały organizatora leżą w `data/raw/` i nie trafiają do gita. Ten plik opisuje tylko to, co z nich wynika.

## Co jest w sprawie 61

| Plik | Co to jest |
|---|---|
| `reklama_1.png` | zrzut reklamy w kanale (reklamodawca "Glowpixel"). To reklama, nie strona docelowa. |
| `strona_1/` | zapis HTML artykułu "37 minut po emisji..." i plik HAR nazwany samym `.har` |
| `strona_2/` | zapis HTML "Trwały Działunek" (oferta) i `trwaly_dzialunek.har` |
| `strona_3/` | zapis HTML "Glowpixel.org — Portal analiz produkcji medialnej..." i `glowpixel.org.har` |

## Macierz obserwacji

| | strona_2 (oferta) | strona_3 ("portal analiz") | strona_1 (artykuł) |
|---|---|---|---|
| Adres | pełny adres z komentarza `saved from url` i z pierwszego żądania HAR | **identyczny pełny adres**, łącznie z wartością `utm_visit` | brak: zapis z `about:internet`, HAR pochodzi z otwarcia lokalnego pliku (`file://`) |
| Typ dopasowania adresu | dokładny | dokładny | nie do ustalenia |
| Czas przechwycenia | 2026-10-20 12:03:42 UTC | 2026-10-20 12:06:23 UTC, 2 min 41 s później | 2026-10-20 11:55:07 UTC, ale to czas otwarcia pliku z dysku |
| Źródło czasu | `log.pages[].startedDateTime` w HAR | jak obok | jak obok, nie dotyczy strony w sieci |
| Przeglądarka | Microsoft Edge 155, Windows, desktop | Google Chrome 155, Windows, desktop | nieistotne (plik lokalny) |
| `Accept-Language` | `pl,en;q=0.9,en-GB;...` | `pl-PL,pl;q=0.9,en-US;...` | |
| Ciasteczka, referer | brak, brak | brak, brak | |
| Odpowiedź serwera | 200, Cloudflare, ok. 109 KB HTML | 200, Cloudflare, ten sam adres IP, ok. 88 KB HTML | |
| Hosty w HAR | domena strony, Google Ads (konwersja na koncie 18463917747), Google Tag Manager, jsDelivr, open.er-api.com | domena strony i Google Fonts | Google Tag Manager i Google Ads |
| Tekst i obrazy | zapis HTML z katalogiem `_files` | zapis HTML z katalogiem `_files` | zapis HTML z katalogiem `_files` |
| Zrzut strony | brak | brak | brak |
| Kontekst odbiorcy (moderator, ofiara) | nieznany | nieznany | nieznany |

## Czego da się dowieść

- Ten sam pełny adres, z tym samym tokenem wizyty, w odstępie 161 sekund zwrócił dwa różne dokumenty: stronę oferty z pikselem konwersji Google Ads i neutralny "portal analiz" bez żadnych trackerów.
- Oba żądania szły bez ciasteczek i bez referera, z dwóch różnych przeglądarek na Windows.
- Strony 1 i 2 łączy to samo konto Google Ads i ta sama reklama (`reklama_1.png`), co silnik już wykorzystuje.

## Czego nie da się dowieść

- **Że strona 3 jest "dla moderacji", a strona 2 "dla ofiary".** Nie znamy adresów IP, z których przechwytywano, ani tego, kto przechwytywał. Oba przechwycenia wyglądają na zrobione ręcznie z jednego komputera.
- **Że to cloaking według odbiorcy.** Inne wyjaśnienia pasują do danych równie dobrze:
  - jednorazowy token: pierwsza wizyta z danym `utm_visit` dostaje ofertę, każda kolejna białą stronę,
  - odcisk przeglądarki: Edge i Chrome różnią się nagłówkami `sec-ch-ua` i `Accept-Language`,
  - zmiana w czasie: operator przełączył stronę między 12:03 a 12:06,
  - losowy podział ruchu.
- **Niczego o adresie strony 1.** To kopia otwarta z dysku. Zrzut reklamy też nie jest zrzutem strony docelowej.

Poprawne sformułowanie: "ten sam adres dał dwie różne strony; najprostsze wyjaśnienia to cloaking albo jednorazowy token wizyty". Tak też poprawiliśmy [dane-organizatora.md](dane-organizatora.md) i [prezentacja.md](prezentacja.md).

## Jak importer to dziś traktuje

| Sprawa | Stan | Skutek |
|---|---|---|
| strona_2 i strona_3 w osobnych podkatalogach | dwie osobne reklamy (`strona-2-glowpixel.org`, `strona-3-glowpixel.org`) | oba warianty zachowane |
| plik `strona_1/.har` | pomijany: dla nazwy `.har` Python nie widzi rozszerzenia | strata niewielka (HAR z pliku lokalnego), ale reguła jest krucha |
| dwa przechwycenia tej samej domeny w **jednym** katalogu | łączone w jedną stronę po domenie; drugi HAR i drugi HTML nadpisują pierwsze | **gubi warianty**; dotyczy tylko innego ułożenia plików niż w sprawie 61 |
| kontekst przechwycenia (przeglądarka, język, ciasteczka, referer) | nie zapisywany | porównanie wymaga powrotu do surowego HAR |
| czas przechwycenia | zapisywany jako `first_seen` z HAR, archiwum NASK albo `page-capture` | bez informacji, z którego z tych źródeł |

## Propozycja dla #62 (bez niszczenia danych)

1. Plik o nazwie `.har` (albo `*.har` bez rdzenia) traktować jak HAR.
2. W jednym katalogu dwa przechwycenia tej samej domeny łączyć tylko wtedy, gdy mają ten sam pełny adres i czas w granicach minuty. W pozostałych przypadkach zostawiać osobne strony (`domena`, `domena-2`).
3. Przy każdej stronie zapisywać w `Ad.raw["observation"]` (pole JSON, bez migracji): adres dokładny po redakcji sekretów, adres znormalizowany (bez kolejności parametrów, z zachowaniem wszystkich wartości), domenę, czas przechwycenia i jego źródło (`har.pages`, `har.entries`, `nask.archive_info`, `page-capture.manifest`, brak), kontekst: rodzinę przeglądarki z `sec-ch-ua`, `Accept-Language`, czy były ciasteczka i referer, oraz listę hostów. Brak pola oznacza "nieznane", nie "brak".
4. Istniejące reklamy zostają. Nowe pola dochodzą przy ponownym imporcie, a kod porównania (#62, #63) zwraca "brak danych", gdy ich nie ma.
5. Porównanie nie zmienia krawędzi ani grup. Różnica stron pod tym samym adresem to obserwacja, nie nowy dowód wspólnego operatora.

## Co już działa (#62)

- Importer czyta plik nazwany samym `.har`, pomija HAR nagrany z pliku lokalnego (`file:`) i nie skleja dwóch przechwyceń tej samej domeny z różnymi adresami albo dwóch HAR-ów w jednym katalogu. Archiwum NASK i `page-capture` dalej uzupełniają zapis tej samej domeny. Na danych organizatora liczba stron bez zmian (28).
- Każda strona z przechwycenia ma `Ad.raw["observation"]`: adres dokładny po redakcji sekretów, adres znormalizowany, domenę, czas przechwycenia i jego źródło (`har.entries`, `nask.archive_info`, `page-capture.manifest`, puste = nieznane), kontekst przeglądarki z nagłówków żądania (rodzina, platforma, mobilna, język, czy były ciasteczka i referer, bez wartości ciasteczek) i listę hostów z ruchu.
- `similarity/observations.py` porównuje dwie strony: typ zgodności adresu (`exact`, `normalized`, `domain`, `different`, `unknown`), odstęp czasu, podobieństwo treści, szablonu i obrazów z istniejących sygnatur, różnice trackerów, hostów i kontekstu, ocena oraz hipotezy i ograniczenia. Krawędzi nie zmienia.

Progi oceny: treść i szablon co najmniej 0,9 to "identyczne albo prawie identyczne", treść co najmniej 0,5 albo szablon co najmniej 0,6 to "podobne", niżej "istotnie różne", bez sygnatur "za mało danych". To opis skali, nie wykalibrowana pewność. Hipotezy (cloaking, jednorazowy token, kontekst przeglądarki, zmiana w czasie) pojawiają się tylko przy zgodnym adresie i różnej treści.

Starsze importy nie mają `observation`. Porównanie mówi wtedy wprost, czego brakuje. Pełne dane daje ponowny import.

## Materiał do pokazu

Rzeczywisty przykład jest: strony 2 i 3 sprawy 61 spełniają warunek identycznego pełnego adresu. Syntetyczny materiał nie jest potrzebny. Do testów automatycznych używamy zmyślonych domen i tokenów.
