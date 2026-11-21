# Wymagania: NASK "Follow the Fake"

Źródło: `docs/zrodla/opis-zadania.pdf`. Regulaminu zadania NASK jeszcze nie mamy, wymagania formalne zgłoszenia i kryteria z wagami są do uzupełnienia z platformy.
Strona z zajawką: https://science.nask.pl/hacknation

## Cel

Nie robimy idealnego detektora pojedynczej fałszywej reklamy. Robimy narzędzie, które łączy wiele pozornie niezależnych materiałów w kampanie na podstawie wspólnych śladów.

## Co musi być

- [x] **Demonstrator**: Next.js, ekran Discovery (`frontend/src/components/discovery.tsx`). Wygląd się nie liczy, ocena 0/1.
- [ ] Wejście: URL i tekst (nazwa produktu) działają. Zrzut ekranu z linkiem i plik z reklamą jeszcze nie.
- [ ] **Pozyskanie reklam**: Microsoft Ad Library działa na żywo, Meta ma konektor bez sprawdzenia na tokenie, portale rozrywkowe (sieci natywne) jeszcze nie.
- [ ] **Analiza materiału**:
  - [x] narracja: kontakty, prawie identyczne teksty (MinHash). Słowa kluczowe i rama narracyjna z modelu językowego jeszcze nie.
  - [ ] elementy wizualne, szablon produkcji kreacji: brak. Szablon strony docelowej jest.
  - [x] domena, przekierowania, odnośniki, metadane stron: domena, łańcuch, IP, ASN, NS, certyfikat, favicon, RDAP, identyfikatory śledzące, endpoint formularza.
  - [ ] wizerunki osób: tylko wzmianka w tekście.
- [x] **Podobieństwo i klastrowanie**: model dowodowy par z ważeniem rzadkością, relacje `same_campaign` i `similar`, kampanie.
- [ ] **Identyfikacja osób**: baza `people.Person` i dopasowanie po nazwie. Twarz i głos jeszcze nie.
- [x] **Reprezentacja powiązań**: krawędzie z dowodami w Postgresie, projekcja do Neo4j.

## Bonus

- [x] Scheduler: harmonogramy Temporal (`manage.py ensure_schedules`) skanują źródła i zlecają analizy.
- [x] Nowe odsłony tej samej kampanii: nowa reklama dołącza do istniejącej kampanii.

## Do ustalenia z platformy

- [ ] wymagania formalne zgłoszenia (repo, README, prezentacja, film?)
- [ ] kryteria oceny i wagi
- [ ] zasady użycia gotowych bibliotek, modeli i danych
- [ ] sposób udostępnienia repo jury
- [ ] czy organizator daje próbkę danych
