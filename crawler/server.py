"""Usługa renderująca strony docelowe w Chromium (Playwright).

Działa w osobnym kontenerze i osobnej sieci Dockera, bez dostępu do bazy, magazynu dowodów i kolejek.
Backend woła `POST /render {"url": ..., "profile": "victim"|"bot"}` i dostaje:
łańcuch przejść (przekierowania HTTP i skryptowe), HTML po wykonaniu skryptów, HAR z treścią odpowiedzi,
zrzut ekranu PNG (base64), komunikaty konsoli i listę zablokowanych żądań.

Ochrona przed SSRF: przeglądarka łączy się wyłącznie przez serwer pośredniczący (proxy),
który dla każdego połączenia rozwiązuje nazwę raz, odrzuca adresy niepubliczne i łączy się z tym
sprawdzonym adresem. Dzięki temu sprawdzenie obejmuje też przekierowania, WebSockety i żądania
skryptów, a podmiana DNS między sprawdzeniem a połączeniem nic nie daje.

W compose proxy działa w osobnym kontenerze (`python server.py --proxy-only`, usługa `crawler-egress`),
a kontener z przeglądarką siedzi w sieci wewnętrznej bez wyjścia na zewnątrz. Nawet przejęty Chromium
nie ma wtedy innej drogi niż przez proxy.
"""

import base64
import ipaddress
import json
import os
import select
import sys
import urllib.request
import socket
import socketserver
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

PORT = int(os.environ.get("PORT", "8000"))
PROXY_PORT = int(os.environ.get("GUARD_PROXY_PORT", "3128"))
# Adres proxy ochronnego. Pusty: proxy w tym samym procesie (praca lokalna). W compose osobny kontener `crawler-egress`.
PROXY_URL = os.environ.get("GUARD_PROXY_URL", "")
RENDER_TIMEOUT_MS = int(float(os.environ.get("RENDER_TIMEOUT_S", "20")) * 1000)
SETTLE_MS = int(os.environ.get("RENDER_SETTLE_MS", "3000"))
MAX_REQUESTS = int(os.environ.get("RENDER_MAX_REQUESTS", "250"))
MAX_NAVIGATIONS = int(os.environ.get("RENDER_MAX_NAVIGATIONS", "10"))
MAX_CONN_BYTES = int(os.environ.get("RENDER_MAX_CONN_BYTES", str(25 * 1024 * 1024)))
MAX_HAR_BYTES = int(os.environ.get("RENDER_MAX_HAR_BYTES", str(30 * 1024 * 1024)))
MAX_HTML_BYTES = int(os.environ.get("RENDER_MAX_HTML_BYTES", str(3 * 1024 * 1024)))
ALLOWED_PORTS = {80, 443, 8080, 8443}

# Te same profile co w backend/crawler/fetch.py: telefon z przeglądarką w aplikacji Facebooka i jawny automat.
PROFILES = {
    "victim": {
        "user_agent": "Mozilla/5.0 (Linux; Android 14; SM-A546B) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Mobile Safari/537.36 [FB_IAB/FB4A;FBAV/489.0.0.66.81;]",
        "locale": "pl-PL",
        "timezone_id": "Europe/Warsaw",
        "viewport": {"width": 412, "height": 915},
        "device_scale_factor": 2,
        "is_mobile": True,
        "has_touch": True,
        "extra_http_headers": {"Accept-Language": "pl-PL,pl;q=0.9", "Referer": "https://l.facebook.com/"},
    },
    "bot": {
        "user_agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) HeadlessChrome/131.0.0.0 Safari/537.36",
        "locale": "en-US",
        "viewport": {"width": 1280, "height": 900},
        "extra_http_headers": {"Accept-Language": "en-US,en;q=0.9"},
    },
}


class Blocked(ValueError):
    pass


