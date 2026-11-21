# Pamięć sprzeciwu i Jev: scenariusz pokazu

Dodatek do demo ([#75](https://github.com/NikodemJachec99/deepfake-atlas/issues/75)). Pokazuje, że decyzja analityka z powodem wraca przy następnej podobnej sprawie jako precedens, a sugestia Jev jest osobną, opcjonalną warstwą. Idzie po głównym demo z [prezentacja.md](prezentacja.md) i korzysta z jego Planu B (`p11.zip`), niczego w nim nie zmienia. Stan na 21.11.2026.

## Cztery różne rzeczy na jednym ekranie

| Co | Skąd | Czy zmienia grupy |
|---|---|---|
| wynik regułowy: relacja, bity, pewność | silnik dowodowy (`fusion.py`, model `fs-5`) | tak, tylko przez relacje `same_campaign` i `same_operator` |
| dowód | konkretne ślady obu reklam z liczbą źródeł i wkładem w bitach | nie bezpośrednio, są podstawą relacji |
| wcześniejsza decyzja (precedens) | zapisana decyzja analityka o innej parze, z powodem i migawką dowodów | nie, to punkt odniesienia |
| sugestia Jev | zewnętrzny model, tylko gdy włączony, ze zgodą na dane spraw | nie, doradczo |

## Wersje

`main` po #135 (merge `#141`), model dowodowy `fs-5`, pamięć sprzeciwu z #67/#68 i panel z #69, panel Jev z #74, adapter Jev z #116 i #73. Jev: `JEV_MODE=off`, `JEV_ALLOW_CASE_DATA=false`.

## Przebieg (ok. 45 s)

Korpus jak w głównym demo, bez spraw p3, p4 i p11. Krok 2 to Plan B z głównego demo, więc nie trzeba niczego przygotowywać osobno.

| Czas | Co robimy | Co ma być widać |
|---|---|---|
| 0:00 | Archiwum albo graf, krawędź sprawa 1 ↔ sprawa 48 (`similar`, 26,4 bita) | dowody: ścieżki zaplecza, zestaw parametrów, osoba i tematyka; żadnego śladu konta operatora |
| 0:10 | W panelu krawędzi: "Powód decyzji" → "Wspólne narzędzie albo silnik, nie ślad operatora", notatka "ten sam silnik lejka, brak śladu konta operatora", przycisk "Odrzuć" | decyzja zapisana; "Historia decyzji i precedensy" pokazuje wpis z powodem i migawką 11 dowodów |
| 0:20 | Discovery, przeciągamy `p11.zip` | "Podobna koncepcja, brak dowodu wspólnego źródła" (jak w Planie B) |
| 0:30 | Klik w krawędź p11 ↔ sprawa 1, sekcja "Historia decyzji i precedensy" | precedens: odrzucenie krawędzi 1 ↔ 48 z powodem "Wspólne narzędzie albo silnik", podobieństwo 0,5, wspólne grupy: ślady silnika lejka i motywy, różnica: "Precedens miał ślady, których tu nie ma: Infrastruktura domeny, Ślad językowy operatora" |
| 0:40 | Sekcja "Sugestia przeglądu Jev" | "Model wyłączony". Jedno zdanie: "Model jest opcjonalny. W ewaluacji nie oceniał struktury przesłanek lepiej niż reguła, więc decyzję podejmuje analityk." |

## Wynik zaobserwowany

Próba 21.11.2026 na kopii bazy stosu demo (28 reklam, 63 krawędzie, w tym p11, więc bez wrzucania na żywo). Te same wywołania API, które robi interfejs:

| Krok | Wynik | Czas |
|---|---|---|
| `GET /api/edges/3350` (1 ↔ 48) | `similar`, 26,4 bita | 255 ms (pierwsze wywołanie po starcie) |
| `POST /api/edges/3350/verdict` z `reason=shared_tool` | `rejected`, `verdict_reason=shared_tool` | 33 ms |
| `GET /api/edges/3350/decisions` | 1 wpis, migawka: `similar`, 11 dowodów, `fs-5` | 3 ms |
| `GET /api/edges/3363/precedents` (1 ↔ p11) | `found`, 1 rozpatrzony, 1 pasujący, bez konfliktu; podobieństwo 0,5; wspólne: `kit`, `motif`; tylko w precedensie: `infra`, `kind:lang_trace`; nowych niezależnych śladów brak | 4 ms |
| `GET /api/edges/3363/assist` | `mode=off`, `status=disabled`, `visible=false`, w przesłankach `tylko_silnik_lub_motywy=true` | 3 ms |

Identyfikatory krawędzi zależą od importu. Na scenie wybieramy krawędzie po sprawach, nie po numerach.

## Plan awaryjny bez modelu

To jest wariant domyślny: Jev jest wyłączony, a pamięć sprzeciwu i precedensy działają lokalnie, bez sieci. Gdy precedens się nie pokaże (np. decyzja zapisana na innej parze), pokazujemy "Historia decyzji i precedensy" na samej krawędzi 1 ↔ 48: powód, notatkę i migawkę. Gdy nie działa interfejs, te same kroki przez `curl` na endpointach z tabeli wyżej.

## Jev na pokazie, jeśli padnie pytanie

Danych spraw do Jev nie wysyłamy, dopóki nie wyjaśnimy dopuszczalności (`JEV_ALLOW_CASE_DATA=false`). Na żywo można pokazać tylko stany syntetyczne: `python manage.py jev_eval --versions edge-review-v1 --sample 10 --out raport.json` (ok. 40 zapytań, poniżej 0,002 USD). Wynik i ograniczenia: [jev.md](jev.md#ewaluacja-72-21112026). Nie mówimy o skuteczności Jev na danych NASK, bo jej nie mierzyliśmy.

## Ograniczenia

- Precedens działa na grupach śladów, nie na wartościach. Pokazuje podobny kształt dowodów, a nie ten sam ślad.
- Wcześniejsza decyzja nie przesądza o nowej krawędzi i nic w systemie jej automatycznie nie stosuje.
- Pokaz na jednej decyzji pokazuje mechanizm, a nie jakość. O trafności precedensów nic nie wiemy bez zbioru decyzji analityków.
- API nie ma uwierzytelniania, więc notatki są widoczne dla każdego z dostępem do API (sekrety są zamieniane na skróty).
