> **Archiwum:** decyzją użytkownika basal zastępuje Jev. Aktualny kierunek i zadania są w [jev.md](jev.md), [planie laboratorium](laboratorium.md#jev-jako-pomoc-analityka) oraz [#116](https://github.com/NikodemJachec99/deepfake-atlas/issues/116). Poniższy dokument opisuje poprzedni wariant, nie instrukcję bieżącego wdrożenia.

# Basal: plan zastosowań, wersje i sprzęt

Plan do [#70](https://github.com/NikodemJachec99/deepfake-atlas/issues/70). Uzupełnia sekcję "Basal jako pomoc analityka" w [laboratorium.md](laboratorium.md) i niczego w niej nie zmienia. Stan na 21.11.2026.

## Co to jest i czego nie robi

basal to lokalny silnik "typowanych decyzji": dostaje stan (tekst albo JSON) i pytanie z listą dozwolonych odpowiedzi, a zwraca skalibrowany rozkład prawdopodobieństwa po tych odpowiedziach w jednym przebiegu modelu. Nie generuje tekstu, więc nie ma "uzasadnienia modelu" i nie wolno go pokazywać ani dopisywać.

U nas wynik basal jest wyłącznie doradczy:

- nie łączy i nie rozdziela kampanii ani operatorów, nie zmienia krawędzi, wag, dowodów ani werdyktów,
- nie jest dowodem, wykryciem oszustwa ani oceną winy, a jego prawdopodobieństwo nie jest prawdopodobieństwem winy,
- nie zastępuje silnika dowodowego (`similarity/fusion.py`) w analizie, w Laboratorium dowodów ([#48](https://github.com/NikodemJachec99/deepfake-atlas/issues/48)) ani w teście najsłabszego ogniwa ([#56](https://github.com/NikodemJachec99/deepfake-atlas/issues/56)),
- modele omni (obrazy, audio) są u twórcy eksperymentalne. Nie używamy ich i nie przypisujemy im wykrywania deepfake.

## Źródła, wersje i licencje

Wersje silnika, wag i kwantyzacji to osobne rzeczy. Każdą przypinamy osobno.

| Element | Wersja | Rewizja | Licencja |
|---|---|---|---|
| Silnik basal | 2.8.1, wydany 15.11.2026 | tag `466ae93`, commit `50ce7997520b` | Apache-2.0 ([LICENSE](https://github.com/rkinas/basal/blob/v2.8.1/LICENSE), [NOTICE](https://github.com/rkinas/basal/blob/v2.8.1/NOTICE)) |
| `Remek/basal-2.0-mini` (1,5B, bf16) | rodzina basal-2.0 | HF `1fb226f19c9b` | Apache-2.0, baza `speakleash/Bielik-1.5B-v3.0-Instruct` (Apache-2.0) |
| `Remek/basal-2.0-mini-GGUF` | Q8_0, Q5_K_M | HF `b6b79ac00da3` | jak wyżej |
| `Remek/basal-2.0-4.5B` (bf16) | rodzina basal-2.0 | HF `42ca9c578278` | Apache-2.0, baza `speakleash/Bielik-4.5B-v3.0-Instruct` (Apache-2.0) |
| `Remek/basal-2.0-4.5B-FP8` | FP8 (ModelOpt) | HF `4ef8cf272df9` | jak wyżej |
| `Remek/basal-2.0-4.5B-GGUF` | Q8_0, Q5_K_M | HF `c8996b389cd7` | jak wyżej |
| `Remek/basal-2.0-4.5B-MLX-8bit`, `-mini-MLX-8bit` | MLX 8-bit | HF `66646fecddf2`, `15d68296c4e3` | jak wyżej |

Źródła: [repozytorium](https://github.com/rkinas/basal), [wydanie 2.8.1](https://github.com/rkinas/basal/releases/tag/v2.8.1), [API](https://github.com/rkinas/basal/blob/v2.8.1/docs/API.md), [kalibracja](https://github.com/rkinas/basal/blob/v2.8.1/docs/CALIBRATION.md), [sprzęt](https://github.com/rkinas/basal/blob/v2.8.1/docs/HARDWARE.md), [strona](https://basal.si5.pl/). Rewizje HF odczytane z `huggingface.co/api/models` 21.11.2026. Przy wdrożeniu uruchamiamy model po rewizji, nie po nazwie, i zapisujemy `revision` i `model_files`, które zwraca `GET /v1/models`.

Wydanie 2.8.1 poprawia jedno: wersja 2.8.0 ładowała checkpointy `-FP8` w trybach `eager` i `mps` bez skal i bez błędu zwracała złe odpowiedzi. Każdy pomiar na FP8 robimy więc na 2.8.1 albo nowszym, w trybie `fast` lub `vllm`.

Wyniki twórcy (np. Werdykt) dotyczą jego zbiorów. Nie są miarą skuteczności dla NASK i nie cytujemy ich jako takiej.

## Sprzęt

| Komputer | Sprzęt | Co ma sens |
|---|---|---|
| główny, Windows 11 | RTX 4070 Laptop, 8 GB VRAM, compute capability 8.9; i9-13900HX; 64 GB RAM; ok. 320 GB wolnego na D: | patrz niżej |
| koder, MacBook | Apple Silicon (MLX) | według zasad repo koder nie uruchamia modeli, więc tylko informacyjnie |

Budżet pamięci na głównym, z rozmiarów plików wag:

| Wariant | Wagi | Na 8 GB VRAM | Uwagi |
|---|---|---|---|
| basal-2.0-4.5B bf16 | 9,51 GB | nie mieści się | — |
| basal-2.0-4.5B-FP8, `--mode fast` | 5,2 GB | możliwe | FP8 wymaga sm89+, a ta karta ma 8.9. Tryb `fast` kompiluje jądra CUDA; na natywnym Windowsie twórca opisuje pomiar tylko dla basal-omni-pico na SM120, więc najpewniej przez Docker z GPU w WSL2 |
| basal-2.0-4.5B-GGUF Q8_0 | 5,06 GB | możliwe przez llama.cpp | ścieżka GGUF ma własną kalibrację (`CALIBRATION.ollama.json` u twórcy) |
| basal-2.0-mini bf16, `--mode eager` | 3,19 GB | tak | kontekst 8 192 tokenów, wg twórcy słabsza od basal-1.5-mini na polskich decyzjach |
| basal-2.0-mini-GGUF Q8_0 na CPU | 1,7 GB | bez GPU | wariant awaryjny |

**Pomiar 21.11.2026 na tym komputerze**, basal 2.8.1, torch 2.11.0+cu128, Windows 11: basal-2.0-mini bf16 (rewizja `1fb226f`, `model_files` `768ccc5231d6e363`) w `--mode eager` wstaje w 63 s i zajmuje 3,4 GB VRAM. Na 44 krawędziach z kopii bazy po imporcie paczek pytanie `edge-review-v1` trwa 62 ms w medianie, 765 ms najdłużej. Model odpowiedział `przeglad` dla wszystkich 44, także dla 19 krawędzi `same_campaign` z kilkoma niezależnymi grupami śladów, więc w tej postaci nic nie rozróżnia. To wynik dla jednego modelu i jednego sformułowania pytania. Pozostałych wariantów (4.5B-FP8, GGUF) nie mierzyłem. Wiersze "możliwe" wyżej to wnioski z rozmiarów i dokumentacji. Kolejność prób w [#71](https://github.com/NikodemJachec99/deepfake-atlas/issues/71): (1) basal-2.0-4.5B-FP8 w `--mode fast` w kontenerze Linux z GPU, (2) basal-2.0-mini bf16 w `--mode eager` na Windowsie, (3) basal-2.0-mini-GGUF Q8_0 na CPU. Wybieramy wariant, który się uruchamia i ma najwyższą zgodność na naszym zbiorze walidacyjnym z [#72](https://github.com/NikodemJachec99/deepfake-atlas/issues/72), przy opóźnieniu poniżej 2 s na decyzję.

## Zastosowania

### 1. Czy krawędź wymaga przeglądu człowieka (scenariusz MVP)

Najprostsze i najlepiej sprawdzalne: pytanie zamknięte o istniejącą krawędź, ze strukturą przesłanek, którą już mamy.

- Stan: JSON z pól policzonych przez silnik: relacja, bity, pewność, `decisive`, `duplicate`, bity per rodzina, grupy śladów z [#56](https://github.com/NikodemJachec99/deepfake-atlas/issues/56) (`kit`, `motif`, `infra`, `content`, `creative`, `template`, `kind:<typ>`) z liczbą i wkładem, liczba niezależnych rodzin, wersja modelu. Bez wartości śladów, adresów, tekstu stron i reklam.
- Pytanie `choice` z dwiema odpowiedziami: `przeglad` ("przesłanki są niepełne albo pochodzą z jednej przyczyny, potrzebna ocena człowieka") i `spojne` ("przesłanki są niezależne i spójne z relacją").
- `max_error` z progiem dopasowanym na naszej walidacji (`basal-calibrate`), bo progi z pliku modelu są dopasowane do danych twórcy. Poniżej progu odpowiedź to "wstrzymane", a nie "spójne".
- Punkt odniesienia: reguła bez modelu, np. "tylko ślady silnika lejka albo tylko motywy" → przegląd. Model ma sens tylko wtedy, gdy na walidacji robi coś lepiej niż ta reguła.

### 2. Kolejność precedensów pamięci sprzeciwu (po osobnej ocenie)

Kandydatów wybiera deterministycznie [#68](https://github.com/NikodemJachec99/deepfake-atlas/issues/68). Model może je tylko przestawić typem pytania `rank` albo `choice` na stanie złożonym z grup śladów obu stron. Nie dodaje kandydatów, nie usuwa ich i nie zmienia opisu różnic. Bez potwierdzonej poprawy kolejność zostaje regułowa.

### 3. Etykiety narracji dla analityka (opcjonalnie, osobna ocena)

Np. tematyka tekstu reklamy z zamkniętej listy. Tekst reklamy jest niezaufany: limit długości, bez wykonywania instrukcji, bez danych osobowych. Osobny zbiór i osobna ocena. Poza MVP.

## Architektura

- Usługa `basal-serve` działa lokalnie, nasłuchuje tylko na `127.0.0.1` albo w sieci compose bez publikowania portu, z `--api-keys`. Nigdy nie jest wystawiona publicznie.
- Backend ma adapter `POST /v1/systemone` w osobnym module. Adres w `BASAL_URL`, pusty oznacza wyłączony. Do tego jawnie przypięte: model, rewizja, wariant, tryb, wersja pytania.
- Wyniki trafiają do osobnej tabeli sugestii: model, rewizja, kwantyzacja, wersja pytania i opcji, data, skrót SHA-256 stanu, rozkład odpowiedzi, status (`ok`, `abstain`, `disabled`, `unavailable`, `error`, `timeout`). Nic nie trafia do `EdgeEvidence`, grup ani decyzji analityka.
- Tryby: wyłączony (domyślnie), `shadow` (liczy i zapisuje, interfejs nie pokazuje), `on` (interfejs pokazuje z etykietą "sugestia modelu"). Limit czasu, rozmiaru stanu i liczby zapytań. Brak modelu albo błąd nie przerywa analizy.
- Interfejs pokazuje obok sugestii tylko rzeczywiste przesłanki: dowody, reguły i zapisane decyzje. Żadnego generowanego tekstu.

## Uruchomienie adaptera ([#71](https://github.com/NikodemJachec99/deepfake-atlas/issues/71))

Silnik i wagi nie są częścią repozytorium ani obrazów kontenerów. Instalacja w osobnym środowisku, poza repo:

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv/Scripts/python.exe torch==2.11.0 --index-url https://download.pytorch.org/whl/cu128
uv pip install --python .venv/Scripts/python.exe "basal @ https://github.com/rkinas/basal/archive/refs/tags/v2.8.1.tar.gz"
.venv/Scripts/basal-serve --model Remek/basal-2.0-mini --revision 1fb226f19c9ba9f2053991081e6c4dfc7890de64     --mode eager --host 127.0.0.1 --port 8090
```

Backend (zmienne w `.env`, wszystkie domyślnie puste albo `off`):

| Zmienna | Znaczenie |
|---|---|
| `BASAL_MODE` | `off` (domyślnie), `shadow` (zapisuje, interfejs nie pokazuje), `on` |
| `BASAL_URL` | np. `http://127.0.0.1:8090`; z kontenera `http://host.docker.internal:8090` |
| `BASAL_MODEL`, `BASAL_REVISION`, `BASAL_VARIANT` | przypięty model, rewizja HF i wariant (np. `eager-bf16`); bez `BASAL_MODEL` adapter się nie uruchomi |
| `BASAL_API_KEY` | klucz, gdy serwer działa z `--api-keys` (wysyłany jako `Authorization: Bearer`) |
| `BASAL_TIMEOUT` | sekundy na jedną decyzję, domyślnie 20 |
| `BASAL_MAX_ERROR` | np. `0.05`: poniżej progu model się wstrzymuje; pusty: bez wstrzymywania |
| `BASAL_ALLOWED_HOSTS` | hosty, do których adapter w ogóle wyśle zapytanie; domyślnie tylko lokalne i `basal` |

`python manage.py basal_review [--edge N] [--relation same_operator] [--limit 100]` zapisuje sugestie do `AssistSuggestion` ze statusem `ok`, `abstain`, `unavailable`, `timeout` albo `error`. Po trzech zapytaniach bez odpowiedzi przerywa. Niepoprawna odpowiedź (odpowiedź spoza listy, rozkład spoza zakresu, przekierowanie, za duża treść) jest błędem, nigdy zgadywanym wynikiem. Pytanie ma wersję `edge-review-v1`, stan jego skrót SHA-256.

## Prywatność

- Do modelu idzie tylko stan zbudowany z pól policzonych przez silnik. Bez HAR, HTML, adresów, tokenów, kontaktów, nazwisk, tekstu stron i reklam (z wyjątkiem zastosowania 3, po osobnej decyzji).
- Model działa lokalnie. Danych organizatora nie wysyłamy do żadnej usługi zewnętrznej.
- Zapisujemy skrót stanu, nie sam stan, chyba że to dane syntetyczne do testów.

## Ewaluacja ([#72](https://github.com/NikodemJachec99/deepfake-atlas/issues/72))

- Etykiety: decyzje analityka z powodem z pamięci sprzeciwu ([#67](https://github.com/NikodemJachec99/deepfake-atlas/issues/67)) oraz krawędzie ocenione w przeglądzie z [dane-organizatora.md](dane-organizatora.md). Każda etykieta ma źródło i datę.
- Podział po operatorach i kampaniach, a duplikaty (np. sprawy p1 i p2) zawsze po jednej stronie podziału, żeby uniknąć przecieku.
- Porównanie: reguła bez modelu i basal. Precision i recall dla obu klas, pokrycie (ile decyzji model podejmuje przy danym `max_error`), kalibracja, opóźnienie, pamięć.
- Progi ustawiamy na walidacji, nie na teście. Wynik zależy od modelu, portu, kwantyzacji i treści pytania, więc zapisujemy wszystkie.
- Na danych organizatora krawędzi jest kilkadziesiąt. Taki zbiór daje wynik wstępny, bez twierdzeń o jakości. Do tego przypadki trudne: sprzeczne przesłanki, braki danych, warianty tekstu i wstrzyknięte instrukcje w treści.

## Zadania wdrożenia

| Zadanie | Co | Zależy od |
|---|---|---|
| [#71](https://github.com/NikodemJachec99/deepfake-atlas/issues/71) | adapter `POST /v1/systemone`, tabela sugestii, tryby `off` / `shadow` / `on`, testy na symulowanym serwisie | ten plan |
| [#72](https://github.com/NikodemJachec99/deepfake-atlas/issues/72) | uruchomienie wybranego wariantu i ewaluacja według planu wyżej | #71 i uruchomiony model |
| [#73](https://github.com/NikodemJachec99/deepfake-atlas/issues/73) | sugestia przeglądu w API, ewentualnie kolejność precedensów | #72, #68 |
| [#74](https://github.com/NikodemJachec99/deepfake-atlas/issues/74) | panel analityka | #73 |
| [#75](https://github.com/NikodemJachec99/deepfake-atlas/issues/75) | scenariusz demo z planem awaryjnym bez modelu | #69, #74 |

Bez uruchomionego modelu #72 i dalsze zadania nie mają podstaw do pokazania wyniku. Demo pokazuje wtedy pamięć sprzeciwu i precedensy bez sugestii modelu.
