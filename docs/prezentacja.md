# Prezentacja na 5 minut i demo na 2 minuty

Etap II: 5 minut prezentacji, 5 minut pytań. Zgłoszenie: prezentacja i demo do 2 minut.
Liczby poniżej pochodzą z `GET /api/stats` po imporcie samych paczek organizatora, bez reklam z bibliotek (model `fs-5`, z podobieństwem znaczenia treści):

```json
{"ads": 28, "campaigns": 4, "operators": 3,
 "edges": {"same_campaign": 20, "same_operator": 13, "similar": 34},
 "cert_pl_listed": 6}
```

Przed prezentacją sprawdź je jeszcze raz: `curl localhost:8000/api/stats`. Jeśli się różnią, popraw slajd 4. Harmonogram skanów co 6 godzin dokłada reklamy z Microsoft Ad Library, więc na stosie, który chodzi dłużej, reklam jest więcej (np. 327 zamiast 28). Na demo wstrzymaj skany (przygotowanie niżej).

## Slajdy

### 1. Problem (30 s)

- Pojedyncza fałszywa reklama mówi mało. Domena żyje kilka dni, treść się zmienia, twarz celebryty jest wszędzie ta sama.
- Pytanie NASK: które materiały pochodzą z tego samego źródła i skąd to wiemy.
- Nasza odpowiedź: nie oceniamy, czy reklama jest oszustwem. Łączymy materiały w kampanie i operatorów, a każde połączenie ma listę dowodów, którą da się sprawdzić i podważyć.

### 2. Genom reklamy (45 s)

- Z każdego materiału (URL, zrzut reklamy, nagranie, zapisana strona, HAR, ZIP sprawy, archiwum NASK) wyciągamy markery w 7 rodzinach: infrastruktura, tracking i lejek, szablon strony, kreacja, narracja, osoby i marki, zachowanie.
- Ok. 50 typów markerów. Przykłady, które rozstrzygały na danych organizatora: identyfikator strony w panelu lejka z treści żądań POST, ścieżki zaplecza strony z HAR, piksel Meta, konto Google Ads, własny host zasobów operatora.
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
- Sprawdziliśmy to liczbowo. Bez plików HAR zostaje 19 z 33 połączeń, bez zapisu strony 30, bez zrzutów 32, a w żadnym wariancie nie powstaje fałszywe połączenie. Zmiana wag o ±50% rusza tylko 4 pary graniczne, rdzeń operatora A się nie zmienia.

### 6. Demo (2 min, scenariusz niżej)

### 7. Ograniczenia i dalej (30 s)

- Wagi są eksperckie. Bez oznaczonego zbioru nie podajemy precyzji ani czułości. Następny krok: model uczony na decyzjach analityków, które już zapisujemy w dzienniku audytu.
- Twarze rozpoznajemy tylko dla osób z małej bazy referencyjnej. Z nagrań bierzemy klatki, dźwięku nie analizujemy.
- Strony na żywo pobieramy bez JavaScriptu. Pełny zestaw cech dają przechwycenia z HAR.
- Działa jako `docker compose up`, z Temporalem, Postgresem i projekcją do Neo4j, sprawdzone na Windowsie i Linuksie, CI stawia cały stos przy każdym PR. Harmonogram skanuje bibliotekę reklam Microsoft. Wzbogacony korpus do pobrania jednym kliknięciem (`GET /api/export`).

## Plik PDF do zgłoszenia

Slajdy do zgłoszenia generujemy z prawdziwego interfejsu i API, a nie ręcznie. Zrzuty i liczby pochodzą z działającego stosu, więc PDF zawiera dane organizatora i leży tylko w `data/zgloszenie/` (poza gitem).

```powershell
uv run --no-project --with playwright python scripts/prezentacja/zrzuty.py --base http://localhost:3010 --api http://localhost:8010 --out data/zgloszenie/zrzuty
uv run --no-project --with playwright python scripts/prezentacja/pdf.py --api http://localhost:8010 --shots data/zgloszenie/zrzuty --out data/zgloszenie/prezentacja.pdf
```

