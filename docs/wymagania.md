# Wymagania: NASK "Follow the Fake"

Źródło: `docs/zrodla/opis-zadania.pdf`. Regulaminu zadania NASK jeszcze nie mamy, wymagania formalne zgłoszenia i kryteria z wagami są do uzupełnienia z platformy.
Strona z zajawką: https://science.nask.pl/hacknation

## Cel

Nie robimy idealnego detektora pojedynczej fałszywej reklamy. Robimy narzędzie, które łączy wiele pozornie niezależnych materiałów w kampanie na podstawie wspólnych śladów.

## Co musi być

- [ ] **Demonstrator**: prosta strona (Streamlit, Gradio albo coś innego). Wygląd się nie liczy, ocena 0/1: jest albo nie ma.
- [ ] Wejście: URL, screenshot z linkiem, nazwa produktu albo plik z podejrzaną reklamą. Uruchamia analizę.
- [ ] **Pozyskanie reklam**: dostęp do bibliotek reklam (social media, portale rozrywkowe).
- [ ] **Analiza materiału**, zakres dowolny, oceniana jest przydatność mechanizmów. Przykłady z opisu:
  - [ ] słowa kluczowe z tekstu, narracja, motyw przewodni
  - [ ] najważniejsze elementy wizualne, szablon produkcji
  - [ ] domena, przekierowania, odnośniki, metadane stron (domeny żyją krótko, ale dzielą metadane)
  - [ ] wizerunki osób
- [ ] **Podobieństwo i klastrowanie** (kluczowy element). Metoda dowolna: ważone podobieństwo, mały model albo silnik klastrujący. Sygnały: wizualne, semantyczne, konceptualne, wspólna domena, te same osoby, ten sam szablon, drobne sygnały, które razem wskazują jedno źródło.
- [ ] **Identyfikacja osób**: metoda dowolna. Sugestia: mała baza referencyjna kilku najczęściej występujących osób. Wielkość bazy nie ma znaczenia, ma pokazać, że narzędzie działa.
- [ ] **Reprezentacja powiązań**: dowolna, organizator podsuwa Neo4j.

## Bonus

- [ ] Wbudowany scheduler, który sam skanuje znane biblioteki reklam, znajduje podejrzane i je analizuje.
- [ ] Wykrywanie nowych odsłon tej samej kampanii na podstawie znanych wzorców.

## Do ustalenia z platformy

- [ ] wymagania formalne zgłoszenia (repo, README, prezentacja, film?)
- [ ] kryteria oceny i wagi
- [ ] sposób udostępnienia repo jury
- [ ] czy repo ma zostać prywatne do końca wydarzenia (u KOWR tak, tu zakładamy to samo)