def resolve_public(host: str, port: int) -> str:
    """Jeden adres publiczny dla nazwy albo wyjątek. Odmawiamy, gdy którykolwiek adres z DNS jest niepubliczny."""
    if not host or port not in ALLOWED_PORTS:
        raise Blocked(f"niedozwolony cel {host}:{port}")
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise Blocked(f"nie można rozwiązać {host}") from exc
    addresses = [ipaddress.ip_address(info[4][0]) for info in infos]
    if not addresses:
        raise Blocked(f"nie można rozwiązać {host}")
    for ip in addresses:
        if not ip.is_global:
            raise Blocked(f"{host} prowadzi do sieci niepublicznej ({ip})")
    return str(addresses[0])


# Ostatnio sprawdzone adresy hostów. Wpisujemy je do HAR, bo przeglądarka widzi tylko adres proxy.
RESOLVED: dict[str, str] = {}
BLOCKED: list[str] = []
_lock = threading.Lock()


def pipe(a: socket.socket, b: socket.socket) -> None:
    total = 0
    sockets = [a, b]
    while total < MAX_CONN_BYTES:
        readable, _, errored = select.select(sockets, [], sockets, 30)
        if errored or not readable:
            return
        for source in readable:
            data = source.recv(65536)
            if not data:
                return
            (b if source is a else a).sendall(data)
            total += len(data)


