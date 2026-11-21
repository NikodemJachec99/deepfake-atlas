"""Uruchomienie całej aplikacji jednym poleceniem: python scripts/start.py

Kroki (każdy można pominąć flagą):
1. `.env` z `.env.example`, jeśli go nie ma.
2. `docker compose up -d --build` i czekanie, aż backend odpowie.
3. Baza referencyjna osób, harmonogramy Temporala (wstrzymane), opcjonalnie Lista Ostrzeżeń CERT Polska.
4. Import każdej paczki z `data/raw/<nazwa>/` (nazwa katalogu = nazwa paczki), o ile jeszcze jej nie ma.
5. Adresy interfejsu i API.

Działa tak samo na Windowsie, Linuksie i macOS (sam Python ze standardowej biblioteki i Docker z Compose).
"""

import argparse
import json
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def env_value(name: str, default: str) -> str:
    env = ROOT / ".env"
    if env.is_file():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith(f"{name}="):
                return line.split("=", 1)[1].strip() or default
    return default


def compose(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    cmd = ["docker", "compose", *args]
    print("$ " + " ".join(cmd), flush=True)
    return subprocess.run(cmd, cwd=ROOT, check=check)


def manage(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    # -T: bez terminala, działa też w skryptach i na Windowsie.
    return compose("exec", "-T", "backend", "python", "manage.py", *args, check=check)


def get_json(url: str) -> dict | None:
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            return json.loads(response.read())
    except (OSError, ValueError):
        return None


def wait_for(url: str, seconds: int) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if get_json(url) is not None:
            return True
        time.sleep(3)
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--no-build", action="store_true", help="bez przebudowy obrazów")
    parser.add_argument("--cert", action="store_true", help="wczytaj Listę Ostrzeżeń CERT Polska (ok. 127 tys. domen, wymaga internetu)")
    parser.add_argument("--no-import", action="store_true", help="bez importu paczek z data/raw/")
    parser.add_argument("--skan", action="store_true", help="zostaw włączone cykliczne skany bibliotek reklam (domyślnie wstrzymane, korpus się nie zmienia)")
    parser.add_argument("--wait", type=int, default=600, help="ile sekund czekać na backend (domyślnie 600)")
    args = parser.parse_args()

    if shutil.which("docker") is None:
        print("Brak polecenia docker. Zainstaluj Docker z Compose.", file=sys.stderr)
        return 1
    env = ROOT / ".env"
    if not env.is_file():
        shutil.copyfile(ROOT / ".env.example", env)
        print("Utworzono .env z .env.example")

    compose("up", "-d", *([] if args.no_build else ["--build"]))
    api = f"http://localhost:{env_value('BACKEND_PORT', '8000')}"
    ui = f"http://localhost:{env_value('FRONTEND_PORT', '3000')}"
    print(f"Czekam na backend pod {api}/health ...", flush=True)
    if not wait_for(f"{api}/health", args.wait):
        print("Backend nie odpowiada. Sprawdź: docker compose logs backend", file=sys.stderr)
        return 1

    manage("seed_people")
    manage("ensure_schedules", check=False)
    if not args.skan:
        # Skany bibliotek dokładają reklamy co kilka godzin. Bez --skan korpus zostaje taki, jak po imporcie.
        manage("ensure_schedules", "--pause", check=False)
    if args.cert:
        manage("collect", "cert_pl")

    if not args.no_import:
        raw = ROOT / "data" / "raw"
        bundles = sorted(p for p in raw.iterdir() if p.is_dir()) if raw.is_dir() else []
        if not bundles:
            print("W data/raw/ nie ma paczek. Rozpakuj paczkę do data/raw/<nazwa>/ i uruchom ponownie albo wgraj sprawy w interfejsie (Zgłoś materiał).")
        for bundle in bundles:
            probe = f"from ads.models import Ad; raise SystemExit(0 if Ad.objects.filter(external_id__startswith='{bundle.name}/').exists() else 3)"
            if manage("shell", "-c", probe, check=False).returncode == 0:
                print(f"Paczka {bundle.name} już jest w bazie, pomijam.")
                continue
            # Ścieżka w kontenerze: katalog data/ jest zamontowany jako /data.
            manage("import_bundle", f"/data/raw/{bundle.name}", "--name", bundle.name)

    stats = get_json(f"{api}/api/stats") or {}
    print()
    print(f"Interfejs: {ui}")
    print(f"API:       {api}/api/  (dokumentacja: {api}/api/docs/)")
    if stats:
        print(f"Korpus:    reklamy {stats.get('ads', '?')}, kampanie {stats.get('campaigns', '?')}, operatorzy {stats.get('operators', '?')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
