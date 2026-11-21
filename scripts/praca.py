#!/usr/bin/env python3
"""Praca na dwóch komputerach bez dublowania.

Zadania to GitHub Issues. Kto bierze zadanie, dostaje na nim etykietę `robi:<rola>` i od tej chwili
drugi komputer go nie widzi. Jedno zadanie to jedna gałąź i jeden PR, mergowany po zielonym CI.

Wymaga tylko `git` i `gh` (zalogowanego). Działa na Windowsie i macOS.

    python scripts/praca.py start glowny|koder [--host IP] [--port 8000]
    python scripts/praca.py status
    python scripts/praca.py nastepne            bierze następne wolne zadanie tej maszyny albo wraca do rozpoczętego
    python scripts/praca.py oddaj -m "opis"     testy, push, PR, czeka na CI, merge
    python scripts/praca.py lista [--wszystkie]
    python scripts/praca.py biore N | puszczam N | pokaz N
    python scripts/praca.py blokada N "powód"
    python scripts/praca.py nowe "tytuł" --strefa frontend [--p0] [--opis "..."] [--zalezy 12,13]
"""

import argparse
import json
import re
import socket
import subprocess
import sys
import time
import unicodedata
import urllib.request
from pathlib import Path

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

ROLES = ("glowny", "koder")
# Strefy, z których dana maszyna bierze zadania. Główny ma moc na Dockera, import danych i modele.
ZONES = {"koder": ["frontend"], "glowny": ["backend", "dane", "infra", "docs"]}
# Pliki frontendu, które zmienia tylko główny: kontrakt API i budowanie kontenera.
MAIN_ONLY_IN_FRONTEND = ("frontend/src/lib/api.ts", "frontend/Dockerfile", "frontend/.dockerignore")
LABELS = {
    "robi:glowny": ("1d76db", "Zadanie w toku na komputerze głównym"),
    "robi:koder": ("0e8a16", "Zadanie w toku na komputerze do kodowania"),
    "strefa:frontend": ("c5def5", "frontend/"),
    "strefa:backend": ("fef2c0", "backend/"),
    "strefa:dane": ("f9d0c4", "dane, import, modele, ciężkie operacje"),
    "strefa:infra": ("d4c5f9", "compose, CI, uruchamianie"),
    "strefa:docs": ("e6e6e6", "dokumentacja, prezentacja"),
    "p0": ("b60205", "Musi być na demo"),
    "p1": ("fbca04", "Dobrze mieć"),
    "kontrakt": ("5319e7", "Zmienia kontrakt API"),
    "zablokowane": ("000000", "Nie da się ruszyć, powód w komentarzu"),
}
DEPENDS = re.compile(r"Zależy od:\s*([#\d,\s]+)", re.I)


def fail(message: str) -> None:
    print(f"STOP: {message}")
    sys.exit(1)


def run(*cmd: str, check: bool = True, cwd: Path | None = None, quiet: bool = False) -> str:
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=cwd or ROOT)
    if check and result.returncode != 0:
        fail(f"{' '.join(cmd)}\n{(result.stderr or result.stdout).strip()[:1500]}")
    if not quiet and result.returncode != 0:
        return (result.stdout + result.stderr).strip()
    return result.stdout.strip()


def ok(*cmd: str, cwd: Path | None = None) -> bool:
    return subprocess.run(cmd, capture_output=True, cwd=cwd or ROOT).returncode == 0


try:
    ROOT = Path(subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True).stdout.strip())
except (subprocess.CalledProcessError, FileNotFoundError):
    print("STOP: uruchom w katalogu repozytorium (potrzebny git)")
    sys.exit(1)
CONFIG = ROOT / ".maszyna"


def config() -> dict:
    if not CONFIG.exists():
        fail("ta maszyna nie ma roli. Uruchom: python scripts/praca.py start glowny  albo  start koder --host <IP głównego>")
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def role() -> str:
    return config()["rola"]


def issues(state: str = "open") -> list[dict]:
    raw = run("gh", "issue", "list", "--state", state, "--limit", "300", "--json", "number,title,labels,body")
    items = json.loads(raw or "[]")
    for item in items:
        item["labels"] = [label["name"] for label in item["labels"]]
    return items