- `zrzuty.py` otwiera graf operatora A, krawędzie spraw 1 i 2 oraz 2 i p3, laboratorium z testem najsłabszego ogniwa, dwie twarze sprawy 61 i kartę reklamy p3. Identyfikatory reklam i krawędzi szuka przez API po numerach spraw, bo zmieniają się przy imporcie. Tylko czyta.
- `pdf.py` liczy wynik z API z filtrem `source=capture` (same paczki organizatora): strony, sprawy, kampanie, operatorów, krawędzie między stronami z paczek i strony z Listy CERT. Wstawia liczby i zrzuty do `scripts/prezentacja/slajdy.html` i drukuje 10 slajdów 1280x720. Przerywa, gdy PDF ma ponad 10 MB.
- Treść slajdów (poza liczbami ze slajdu z wynikiem) jest w szablonie. Zmiana opisu metody wymaga zmiany w `slajdy.html` i tutaj.

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
| 0:00 | Ekran Discovery, przeciągamy `p3.zip` na pole plików | przycisk "Analiza trwa" |
| 0:10 | Przebieg analizy | siedem kroków "zakończono" i dziennik zdarzeń: łańcuch adresu, liczba markerów w każdej rodzinie, wzbogacanie, powiązania |
| 0:25 | Wynik po prawej | "Nowa kampania znanego operatora", Operator O-0001, najsilniejsze dowody: Meta Pixel i identyfikator strony w panelu lejka po 18 bitów |
| 0:40 | Przewijamy niżej | graf: nowa reklama w środku, krawędzie do 6 stron operatora |
| 0:55 | Klik w krawędź z listy powiązań | panel "Ten sam operator": pewność 1,00, suma ok. 56 bitów, znacznik "marker rozstrzygający", pasek rodzin, obie reklamy ze zrzutami, dowody według wkładu z liczbą źródeł (np. "w 2 z 19 źródeł") |
| 1:25 | Operatorzy, O-0001 | kampania K-0001, 7 reklam (nowa bez kampanii), markery rdzeniowe: zestaw parametrów z `utm_visit`, identyfikatory w panelu lejka, ścieżki zaplecza; "Otwórz graf grupy" |
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

## Pytania, których się spodziewamy

| Pytanie | Odpowiedź |
|---|---|
| Skąd wagi? | Eksperckie, w jednym pliku (`evidence/kinds.py`). Rzadkość liczona z korpusu po niezależnych źródłach, w małym korpusie działa częstość bazowa typu. |
| Jaka skuteczność? | Nie mamy oznaczonego zbioru, więc nie podajemy liczb. Każdą krawędź między sprawami przejrzeliśmy ręcznie po dowodach, wynik w `docs/dane-organizatora.md`. |
| Co z nową kampanią z innej domeny i innym artykułem? | Właśnie to pokazuje demo: łączy ślad konta w panelu lejka i piksel, nie treść. |
| Co, gdy strona już nie działa? | Analiza kończy się z mniejszą liczbą cech. Sam zrzut reklamy daje OCR, nazwę reklamodawcy i hash kreacji. |
| Twarze? | Twarz na zrzucie reklamy porównujemy z małą bazą osób publicznych (YuNet i SFace, zdjęcia z Commons na wolnej licencji). Na danych organizatora rozpoznało twarze w 8 zrzutach (baza 9 osób), zgodnie z nazwiskami w tekstach. Twarz to motyw: nie łączy operatorów, bo ta sama twarz występuje u różnych. |
| Skąd wiecie, które połączenie jest kruche? | Laboratorium dowodów: `POST /api/edges/{id}/simulate` przelicza krawędź bez wybranych śladów i niczego nie zapisuje, a `GET /api/edges/{id}/suggestions` mówi, czego brakuje. Przykład z danych: operator B trzyma się na jednym hoście zasobów. Bez niego para spada do podobieństwa. Opis: `docs/laboratorium.md`. |
| Dlaczego sprawy 48 i p11 nie są przy operatorze A? | Dzielą z nim tylko silnik lejka. Program mógł kupić każdy, operatora wskazuje ślad jego konta albo infrastruktury. |
