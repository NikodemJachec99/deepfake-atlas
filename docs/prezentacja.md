# Prezentacja na 5 minut i demo na 2 minuty

Etap II: 5 minut prezentacji, 5 minut pytań. Zgłoszenie: prezentacja i demo do 2 minut.
Liczby poniżej pochodzą z `GET /api/stats` po imporcie samych paczek organizatora, bez reklam z bibliotek (model `fs-5.1`, pomiar 22.11, z podobieństwem znaczenia treści):

```json
{"ads": 28, "campaigns": 4, "operators": 3,
 "edges": {"same_campaign": 19, "same_operator": 13, "similar": 35},
 "cert_pl_listed": 6}
```

Przed prezentacją sprawdź je jeszcze raz: `curl localhost:8000/api/stats`. Jeśli się różnią, popraw liczby na slajdach z wynikami (patrz niżej). Harmonogram skanów co 6 godzin dokłada reklamy z Microsoft Ad Library, więc na stosie, który chodzi dłużej, reklam jest więcej (np. 327 zamiast 28). Na demo wstrzymaj skany (przygotowanie niżej).

## Talia zgłoszeniowa: 10 slajdów

Struktura talii do zgłoszenia (zadanie [#487](https://github.com/NikodemJachec99/deepfake-atlas/issues/487)), z liczbami policzonymi z API przez `scripts/prezentacja/pdf.py` (filtr `source=capture`, same paczki organizatora) i zrzutami z prawdziwego interfejsu. Sama talia (`data/zgloszenie/prezentacja.html` i `.pdf`) leży poza gitem, bo zawiera dane organizatora. W repozytorium jest generator (`scripts/prezentacja/`) i ten opis.

| Nr | Slajd | Treść |
|---|---|---|
| 1 | hero | SCAM DNA, hasło „Różne reklamy. Jedno zaplecze.”, jedno zdanie o tym, co system robi |
| 2 | mapa | graf kampanii i operatorów zbudowany z paczek organizatora bez podpowiedzi, które sprawy pasują |
| 3 | genom | siedem rodzin śladów, 62 typy markerów, przykłady, które rozstrzygały na danych organizatora |
| 4 | operator | karta operatora: „dlaczego razem” w bitach, miniatury materiałów, domeny, kampanie |
| 5 | wagi | wagi w bitach zamiast progów podobieństwa, rzadkość liczona po niezależnych źródłach |
| 6 | podobne | podobne to nie to samo źródło: skopiowana treść i silnik lejka bez śladu operatora |
| 7 | link | jedno powiązanie z dowodami: hipoteza modelu, przesłanki w bitach, ograniczenia, dwie twarze jednego linku |
| 8 | przesłanka | zakwestionowanie przesłanki w całym korpusie: podgląd, co się rozpadnie, a co trzyma się na innych śladach |
| 9 | odporność | pomiar: bez HAR 18 z 32 połączeń, bez zapisu strony 30, bez zrzutów 32, 0 nowych fałszywych połączeń, 7 z 7 wariantów próby jury |
| 10 | cert | pokrycie Listą Ostrzeżeń CERT Polska i co z tego wynika: jedna znana domena wskazuje resztę zaplecza, plus ograniczenia i dalsze kroki |

Plan 5-minutowego wystąpienia poniżej mieści się w tych dziesięciu slajdach. Jeżeli szablon w `scripts/prezentacja/slajdy.html` ma inną liczbę slajdów niż ta tabela, obowiązuje szablon, a tabelę trzeba poprawić.

## Slajdy

### 1. Problem (30 s)

- Pojedyncza fałszywa reklama mówi mało. Domena żyje kilka dni, treść się zmienia, twarz celebryty jest wszędzie ta sama.
- Pytanie NASK: które materiały pochodzą z tego samego źródła i skąd to wiemy.
- Nasza odpowiedź: nie oceniamy, czy reklama jest oszustwem. Łączymy materiały w kampanie i operatorów, a każde połączenie ma listę dowodów, którą da się sprawdzić i podważyć.

### 2. Genom reklamy (45 s)

- Z każdego materiału (URL, zrzut reklamy, nagranie, zapisana strona, HAR, ZIP sprawy, archiwum NASK) wyciągamy markery w 7 rodzinach: infrastruktura, tracking i lejek, szablon strony, kreacja, narracja, osoby i marki, zachowanie.
- 62 typy markerów (57 niosących dowód). Przykłady, które rozstrzygały na danych organizatora: identyfikator strony w panelu lejka z treści żądań POST, ścieżki zaplecza strony z HAR, piksel Meta, konto Google Ads, własny host zasobów operatora.
- Nagrania: 8 klatek z OCR, twarzami i hashem. Sprawa 5 (sama reklama wideo) dostaje tak tekst reklamy z podszyciem pod lekarza.
- Znaczenie treści: lokalny model wielojęzyczny łapie ten sam artykuł przepisany innymi słowami (sprawa 48 i strona 1 sprawy 61: znaczenie 0,98 przy zgodności tekstu 0,39).
- Analiza materiału z przechwycenia działa bez sieci. Niczego nie pobieramy od oszustów.

### 3. Metoda: Evidence Fusion (1 min)

- Każdy wspólny marker dostaje wagę w bitach: o ile bardziej prawdopodobne jest, że dwie reklamy go dzielą, bo mają wspólne źródło, niż przez przypadek (Fellegi-Sunter z ważeniem rzadkością).
- Adres z puli Cloudflare: ułamek bita. Identyfikator w panelu lejka: 18 bitów.
- Sama wysoka suma nie wystarcza. Wspólne źródło wymaga rzadkiego markera rozstrzygającego albo dwóch niezależnych potwierdzeń, z których jedno dotyczy zaplecza.
- Trzy relacje: ta sama kampania (źródło i opowieść), ten sam operator (źródło, inna opowieść), podobne (koncepcja bez dowodu wspólnego źródła).
- Kampania i operator to składowe spójne po krawędziach, które przeszły regułę. Bez łączenia po progu, więc bez efektu łańcucha.

### 4. Wynik na danych organizatora (1 min)

- 28 stron z 25 spraw z dwóch paczek. Silnik nie dostał informacji, które sprawy pasują do siebie.
- **Operator A**: 8 stron na 7 domenach w 2 kampaniach. Łączą je identyfikatory strony w panelu lejka i wspólny piksel Meta, mimo różnych domen, adresów IP i treści.
- **Operator B**: 3 strony na 2 domenach, spięte własnym hostem zasobów operatora.
- **Sprawa 61**: jedna kampania. Ten sam pełny adres dał w odstępie 3 minut dwie różne strony: ofertę z pikselem Google Ads i neutralny "portal analiz". Mówimy "cloaking albo jednorazowy token wizyty", bo nie wiemy, kto przechwytywał.
- 6 stron jest na Liście Ostrzeżeń CERT Polska. Pozostałe domeny tych samych operatorów na liście nie ma. Jedna znana domena wskazuje resztę.
- Duplikat (to samo przechwycenie w dwóch sprawach) oznaczony osobno.

### 5. Czego nie łączymy (30 s)

- Ten sam artykuł na innym zapleczu to tylko podobieństwo: treść da się skopiować.
- Ten sam silnik lejka bez śladu konta operatora to też tylko podobieństwo: silnik da się kupić. Tak potraktowaliśmy sprawy 48, 61 i p11. Wcześniej wisiały przy operatorze A, przegląd każdej krawędzi to wyłapał i reguła została poprawiona z testem.
- 14 stron zostało bez operatora.
- Sprawdziliśmy to liczbowo. Bez plików HAR zostaje 18 z 32 połączeń, bez zapisu strony 30, bez zrzutów 32, a w żadnym wariancie nie powstaje fałszywe połączenie. Zmiana wag o ±50% rusza tylko 4 pary graniczne, rdzeń operatora A się nie zmienia.

### 6. Demo (2 min, scenariusz niżej)

### 7. Ograniczenia i dalej (30 s)

- Domyślnie działają wagi eksperckie, wagi uczone metodą EM są policzone do porównania. Bez oznaczonego zbioru nie podajemy precyzji ani czułości, a wynik modelu nie jest kalibrowany. Następny krok: kalibracja na decyzjach analityków, które już zapisujemy.
- Twarze rozpoznajemy tylko dla osób z małej bazy referencyjnej. Z nagrań bierzemy klatki i mowę zamienioną na tekst (Whisper lokalnie), głosu mówcy nie porównujemy.
- Crawler z przeglądarką działa w odizolowanym kontenerze, ale bez polskiego adresu domowego; strony wykrywające automat mogą pokazać białą stronę.
- Start jednym poleceniem (`python scripts/start.py`), z Temporalem, Postgresem, crawlerem i projekcją do Neo4j, sprawdzony na świeżym klonie. Harmonogram skanuje bibliotekę reklam Microsoft. Pakiet dowodowy operatora i korpus do pobrania jednym kliknięciem.

## Plik PDF do zgłoszenia

Slajdy do zgłoszenia generujemy z prawdziwego interfejsu i API, a nie ręcznie. Zrzuty i liczby pochodzą z działającego stosu, więc PDF zawiera dane organizatora i leży tylko w `data/zgloszenie/` (poza gitem).

```powershell
uv run --no-project --with playwright python scripts/prezentacja/zrzuty.py --base http://localhost:3010 --api http://localhost:8010 --out data/zgloszenie/zrzuty
uv run --no-project --with playwright python scripts/prezentacja/pdf.py --api http://localhost:8010 --shots data/zgloszenie/zrzuty --out data/zgloszenie/prezentacja.pdf
```

- `zrzuty.py` otwiera graf operatora A, krawędzie spraw 1 i 2 oraz 2 i p3, laboratorium z testem najsłabszego ogniwa (zakładka Kontekst), dwie twarze sprawy 61, ślady karty reklamy p3, stanowisko oceny na parze operatora A, podgląd zakwestionowania jej najmocniejszej przesłanki i kartę operatora O-0001. Identyfikatory reklam i krawędzi szuka przez API po numerach spraw, bo zmieniają się przy imporcie. Tylko czyta.
- `pdf.py` liczy wynik z API z filtrem `source=capture` (same paczki organizatora): strony, sprawy, kampanie, operatorów, krawędzie między stronami z paczek i strony z Listy CERT. Wstawia liczby i zrzuty do `scripts/prezentacja/slajdy.html` i drukuje slajdy 1280x720 z szablonu (talia z sekcji niżej). Przerywa, gdy PDF ma ponad 10 MB.
- Treść slajdów (poza liczbami ze slajdu z wynikiem) jest w szablonie. Zmiana opisu metody wymaga zmiany w `slajdy.html` i tutaj.

## Nagranie demo do zgłoszenia

Nagranie (ok. 70 s, 1440x900, napisy na ekranie) powstaje skryptem na osobnym stosie przygotowanym jak w scenariuszu niżej, bo wrzucenie `p3.zip` zmienia korpus. Plik zawiera dane organizatora, więc leży w `data/zgloszenie/demo.mp4` (poza gitem).

```powershell
uv run --no-project --with playwright --with imageio-ffmpeg python scripts/nagranie_demo.py --ui http://localhost:3100 --api http://localhost:8100 --zip data/raw/p3.zip --out data/zgloszenie
```

Kolejność: Analiza, zakładka Pliki i wrzucenie `p3.zip`, wynik "nowa kampania znanego operatora", stanowisko oceny na parze z nową reklamą (hipoteza, materiały A i B, przesłanki i ograniczenia), podgląd zakwestionowania pierwszej przesłanki (bez zapisu), karta operatora O-0001 z sekcją "Dlaczego razem" i pakietem dowodowym. Próba 22.11 na stosie `fresh-z14` (main po #379): 67 s, mp4 1,6 MB. Przed kolejnym nagraniem korpus trzeba przygotować od nowa, bo p3 jest już w nim po pierwszym przebiegu.

## Scenariusz demo (2 min)

Cel: pokazać pełny proces na nowym materiale i dołączenie do znanego operatora jako nowej kampanii. Kampania B operatora A (sprawy p3 i p4 z drugiej paczki) zostaje poza importem.

### Przygotowanie (przed wejściem na scenę)

Korpus bez spraw p3, p4 i p11 z drugiej paczki, wszystkie trzy spakowane do ZIP-ów:

```bash
docker compose exec backend python manage.py ensure_schedules --pause   # skany bibliotek reklam stoją do końca demo
docker compose exec backend python manage.py reset_corpus --yes
docker compose exec backend python manage.py import_bundle /data/raw/nask --name nask
mkdir -p data/raw/demo data/raw/demo-na-zywo
cp -r data/raw/nask-backup/. data/raw/demo/
mv data/raw/demo/p3 data/raw/demo/p4 data/raw/demo/p11 data/raw/demo-na-zywo/
docker compose exec backend python manage.py import_bundle /data/raw/demo --name nask-backup
cd data/raw/demo-na-zywo && for c in p3 p4 p11; do zip -qr ../$c.zip $c; done && cd -
```

Na Windowsie bez `zip`: `Compress-Archive data/raw/demo-na-zywo/p3 data/raw/p3.zip` (tak samo p4 i p11). Na Git Bash przed poleceniami z `/data/...` ustaw `MSYS_NO_PATHCONV=1`.

Po imporcie `GET /api/stats` daje 25 reklam, 3 kampanie i 3 operatorów, a operator O-0001 ma 6 stron na 5 domenach w jednej kampanii.

Próba 2026-11-21 na świeżym klonie (`main` po #16, crt.sh włączony): przygotowanie ok. 2 min, analiza `p3.zip` ok. 5 s, `p11.zip` ok. 25 s, bo etap Infrastruktura czeka na crt.sh. Jeśli crt.sh nie odpowiada, etap czeka do 25 s i idzie dalej.

Po demo: `docker compose exec backend python manage.py ensure_schedules --resume` wznawia skany.

### Przebieg

| Czas | Co robimy | Co ma być widać |
|---|---|---|
| 0:00 | Ekran Analiza, zakładka Pliki, przeciągamy `p3.zip` na pole plików, "Przeanalizuj materiał" | przycisk "Analiza trwa" |
| 0:10 | Przebieg analizy | siedem kroków "zakończono" i dziennik zdarzeń: łańcuch adresu, liczba markerów w każdej rodzinie, wzbogacanie, powiązania |
| 0:25 | Wynik po prawej | "Nowa kampania znanego operatora", Operator O-0001, najsilniejsze dowody: Meta Pixel i identyfikator strony w panelu lejka po 18 bitów |
| 0:40 | Do oceny, para "Nowa reklama w znanej grupie" | hipoteza modelu osobno od oceny, materiały A i B obok siebie, przesłanki: Meta Pixel i identyfikator panelu lejka (znacznik "rozstrzyga"), ramka z ograniczeniami |
| 0:55 | "Zakwestionuj przesłankę" przy pikselu, tylko podgląd | "Wpływ na cały korpus": ile krawędzi używa śladu, grupy, które zostają razem, i dzięki jakim innym śladom |
| 1:25 | Operatorzy, O-0001 | "Dlaczego razem" w bitach, miniatury materiałów, "Pobierz pakiet (ZIP)" |
| 1:50 | Jedno zdanie | "Nowa domena, inny artykuł, inna osoba. System wie, kto za nią stoi, i pokazuje dlaczego." |

### Plan B

- Gdy Discovery nie zadziała: `curl -X POST localhost:8000/api/analyses/upload -F "files=@data/raw/p3.zip"` i karta reklamy w archiwum.
- Gdy jest czas albo pytają o warianty: wrzucić `p4.zip`. Wynik: nowa odsłona znanej kampanii, bo p4 to ten sam szablon artykułu co p3 z podmienioną osobą.
- Gdy pytają o fałszywe połączenia: wrzucić `p11.zip`. Wynik: "Podobna koncepcja, brak dowodu wspólnego źródła", dowody to tylko ścieżki zaplecza strony. Ten sam silnik lejka, ale bez śladu konta operatora, więc system nie dopisuje jej do operatora A. W dzienniku etapu Infrastruktura widać trop z crt.sh: certyfikat `sfuxd.com` obejmuje też `zixips.com`.

### Dodatek, gdy zostaje czas albo padnie pytanie o kruche połączenia (40 s)

Laboratorium dowodów na kampanii A i operatorze B, kroki i sprawdzone wyniki w [laboratorium.md](laboratorium.md#scenariusz-pokazu-laboratorium-52). Idzie po głównym demo, nie zamiast niego.

### Drugi dodatek: dwie twarze jednego linku (25 s)

Sprawa 61: ten sam pełny adres dał w 161 s dwie różne strony. Kroki i wyniki w [dwie-twarze.md](dwie-twarze.md#scenariusz-pokazu-65). Po laboratorium, jeśli jest czas.

### Trzeci dodatek: pamięć sprzeciwu (45 s)

Odrzucenie krawędzi 1 ↔ 48 z powodem "wspólne narzędzie" wraca jako precedens przy `p11.zip` z Planu B. Panel Jev pokazuje "Model wyłączony". Kroki i wyniki w [pamiec-sprzeciwu.md](pamiec-sprzeciwu.md). Po pozostałych dodatkach, jeśli jest czas.

### Czwarty dodatek: "Spróbuj zgubić kampanię" (90 s)

Jury samo próbuje oszukać system. Wyniki i metoda: [dane-organizatora.md](dane-organizatora.md#próba-jury-spróbuj-zgubić-kampanię-22112026). Pliki wariantów powstają przed demo poza repozytorium (`scripts/proba_jury.py` zapisuje je jako ZIP-y w katalogu `--robocze`: `pulapka_*.zip`, `przebranie_*_bez_har.zip`). Korpus jak w głównym demo, z operatorem A w całości.

| Czas | Krok | Co robimy | Co ma być widać |
|---|---|---|---|
| 0:00 | 1. Przebranie (35 s) | Discovery, wrzucamy `przebranie_nask_1_bez_har.zip`: zrzut przycięty i w JPEG, 3 zdania podmienione, domena `.example`, bez HAR | kampania K-0001 i operator O-0001, jak oryginał. Powiedz: "bez HAR zniknął identyfikator panelu lejka i piksel (z 51 markerów zostało 11), ale 97% tekstu, szablon i twarz zostały, więc kampania się trzyma" |
| 0:35 | 2. Pułapka (25 s) | wrzucamy `pulapka_nask_1_obca_infrastruktura.zip`: ten sam zrzut i tekst, obca domena, bez śladów zaplecza | "Podobna koncepcja", bez kampanii i operatora. Powiedz: "kopia kreacji i tekstu to pokrewieństwo treści, nie dowód wspólnego operatora" |
| 1:00 | 3. Zakwestionowanie mostu (30 s) | krawędź backup/p5 do nask/2, "Zakwestionuj przesłankę" na hoście zasobów, potem "Przywróć przesłankę" w historii zakwestionowań | po zapisaniu O-0002 traci backup/p5 (3 reklamy na 2), po przywróceniu wraca. Powiedz: "to jedyny most: 1 ślad z 104 wspólnych rozdziela grupę" |

Plan B: te same trzy kroki z `curl -X POST localhost:8000/api/analyses/upload -F "files=@<plik>.zip"`, `POST /api/premises/preview`, `POST /api/premises` i `POST /api/premises/{id}/restore`. Kroki 1 i 3 w interfejsie nie były przećwiczone (wynik sprawdzony przez API). Całość jednym poleceniem na osobnym stosie: `scripts/proba_jury.py` (zmienia korpus, więc nie na stosie demo).

Uczciwie, gdy padnie pytanie "a mocniejsze przebranie?": zmieniliśmy 3 zdania i domenę, szablon i reszta tekstu zostały, wszystkie 7 wariantów wróciło do swojej grupy. Przepisanego całego artykułu na innym szablonie nie sprawdzaliśmy. Pułapka pokazuje, że z samej kopii treści system nie zrobi operatora.

## Tryb prosty i Szczegóły techniczne

Interfejs startuje w trybie prostym: wnioski prostym językiem (ocena, jedno zdanie "dlaczego", z czym się łączy), bez bitów, prawdopodobieństw, identyfikatorów krawędzi, wersji modelu, skrótów i nazw etapów potoku; pasek stanu korpusu jest ukryty. Pełne dane włącza przełącznik "Szczegóły techniczne" w nagłówku (na telefonie w menu "Więcej"). Wybór zostaje w przeglądarce, a dane są te same, zmienia się tylko to, co widać.

## Pytania, których się spodziewamy

| Pytanie | Odpowiedź |
|---|---|
| Skąd wagi? | Eksperckie, w jednym pliku (`evidence/kinds.py`). Rzadkość liczona z korpusu po niezależnych źródłach, w małym korpusie działa częstość bazowa typu. |
| Jaka skuteczność? | Nie mamy oznaczonego zbioru, więc nie podajemy liczb. Każdą krawędź między sprawami przejrzeliśmy ręcznie po dowodach, wynik w `docs/dane-organizatora.md`. |
| Co z nową kampanią z innej domeny i innym artykułem? | Właśnie to pokazuje demo: łączy ślad konta w panelu lejka i piksel, nie treść. |
| Co, gdy strona już nie działa? | Analiza kończy się z mniejszą liczbą cech. Sam zrzut reklamy daje OCR, nazwę reklamodawcy i hash kreacji. |
| Twarze? | Twarz na zrzucie reklamy porównujemy z małą bazą osób publicznych (YuNet i SFace, zdjęcia z Commons na wolnej licencji). Na danych organizatora rozpoznało twarze w 8 zrzutach (baza 10 osób), zgodnie z nazwiskami w tekstach. Twarz to motyw: nie łączy operatorów, bo ta sama twarz występuje u różnych. |
| Skąd wiecie, które połączenie jest kruche? | Laboratorium dowodów: `POST /api/edges/{id}/simulate` przelicza krawędź bez wybranych śladów i niczego nie zapisuje, a `GET /api/edges/{id}/suggestions` mówi, czego brakuje. Przykład z danych: operator B trzyma się na jednym hoście zasobów. Bez niego para spada do podobieństwa. Opis: `docs/laboratorium.md`. |
| Dlaczego sprawy 48 i p11 nie są przy operatorze A? | Dzielą z nim tylko silnik lejka. Program mógł kupić każdy, operatora wskazuje ślad jego konta albo infrastruktury. |