def issue(number: int) -> dict:
    item = json.loads(run("gh", "issue", "view", str(number), "--json", "number,title,labels,body,state"))
    item["labels"] = [label["name"] for label in item["labels"]]
    return item


def owner(item: dict) -> str | None:
    return next((label.split(":", 1)[1] for label in item["labels"] if label.startswith("robi:")), None)


def zone(item: dict) -> str | None:
    return next((label.split(":", 1)[1] for label in item["labels"] if label.startswith("strefa:")), None)


def priority(item: dict) -> int:
    return 0 if "p0" in item["labels"] else 1 if "p1" in item["labels"] else 2


def depends_on(item: dict) -> list[int]:
    match = DEPENDS.search(item.get("body") or "")
    return [int(n) for n in re.findall(r"\d+", match.group(1))] if match else []


def free_for(me: str, everything: list[dict], all_zones: bool = False) -> list[dict]:
    open_numbers = {item["number"] for item in everything}
    out = []
    for item in everything:
        if owner(item) or "zablokowane" in item["labels"]:
            continue
        if not all_zones and zone(item) not in ZONES[me]:
            continue
        if any(dep in open_numbers for dep in depends_on(item)):
            continue  # czeka na inne zadanie
        out.append(item)
    return sorted(out, key=lambda i: (priority(i), i["number"]))


def slug(title: str) -> str:
    text = unicodedata.normalize("NFKD", title.replace("ł", "l").replace("Ł", "L")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40]


def branch_of(number: int) -> str | None:
    names = run("git", "branch", "-a", "--format=%(refname:short)").splitlines()
    for name in names:
        short = name.removeprefix("origin/")
        if re.match(rf"^z{number}-", short):
            return short
    return None


def current_branch() -> str:
    return run("git", "rev-parse", "--abbrev-ref", "HEAD")


def task_of_branch(branch: str) -> int | None:
    match = re.match(r"^z(\d+)-", branch)
    return int(match.group(1)) if match else None


def dirty() -> list[str]:
    return [line for line in run("git", "status", "--porcelain").splitlines() if line.strip()]


def show(item: dict) -> None:
    labels = " ".join(label for label in item["labels"] if not label.startswith("robi:"))
    print(f"\n#{item['number']} {item['title']}   [{labels}]")
    print("-" * 70)
    print((item.get("body") or "(bez opisu)").strip())
    print("-" * 70)


def lan_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("192.0.2.1", 80))
            return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"


# --- polecenia ---------------------------------------------------------------


def cmd_start(args) -> None:
    if not ok("gh", "auth", "status"):
        fail("gh nie jest zalogowany. Uruchom: gh auth login")
    data = {"rola": args.rola}
    if args.rola == "koder":
        if not args.host:
            fail("podaj adres komputera głównego: start koder --host 192.168.x.x")
        api = f"http://{args.host}:{args.port}"
        data.update(host=args.host, port=args.port)
        (ROOT / "frontend" / ".env.local").write_text(f"# Backend działa na komputerze głównym\nNEXT_PUBLIC_API_URL={api}\n", encoding="utf-8")
        try:
            with urllib.request.urlopen(f"{api}/health", timeout=5) as response:
                print(f"Backend na głównym odpowiada: {api}/health -> {response.status}")
        except OSError as exc:
            print(f"UWAGA: backend {api} nie odpowiada ({exc}).")
            print("  Sprawdź: oba komputery w tej samej sieci, zapora na głównym przepuszcza ten port, kontenery działają.")
            print("  Bez backendu da się pisać kod i robić build, ale nie da się sprawdzić ekranów na danych.")
    CONFIG.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for name, (color, description) in LABELS.items():
        run("gh", "label", "create", name, "--color", color, "--description", description, "--force", check=False, quiet=True)
    print(f"Rola tej maszyny: {args.rola}. Strefy: {', '.join(ZONES[args.rola])}.")
    if args.rola == "glowny":
        print(f"Adres tej maszyny w sieci lokalnej: {lan_ip()}  (na drugim komputerze: start koder --host {lan_ip()} --port <BACKEND_PORT>)")
    print("Dalej: python scripts/praca.py status")