class GuardProxy(socketserver.StreamRequestHandler):
    """Proxy HTTP z CONNECT. Tylko publiczne adresy, tylko typowe porty, połączenie z przypiętym adresem."""

    def handle(self) -> None:
        head = b""
        while b"\r\n\r\n" not in head and len(head) < 65536:
            chunk = self.connection.recv(4096)
            if not chunk:
                return
            head += chunk
        header_bytes, _, rest = head.partition(b"\r\n\r\n")
        lines = header_bytes.decode("latin-1").split("\r\n")
        try:
            method, target, version = lines[0].split(" ", 2)
        except ValueError:
            return
        if method == "GET" and target == "/resolved":
            # Adresy sprawdzone przez proxy, do HAR. Przeglądarka widzi tylko adres proxy.
            with _lock:
                body = json.dumps(RESOLVED).encode()
            head = f"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\nContent-Length: {len(body)}\r\n\r\n"
            self.connection.sendall(head.encode("ascii") + body)
            return
        if method == "CONNECT":
            host, _, port = target.rpartition(":")
            host, port = host.strip("[]"), int(port or 443)
        else:
            parts = urlsplit(target)
            if parts.scheme != "http":
                return self.refuse(f"schemat {parts.scheme}")
            host, port = parts.hostname or "", parts.port or 80
        try:
            ip = resolve_public(host, port)
            upstream = socket.create_connection((ip, port), timeout=15)
        except (Blocked, OSError) as exc:
            with _lock:
                BLOCKED.append(f"{host}:{port} {exc}")
            return self.refuse(str(exc))
        with _lock:
            RESOLVED[host.lower()] = ip
        with upstream:
            if method == "CONNECT":
                self.connection.sendall(b"HTTP/1.1 200 Connection established\r\n\r\n")
                if rest:
                    upstream.sendall(rest)
            else:
                parts = urlsplit(target)
                path = parts.path or "/"
                if parts.query:
                    path += "?" + parts.query
                kept = [line for line in lines[1:] if line.split(":", 1)[0].strip().lower() not in ("proxy-connection", "connection", "keep-alive")]
                request = "\r\n".join([f"{method} {path} {version}", *kept, "Connection: close", "", ""]).encode("latin-1")
                upstream.sendall(request + rest)
            pipe(self.connection, upstream)

    def refuse(self, reason: str) -> None:
        body = f"zablokowane: {reason}".encode()
        self.connection.sendall(b"HTTP/1.1 403 Forbidden\r\nContent-Type: text/plain\r\nConnection: close\r\nContent-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body)


class ThreadingProxy(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True


def start_proxy(host: str = "127.0.0.1", block: bool = False) -> None:
    server = ThreadingProxy((host, PROXY_PORT), GuardProxy)
    if block:
        server.serve_forever()
    threading.Thread(target=server.serve_forever, daemon=True).start()


def proxy_url() -> str:
    return PROXY_URL or f"http://127.0.0.1:{PROXY_PORT}"


def resolved_hosts() -> dict:
    if not PROXY_URL:
        with _lock:
            return dict(RESOLVED)
    try:
        with urllib.request.urlopen(f"{PROXY_URL}/resolved", timeout=5) as response:
            return json.loads(response.read())
    except (OSError, ValueError):
        return {}


def check_url(url: str) -> None:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise Blocked(f"niedozwolony adres: {url}")
    if PROXY_URL:
        # Kontener renderujący nie ma DNS do internetu. Adres sprawdzi proxy przy połączeniu.
        port = parts.port or (443 if parts.scheme == "https" else 80)
        if port not in ALLOWED_PORTS:
            raise Blocked(f"niedozwolony cel {parts.hostname}:{port}")
        return
    resolve_public(parts.hostname, parts.port or (443 if parts.scheme == "https" else 80))


def fix_har(har: dict) -> dict:
    """Adres serwera z proxy zamiast 127.0.0.1 i przycięcie treści, gdy HAR przekracza limit."""
    entries = har.get("log", {}).get("entries", [])
    resolved = resolved_hosts()
    for entry in entries:
        host = (urlsplit(entry["request"]["url"]).hostname or "").lower()
        entry["serverIPAddress"] = resolved.get(host, "")
        entry.pop("_serverPort", None)
    size = len(json.dumps(har))
    if size > MAX_HAR_BYTES:
        # Najpierw wylatują największe treści, typowo obrazy i wideo.
        for entry in sorted(entries, key=lambda e: len(e["response"]["content"].get("text") or ""), reverse=True):
            content = entry["response"]["content"]
            size -= len(content.get("text") or "")
            content.pop("text", None)
            content["comment"] = "treść pominięta: limit rozmiaru HAR"
            if size <= MAX_HAR_BYTES:
                break
    return har


class Renderer:
    def __init__(self) -> None:
        self._pw = sync_playwright().start()
        self._browser = None

    def browser(self):
        if self._browser is None or not self._browser.is_connected():
            self._browser = self._pw.chromium.launch(
                headless=True,
                proxy={"server": proxy_url()},
                args=["--disable-dev-shm-usage", "--proxy-bypass-list=<-loopback>", "--disable-quic"],
            )
        return self._browser

    def render(self, url: str, profile: str) -> dict:
        result = {"profile": profile, "engine": "browser", "chain": [], "final_url": url, "status": 0, "content_type": "",
                  "html": "", "har": None, "screenshot": "", "console": [], "blocked": [], "error": ""}
        try:
            check_url(url)
        except Blocked as exc:
            result["error"] = f"BlockedUrl: {exc}"
            return result
        with _lock:
            blocked_before = len(BLOCKED)
        workdir = Path(tempfile.mkdtemp(prefix="render-"))
        har_path = workdir / "page.har"
        context = self.browser().new_context(
            **PROFILES[profile],
            ignore_https_errors=True,
            service_workers="block",
            accept_downloads=False,
            record_har_path=str(har_path),
            record_har_content="embed",
        )
        requests = {"count": 0}
        chain: list[dict] = []

        def guard(route, request):
            requests["count"] += 1
            scheme = urlsplit(request.url).scheme
            if scheme in ("data", "blob"):
                return route.continue_()
            if scheme not in ("http", "https") or requests["count"] > MAX_REQUESTS:
                result["blocked"].append(request.url[:300])
                return route.abort("blockedbyclient")
            return route.continue_()

        def on_response(response):
            request = response.request
            if request.is_navigation_request() and request.frame.parent_frame is None:
                # Pierwsze wejście i przekierowania 3xx to HTTP, każde kolejne przejście ramki głównej robi skrypt albo meta refresh.
                via = "http" if request.redirected_from or not chain else "js"
                chain.append({"url": request.url, "status": response.status, "via": via})

        try:
            context.route("**/*", guard)
            page = context.new_page()
            page.on("console", lambda m: len(result["console"]) < 50 and result["console"].append(f"{m.type}: {m.text[:300]}"))
            page.on("response", on_response)
            response = page.goto(url, wait_until="load", timeout=RENDER_TIMEOUT_MS)
            deadline = time.monotonic() + RENDER_TIMEOUT_MS / 1000
            seen = page.url
            for _ in range(MAX_NAVIGATIONS):
                page.wait_for_timeout(SETTLE_MS)
                if page.url == seen or time.monotonic() > deadline:
                    break
                seen = page.url
                try:
                    page.wait_for_load_state("load", timeout=max(1000, int((deadline - time.monotonic()) * 1000)))
                except PlaywrightError:
                    break
            result["final_url"] = page.url
            last = next((h for h in reversed(chain) if h["url"] == page.url), None)
            result["status"] = last["status"] if last else (response.status if response else 0)
            result["content_type"] = "text/html; charset=utf-8"
            html = page.content().encode("utf-8")[:MAX_HTML_BYTES]
            result["html"] = html.decode("utf-8", errors="ignore")
            result["screenshot"] = base64.b64encode(page.screenshot(type="png", timeout=10000)).decode("ascii")
        except PlaywrightError as exc:
            result["error"] = f"BrowserError: {str(exc).splitlines()[0][:300]}"
            try:
                result["final_url"] = page.url
            except Exception:  # noqa: BLE001 - strona mogła już zniknąć
                pass
        finally:
            try:
                context.close()  # zapisuje HAR
            except PlaywrightError:
                pass
        # Jeden następujący po sobie skok skryptowy pod ten sam adres to przeładowanie, nie przekierowanie.
        result["chain"] = [h for i, h in enumerate(chain) if i == 0 or h["url"] != chain[i - 1]["url"]]
        if har_path.is_file():
            try:
                result["har"] = fix_har(json.loads(har_path.read_text(encoding="utf-8")))
            except ValueError:
                result["har"] = None
        for item in workdir.iterdir():
            item.unlink()
        workdir.rmdir()
        with _lock:
            result["blocked"] += BLOCKED[blocked_before:]
            del BLOCKED[:-200]
        return result


RENDERER: Renderer | None = None
RENDER_LOCK = threading.Lock()


class Api(BaseHTTPRequestHandler):
    def _send(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/health":
            return self._send(200, {"ok": True})
        self._send(404, {"error": "nie ma"})

    def do_POST(self) -> None:
        if self.path != "/render":
            return self._send(404, {"error": "nie ma"})
        try:
            length = min(int(self.headers.get("Content-Length") or 0), 65536)
            data = json.loads(self.rfile.read(length) or b"{}")
            url, profile = str(data["url"]), str(data.get("profile") or "victim")
        except (ValueError, KeyError):
            return self._send(400, {"error": "oczekuję {\"url\": ..., \"profile\": victim|bot}"})
        if profile not in PROFILES:
            return self._send(400, {"error": f"nieznany profil {profile}"})
        with RENDER_LOCK:  # Playwright w trybie synchronicznym: jedna strona naraz
            self._send(200, RENDERER.render(url, profile))

    def log_message(self, fmt: str, *args) -> None:
        print(f"{self.address_string()} {fmt % args}", flush=True)


def main() -> None:
    global RENDERER
    if "--proxy-only" in sys.argv:
        print(f"crawler-egress: proxy ochronne na 0.0.0.0:{PROXY_PORT}", flush=True)
        return start_proxy("0.0.0.0", block=True)
    if not PROXY_URL:
        start_proxy()
    RENDERER = Renderer()
    print(f"crawler: render na :{PORT}, proxy ochronne {proxy_url()}", flush=True)
    HTTPServer(("0.0.0.0", PORT), Api).serve_forever()


if __name__ == "__main__":
    main()
