# Crawler z przeglądarką

Strony oszustów często przekierowują skryptem, ładują formularz lejka dopiero po wykonaniu JavaScriptu i wysyłają identyfikatory panelu w żądaniach POST. Klient HTTP tego nie widzi. Usługa `crawler` renderuje stronę w Chromium (Playwright) i oddaje to samo, co przechwycenie z HAR, więc etap extract używa tych samych ekstraktorów.

## Co zwraca

`POST http://crawler:8000/render {"url": "...", "profile": "victim" | "bot"}`:

| Pole | Znaczenie |
|---|---|
| `chain` | przejścia ramki głównej: `via` = `http` (pierwsze wejście i 3xx) albo `js` (skrypt, meta refresh) |
| `final_url`, `status` | strona końcowa |
| `html` | DOM po wykonaniu skryptów (do 3 MB) |
| `har` | ruch sieciowy z treścią odpowiedzi; adres serwera wpisuje proxy, które się z nim łączyło |
| `screenshot` | zrzut ekranu PNG (base64) |
| `console`, `blocked` | komunikaty konsoli i żądania zablokowane przez ochronę |

W potoku (`backend/workflows/pipeline.py`, etap crawl) HAR profilu ofiary trafia do `state["capture"]["har"]`, ślady z niego do `state["capture"]["observations"]`, hasze obrazów strony do `image_hashes`. Zrzut zapisujemy jako artefakt `page_screenshot` i pokazujemy przez `GET /api/artifacts/{sha}/image`. HTML oszusta nigdy nie jest renderowany w interfejsie. Cloaking wykrywa istniejący `white_dom_hash`: różnica między renderem dla ofiary i dla automatu.

Backend wybiera przeglądarkę ustawieniem `CRAWLER_FETCHER=crawler.browser.BrowserFetcher` (domyślne w `.env.example`). Gdy usługa nie odpowiada, wraca do klienta HTTP, a zdarzenie `crawl/info` ma `engine: "http"` i notatkę.

## Izolacja

```
worker ──(sieć crawl, wewnętrzna)──> crawler (Chromium)
                                        │ jedyna droga na zewnątrz
                                        v
                               crawler-egress (proxy) ──(sieć egress)──> internet
```

- Sieć `crawl` jest `internal: true`: kontener z przeglądarką nie ma wyjścia do internetu ani do hosta i nie widzi bazy, magazynu dowodów, kolejek ani API backendu. Z crawlerem rozmawia tylko worker.
- Wszystkie połączenia przeglądarki idą przez proxy `crawler-egress`. Proxy rozwiązuje nazwę raz, odrzuca każdy adres niepubliczny (pętla zwrotna, sieci prywatne, link-local, metadane chmury), wpuszcza tylko porty 80, 443, 8080, 8443 i łączy się z tym sprawdzonym adresem. Sprawdzenie obejmuje przekierowania 3xx, żądania skryptów i WebSockety, a podmiana DNS po sprawdzeniu nic nie daje.
- Kontener bez uprawnień (`cap_drop: ALL`, `no-new-privileges`, system plików tylko do odczytu, limit pamięci i procesów). Service workery i pobieranie plików wyłączone. Limit czasu, liczby żądań, przejść i rozmiaru HAR.

Sprawdzone 21.11.2026 na Docker Desktop (Windows):
- render `https://example.com/` przez BrowserFetcher z kontenera backendu: status 200, HAR z adresem serwera, zrzut PNG;
- z kontenera crawler bez proxy: brak DNS dla `db`, `s3`, `backend` i internetu, brak połączenia z hostem (`host.docker.internal:8010`) i adresem publicznym;
- przez proxy: 403 dla `host.docker.internal:8010`, `169.254.169.254` i `crawler:8000`, 200 dla `example.com`;
- `python check_guard.py` w obrazie: przekierowanie 302, fetch i skok skryptowy pod adres lokalny zablokowane, port sekretny bez żadnego żądania.

Czego nie ma: wyjścia przez polski adres domowy lub mobilny (`CRAWLER_PROXY` działa tylko dla klienta HTTP), zachowania ludzkiego (ruch myszy, przewijanie) i omijania CAPTCHA. Strony, które wykrywają automat po odcisku przeglądarki, mogą pokazać białą stronę obu profilom.