def cmd_status(_args) -> None:
    me = role()
    run("git", "fetch", "origin", "--prune", check=False, quiet=True)
    everything = issues()
    mine = [i for i in everything if owner(i) == me]
    theirs = [i for i in everything if owner(i) not in (None, me)]
    behind = run("git", "rev-list", "--count", "HEAD..origin/main", check=False) or "0"
    print(f"Maszyna: {me} | gałąź: {current_branch()} | za main o {behind} commitów | niezapisane pliki: {len(dirty())}")
    print(f"\nW toku u mnie ({len(mine)}):")
    for item in mine:
        print(f"  #{item['number']} {item['title']}")
    print(f"\nW toku na drugim komputerze ({len(theirs)}), nie ruszaj:")
    for item in theirs:
        print(f"  #{item['number']} {item['title']}")
    free = free_for(me, everything)
    print(f"\nWolne dla mnie ({len(free)}), w kolejności brania:")
    for item in free[:8]:
        print(f"  #{item['number']} [{'p0' if priority(item) == 0 else 'p1' if priority(item) == 1 else '--'}] {item['title']}")
    blocked = [i for i in everything if "zablokowane" in i["labels"]]
    if blocked:
        print(f"\nZablokowane ({len(blocked)}): " + ", ".join(f"#{i['number']}" for i in blocked))


def cmd_lista(args) -> None:
    me = role()
    for item in free_for(me, issues(), all_zones=args.wszystkie):
        print(f"#{item['number']:<4} {'p0' if priority(item) == 0 else 'p1' if priority(item) == 1 else '--'}  {zone(item) or '?':<9} {item['title']}")


def claim(number: int) -> dict:
    me = role()
    item = issue(number)
    if item["state"] != "OPEN":
        fail(f"zadanie #{number} jest zamknięte")
    if owner(item) and owner(item) != me:
        fail(f"zadanie #{number} robi już {owner(item)}")
    if dirty():
        fail("masz niezapisane zmiany. Zrób commit albo je odłóż, potem weź zadanie.")
    run("gh", "issue", "edit", str(number), "--add-label", f"robi:{me}")
    # Oba komputery mogły kliknąć w tej samej sekundzie. Sprawdzamy stan po fakcie, główny ma pierwszeństwo.
    time.sleep(1)
    after = issue(number)
    owners = [label for label in after["labels"] if label.startswith("robi:")]
    if len(owners) > 1 and me != "glowny":
        run("gh", "issue", "edit", str(number), "--remove-label", f"robi:{me}")
        fail(f"zadanie #{number} w tej samej chwili wziął główny. Weź następne.")
    run("git", "fetch", "origin", "--prune", check=False, quiet=True)
    existing = branch_of(number)
    if existing:
        run("git", "switch", existing)
        run("git", "pull", "--ff-only", check=False, quiet=True)
    else:
        run("git", "switch", "-c", f"z{number}-{slug(item['title'])}", "origin/main")
    print(f"Wzięte: #{number}. Gałąź: {current_branch()}")
    show(after)
    return after


def cmd_biore(args) -> None:
    claim(args.numer)


def cmd_nastepne(_args) -> None:
    me = role()
    everything = issues()
    mine = sorted((i for i in everything if owner(i) == me), key=lambda i: i["number"])
    if mine:
        item = mine[0]
        print(f"Masz rozpoczęte zadanie #{item['number']}. Dokończ je, zanim weźmiesz kolejne.")
        existing = branch_of(item["number"])
        if existing and current_branch() != existing:
            if dirty():
                fail(f"jesteś na {current_branch()} z niezapisanymi zmianami, a zadanie #{item['number']} ma gałąź {existing}")
            run("git", "switch", existing)
        show(item)
        return
    free = free_for(me, everything)
    if not free:
        waiting = [i for i in everything if zone(i) in ZONES[me] and not owner(i)]
        print("BRAK ZADAŃ dla tej maszyny." + (f" Czeka {len(waiting)}: zablokowane albo zależne od zadań drugiego komputera." if waiting else ""))
        return
    claim(free[0]["number"])


def cmd_pokaz(args) -> None:
    show(issue(args.numer))


