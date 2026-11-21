"""Sprawdzenie ochrony przed SSRF w usłudze crawler, bez sieci zewnętrznej.

Stawia lokalną stronę, która próbuje dostać się do drugiego lokalnego portu na trzy sposoby:
przekierowaniem 302, żądaniem fetch ze skryptu i przekierowaniem skryptowym. Na czas próby
dopuszcza jako "publiczny" wyłącznie port strony startowej. Skok skryptowy pod adres lokalny
zatrzymuje już sam Chromium (Local Network Access), fetch i 302 zatrzymuje proxy. Warunek: sekretny
port nie dostaje ani jednego żądania.

Uruchomienie: uv run --no-project --with playwright==1.65.2 python crawler/check_guard.py
(albo w kontenerze: docker compose run --rm crawler python check_guard.py)
"""

import socket
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import server


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


START, SECRET = free_port(), free_port()
SECRET_HITS: list[str] = []


class Start(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", f"http://127.0.0.1:{SECRET}/via-302")
            self.end_headers()
            return
        body = (
            f"<html><body><h1>start</h1><script>"
            f"fetch('http://localhost:{SECRET}/via-fetch').catch(() => console.log('fetch zablokowany'));"
            f"setTimeout(() => location = 'http://127.0.0.1:{SECRET}/via-js', 200);"
            f"</script></body></html>"
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class Secret(Start):
    def do_GET(self):
        SECRET_HITS.append(self.path)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"SEKRET")


real = server.resolve_public


def resolve_for_test(host: str, port: int) -> str:
    if host == "127.0.0.1" and port == START:
        return "127.0.0.1"
    return real(host, port)


def main() -> int:
    server.resolve_public = resolve_for_test
    for handler, port in ((Start, START), (Secret, SECRET)):
        threading.Thread(target=ThreadingHTTPServer(("127.0.0.1", port), handler).serve_forever, daemon=True).start()
    server.start_proxy()
    renderer = server.Renderer()
    failures = []
    for path in ("/", "/redirect"):
        result = renderer.render(f"http://127.0.0.1:{START}{path}", "victim")
        print(path, "final:", result["final_url"], "status:", result["status"], "blocked:", result["blocked"], "error:", result["error"][:120])
        if not result["blocked"] and "chrome-error" not in result["final_url"]:
            failures.append(f"{path}: brak blokady")
        if "SEKRET" in result["html"]:
            failures.append(f"{path}: strona sekretna w HTML")
    if SECRET_HITS:
        failures.append(f"sekretny port dostał żądania: {SECRET_HITS}")
    print("OK: wszystkie próby zablokowane" if not failures else "BŁĄD: " + "; ".join(failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
