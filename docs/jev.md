# Jev: zewnętrzny model decyzyjny

Opcjonalny adapter usługi [Jev](https://docs.typesafe.ai/introduction) od TypeSafe ([#116](https://github.com/NikodemJachec99/deepfake-atlas/issues/116)). Zastępuje lokalny basal, którego plan i pomiar zostały w [basal.md](basal.md) jako archiwum. Kierunek i zasady są w [laboratorium.md](laboratorium.md#jev-jako-pomoc-analityka). Stan na 21.11.2026.

## Co robi i czego nie robi

Jev dostaje stan i zamknięte pytanie, a zwraca rozkład prawdopodobieństwa po zadanych odpowiedziach i `confidence`. Nie generuje tekstu. U nas zadaje jedno pytanie: czy krawędź wymaga przeglądu człowieka (`przeglad` albo `spojne`). Stan to sama struktura przesłanek policzona przez silnik dowodowy: relacja, bity, grupy śladów z liczbą i wkładem. Bez wartości śladów, adresów, tekstów stron i reklam.

Wynik trafia do `AssistSuggestion` i jest wyłącznie sugestią. Nie zmienia krawędzi, wag, dowodów, grup ani decyzji analityka. Nie jest dowodem ani oceną winy.

## Granica danych

Jev to usługa zewnętrzna, hostowana w USA. Stan budowany z krawędzi to pochodna materiałów organizatora, więc adapter niczego nie wyśle, dopóki `JEV_ALLOW_CASE_DATA` nie jest `true`. Włączamy to dopiero po potwierdzeniu, że takie przekazanie jest dopuszczalne. Sama anonimizacja nie przesądza o dopuszczalności. Do tego czasu testy i pokazy używają wyłącznie danych syntetycznych.

Polityka prywatności TypeSafe (ostatnia zmiana 19.11.2025, [typesafe.ai/legal/privacy-policy](https://typesafe.ai/legal/privacy-policy)):

- usługi są hostowane w USA,
- TypeSafe zbiera dane wejściowe zapytań, ale deklaruje, że nie trenuje na nich ani nie dostraja modeli,
- dane osobowe przechowuje "tak długo, jak to rozsądnie potrzebne" do świadczenia usługi albo w celach biznesowych, bez podanego okresu,
- usuwa je na żądanie, jeśli nie ma obowiązku ich przechowania.

Warunki konkretnego konta (umowa, retencja, region) trzeba sprawdzić w konsoli TypeSafe przed włączeniem. Tego nie sprawdzałem.

## Uruchomienie

Klucz wpisujemy tylko w `.env` w katalogu głównym repo, który jest poza gitem. Klucz zostaje na backendzie, a do usługi idzie jako `Authorization: Bearer`.

| Zmienna | Domyślnie | Znaczenie |
|---|---|---|
| `TYPESAFE_API_KEY` | pusta | klucz API; bez niego adapter się nie uruchomi |
| `JEV_MODEL` | pusta | przypięta wersja, np. `jev-1.14.0`; aliasy `jev-latest` i `jev-preview` są odrzucane, bo ich odpowiedzi zmieniają się z wydaniem |
| `JEV_MODE` | `off` | `shadow` zapisuje sugestie bez pokazywania, `on` pozwala je pokazać |
| `JEV_ALLOW_CASE_DATA` | `false` | zgoda na wysyłkę pochodnych danych spraw, patrz wyżej |
| `JEV_TIMEOUT` | 20 | sekundy na jedno zapytanie |
| `JEV_MAX_REQUESTS` | 100 | najwięcej zapytań w jednym uruchomieniu |
| `JEV_BUDGET_USD` | 0.10 | budżet jednego uruchomienia |
| `JEV_PRICE_PER_MTOK` | 0.042 | cena za milion tokenów wejściowych |

Po zmianie `.env`: `docker compose up -d --force-recreate backend worker`. Potem `docker compose exec backend python manage.py jev_review [--edge N] [--relation same_operator] [--limit 100]`.

## Koszt i limity

Według [cennika modeli](https://docs.typesafe.ai/models) Jev 1.14 kosztuje 42 USD za miliard tokenów wejściowych, czyli 0,042 USD za milion. Tokeny wyjściowe są bezpłatne. Odpowiedź podaje `usage.input_tokens`, a adapter zapisuje je przy każdej sugestii. `jev_review` sumuje tokeny i przerywa przed zapytaniem, które przekroczyłoby `JEV_BUDGET_USD`. Nasz stan ma kilkaset tokenów, więc jedno zapytanie kosztuje rzędu ułamka setnej centa. Rzeczywistej liczby tokenów nie mierzyłem, bo nie wysłałem żadnego zapytania.

Statusy w `AssistSuggestion.status`:

| Odpowiedź usługi | Status | Co robi `jev_review` |
|---|---|---|
| 200 z poprawną odpowiedzią | `ok` albo `abstain` | dalej |
| 401 | `unauthorized` | kończy od razu |
| 402 | `payment` | kończy od razu |
| 429, 529 | `rate_limited` | czeka `Retry-After`, najwyżej 30 s; po 3 odmowach z rzędu kończy |
| 502, 503, brak połączenia | `unavailable` | po 3 z rzędu kończy |
| 504, przekroczony czas | `timeout` | po 3 z rzędu kończy |
| 400 (np. `max_tokens_exceeded`), 413, 422, odpowiedź spoza schematu, przekierowanie | `error` | dalej; zapisujemy tylko kod błędu, bez treści odpowiedzi |

Niepoprawna odpowiedź nigdy nie staje się wynikiem: odpowiedź spoza listy, rozkład spoza zakresu albo `confidence` poza 0..1 to `error`.

## Migracja z basal

- Zmienne `BASAL_*` nie są już czytane. Usuń je z `.env`.
- Wpisy `AssistSuggestion` z czasu basal zostają w bazie. Rozpoznać je można po `model` (`Remek/basal-…`), `revision` i `variant`. Nie mieszamy ich z wynikami Jev i nie przeliczamy.
- Pomiar lokalnego basal-2.0-mini z 21.11.2026 jest w [basal.md](basal.md#wynik-z-21112026-wstępny). Na 44 krawędziach nie pobił prostej reguły i nie ma przełożenia na Jev. Ewaluację Jev na danych organizatora blokuje granica danych opisana wyżej.

## Zadania

[#72](https://github.com/NikodemJachec99/deepfake-atlas/issues/72) ewaluacja (na danych syntetycznych, dopóki nie ma zgody na dane spraw), [#73](https://github.com/NikodemJachec99/deepfake-atlas/issues/73) API sugestii, [#74](https://github.com/NikodemJachec99/deepfake-atlas/issues/74) panel analityka, [#75](https://github.com/NikodemJachec99/deepfake-atlas/issues/75) scenariusz demo z wariantem bez modelu.