def cmd_puszczam(args) -> None:
    run("gh", "issue", "edit", str(args.numer), "--remove-label", f"robi:{role()}")
    print(f"Zadanie #{args.numer} wróciło do kolejki.")


def cmd_blokada(args) -> None:
    run("gh", "issue", "comment", str(args.numer), "--body", f"Zablokowane ({role()}): {args.powod}")
    run("gh", "issue", "edit", str(args.numer), "--add-label", "zablokowane", "--remove-label", f"robi:{role()}", check=False)
    print(f"Zadanie #{args.numer} oznaczone jako zablokowane.")


def cmd_nowe(args) -> None:
    body = (args.opis or "").strip()
    if args.zalezy:
        body += "\n\nZależy od: " + ", ".join(f"#{n.strip()}" for n in args.zalezy.split(","))
    labels = [f"strefa:{args.strefa}"] + (["p0"] if args.p0 else []) + (["p1"] if args.p1 else []) + (["kontrakt"] if args.kontrakt else [])
    url = run("gh", "issue", "create", "--title", args.tytul, "--body", body or "(bez opisu)", "--label", ",".join(labels))
    print(url)


def outside_zone(me: str, files: list[str]) -> list[str]:
    if me == "koder":
        return [f for f in files if not f.startswith("frontend/") or f in MAIN_ONLY_IN_FRONTEND]
    return [f for f in files if f.startswith("frontend/") and f not in MAIN_ONLY_IN_FRONTEND and not f.startswith("frontend/src/lib/")]


def local_checks(files: list[str]) -> None:
    if any(f.startswith("frontend/") for f in files):
        npm = "npm.cmd" if sys.platform == "win32" else "npm"
        for step in (["run", "lint"], ["run", "build"]):
            print(f"  frontend: npm {' '.join(step)}")
            result = subprocess.run([npm, *step], cwd=ROOT / "frontend", capture_output=True, text=True, encoding="utf-8", errors="replace")
            if result.returncode != 0:
                fail("frontend nie przechodzi:\n" + (result.stdout + result.stderr)[-2500:])
    if any(f.startswith("backend/") for f in files):
        python = next((p for p in (ROOT / "backend/.venv/Scripts/python.exe", ROOT / "backend/.venv/bin/python") if p.exists()), None)
        if python is None:
            print("  backend: brak .venv, testy zrobi CI")
            return
        for step in (["-m", "ruff", "check", "."], ["-m", "pytest", "-q"]):
            print(f"  backend: python {' '.join(step)}")
            result = subprocess.run([str(python), *step], cwd=ROOT / "backend", capture_output=True, text=True, encoding="utf-8", errors="replace")
            if result.returncode != 0:
                fail("backend nie przechodzi:\n" + (result.stdout + result.stderr)[-2500:])


def ci_disabled() -> bool:
    """Czy wszystkie workflow w repo są wyłączone (wtedy żadne checki nie przyjdą)."""
    states = run("gh", "workflow", "list", "--all", "--json", "state", "--jq", ".[].state", check=False, quiet=True).split()
    return bool(states) and all(state.startswith("disabled") for state in states)


def wait_for_ci(branch: str) -> None:
    print("Czekam na CI...")
    deadline = time.time() + 900
    while time.time() < deadline:
        checks = subprocess.run(["gh", "pr", "checks", branch, "--watch", "--interval", "10"], capture_output=True, text=True, cwd=ROOT)
        output = checks.stdout + checks.stderr
        if "no checks reported" in output:
            time.sleep(8)
            continue
        if checks.returncode != 0:
            fail("CI nie przeszło. Popraw i uruchom oddaj jeszcze raz.\n" + output[-1500:])
        return
    fail("CI nie skończyło się w 15 minut")


def cmd_oddaj(args) -> None:
    me = role()
    branch = current_branch()
    number = task_of_branch(branch)
    if number is None:
        fail(f"gałąź {branch} nie jest gałęzią zadania. Zacznij od: python scripts/praca.py nastepne")
    item = issue(number)
    if dirty():
        if not args.m:
            fail("są niezapisane zmiany. Podaj opis: oddaj -m \"po co ta zmiana\"")
        run("git", "add", "-A")
        run("git", "commit", "-m", args.m)
    run("git", "fetch", "origin", check=False, quiet=True)
    files = run("git", "diff", "--name-only", "origin/main...HEAD").splitlines()
    if not files:
        fail("gałąź nie ma żadnych zmian względem main")
    stray = outside_zone(me, files)
    if stray and not args.poza_strefa:
        fail("zmiany poza strefą tej maszyny:\n  " + "\n  ".join(stray[:15]) + "\nCofnij je albo, jeśli są konieczne, dodaj --poza-strefa")
    if not args.bez_testow:
        local_checks(files)
    merge = subprocess.run(["git", "merge", "--no-edit", "origin/main"], capture_output=True, text=True, cwd=ROOT)
    if merge.returncode != 0:
        fail("konflikt z main. Rozwiąż go, zrób commit i uruchom oddaj jeszcze raz.\n" + merge.stdout[-800:])
    run("git", "push", "-u", "origin", branch)
    if not ok("gh", "pr", "view", branch):
        run("gh", "pr", "create", "--base", "main", "--head", branch, "--title", item["title"], "--body", f"{args.m or item['title']}\n\nCloses #{number}")
    if args.bez_czekania:
        print("PR wystawiony, bez czekania na CI. Merge zrób ręcznie.")
        return
    if ci_disabled():
        # Decyzja użytkownika z 21.11: Actions wyłączone (billing). Wystarczą testy lokalne z local_checks.
        print("CI na GitHubie wyłączone, merguję po testach lokalnych.")
    else:
        wait_for_ci(branch)
    # Bez --delete-branch: gh próbuje wtedy przełączyć się lokalnie na main, a w worktree main bywa
    # wyciągnięty gdzie indziej. Gałęzie kasujemy sami, a w worktree wracamy na origin/main bez gałęzi.
    run("gh", "pr", "merge", branch, "--merge")
    run("gh", "issue", "edit", str(number), "--remove-label", f"robi:{me}", check=False, quiet=True)
    run("git", "push", "origin", "--delete", branch, check=False, quiet=True)
    run("git", "fetch", "origin", "--prune", check=False, quiet=True)
    if ok("git", "switch", "main"):
        run("git", "pull", "--ff-only", "origin", "main", check=False, quiet=True)
    else:
        run("git", "switch", "--detach", "origin/main", check=False, quiet=True)
    run("git", "branch", "-D", branch, check=False, quiet=True)
    print(f"ODDANE: #{number} {item['title']} jest w main.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Praca na dwóch komputerach bez dublowania")
    sub = parser.add_subparsers(dest="polecenie", required=True)
    p = sub.add_parser("start")
    p.add_argument("rola", choices=ROLES)
    p.add_argument("--host")
    p.add_argument("--port", default="8000")
    p.set_defaults(func=cmd_start)
    sub.add_parser("status").set_defaults(func=cmd_status)
    sub.add_parser("nastepne").set_defaults(func=cmd_nastepne)
    p = sub.add_parser("lista")
    p.add_argument("--wszystkie", action="store_true")
    p.set_defaults(func=cmd_lista)
    for name, func in (("biore", cmd_biore), ("pokaz", cmd_pokaz), ("puszczam", cmd_puszczam)):
        p = sub.add_parser(name)
        p.add_argument("numer", type=int)
        p.set_defaults(func=func)
    p = sub.add_parser("blokada")
    p.add_argument("numer", type=int)
    p.add_argument("powod")
    p.set_defaults(func=cmd_blokada)
    p = sub.add_parser("nowe")
    p.add_argument("tytul")
    p.add_argument("--strefa", required=True, choices=["frontend", "backend", "dane", "infra", "docs"])
    p.add_argument("--opis")
    p.add_argument("--zalezy")
    p.add_argument("--p0", action="store_true")
    p.add_argument("--p1", action="store_true")
    p.add_argument("--kontrakt", action="store_true")
    p.set_defaults(func=cmd_nowe)
    p = sub.add_parser("oddaj")
    p.add_argument("-m")
    p.add_argument("--poza-strefa", action="store_true")
    p.add_argument("--bez-testow", action="store_true")
    p.add_argument("--bez-czekania", action="store_true")
    p.set_defaults(func=cmd_oddaj)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
