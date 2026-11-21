#!/usr/bin/env python3
"""Weryfikacja pakietu dowodowego SCAM DNA. Tylko biblioteka standardowa Pythona (3.8 albo nowszy).

Użycie, z katalogu pakietu albo z podaniem go jako argumentu:

    python weryfikuj.py
    python weryfikuj.py /ścieżka/do/rozpakowanego/pakietu

Skrypt sprawdza dwie rzeczy:
1. SHA256SUMS: każdy wymieniony plik istnieje i ma podaną sumę SHA-256, a w katalogu nie ma plików spoza listy.
2. manifest.json: każdy dowód z katalogu dowody/ istnieje, ma zgodny rozmiar i sumę SHA-256, a nazwa pliku zaczyna się
   od tej sumy (plik jest adresowany swoją treścią). Pliki wygenerowane razem z pakietem (raport, STIX, krawędzie,
   oś czasu) też mają w manifeście sumy.

Kod wyjścia: 0 gdy wszystko się zgadza, 1 gdy cokolwiek się nie zgadza, 2 gdy nie da się odczytać SHA256SUMS albo
manifestu. Skrypt niczego nie zmienia ani nie pobiera z sieci. Pliki z katalogu dowody/surowe/ są tylko czytane
jako bajty: skrypt ich nie otwiera w przeglądarce ani nie wykonuje.
"""

import hashlib
import json
import os
import sys

SUMS = "SHA256SUMS"
MANIFEST = "manifest.json"


def sha256_of(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_path(root, relative):
    """Ścieżka z listy musi zostać w katalogu pakietu. Bez bezwzględnych i bez wyjść przez `..`."""
    if not relative or relative.startswith(("/", "\\")) or ":" in relative.split("/")[0]:
        return None
    full = os.path.normpath(os.path.join(root, *relative.split("/")))
    root_abs = os.path.abspath(root)
    if os.path.abspath(full) != root_abs and not os.path.abspath(full).startswith(root_abs + os.sep):
        return None
    return full


def read_sums(root, problems):
    path = os.path.join(root, SUMS)
    entries = {}
    with open(path, encoding="utf-8") as handle:
        for number, line in enumerate(handle, 1):
            line = line.rstrip("\n")
            if not line.strip():
                continue
            digest, sep, relative = line.partition("  ")
            if not sep or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
                problems.append(f"{SUMS}, wiersz {number}: zły format")
                continue
            entries[relative] = digest
    return entries


def all_files(root):
    found = set()
    for folder, _dirs, names in os.walk(root):
        for name in names:
            relative = os.path.relpath(os.path.join(folder, name), root).replace(os.sep, "/")
            found.add(relative)
    return found


def check_sums(root, entries, problems):
    checked = 0
    for relative, expected in sorted(entries.items()):
        full = safe_path(root, relative)
        if full is None:
            problems.append(f"{SUMS}: niedozwolona ścieżka {relative!r}")
            continue
        if not os.path.isfile(full):
            problems.append(f"BRAK PLIKU: {relative}")
            continue
        actual = sha256_of(full)
        checked += 1
        if actual != expected:
            problems.append(f"ZŁA SUMA: {relative} (jest {actual}, ma być {expected})")
    for relative in sorted(all_files(root) - set(entries) - {SUMS}):
        problems.append(f"PLIK SPOZA LISTY: {relative} (nie ma go w {SUMS})")
    return checked


def check_manifest(root, manifest, sums, problems):
    checked = 0
    for item in manifest.get("pliki", []):
        relative = item.get("sciezka", "")
        full = safe_path(root, relative)
        if full is None or not os.path.isfile(full):
            problems.append(f"MANIFEST: brak pliku {relative}")
            continue
        digest = item.get("sha256", "")
        if os.path.basename(relative).split(".")[0] != digest:
            problems.append(f"MANIFEST: nazwa pliku {relative} nie zaczyna się od jego sumy")
        if os.path.getsize(full) != item.get("rozmiar"):
            problems.append(f"MANIFEST: zły rozmiar {relative} (jest {os.path.getsize(full)}, ma być {item.get('rozmiar')})")
        actual = sha256_of(full)
        checked += 1
        if actual != digest:
            problems.append(f"MANIFEST: zła suma {relative} (jest {actual}, ma być {digest})")
        if sums.get(relative) != digest:
            problems.append(f"MANIFEST: suma {relative} różni się od wpisu w {SUMS}")
    for item in manifest.get("pliki_pakietu", []):
        relative = item.get("sciezka", "")
        full = safe_path(root, relative)
        if full is None or not os.path.isfile(full):
            problems.append(f"MANIFEST: brak pliku {relative}")
            continue
        checked += 1
        if sha256_of(full) != item.get("sha256"):
            problems.append(f"MANIFEST: zła suma {relative}")
    return checked


def main(argv):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    root = argv[1] if len(argv) > 1 else os.path.dirname(os.path.abspath(__file__))
    problems = []
    try:
        entries = read_sums(root, problems)
        with open(os.path.join(root, MANIFEST), encoding="utf-8") as handle:
            manifest = json.load(handle)
    except (OSError, ValueError) as exc:
        print(f"Nie da się odczytać {SUMS} albo {MANIFEST}: {exc}")
        return 2
    sums_checked = check_sums(root, entries, problems)
    manifest_checked = check_manifest(root, manifest, entries, problems)
    skipped = manifest.get("pominiete", [])
    print("Pakiet: {}".format(manifest.get("grupa", {}).get("klucz", "?")))
    print(f"{SUMS}: sprawdzono {sums_checked} plików")
    print(f"{MANIFEST}: sprawdzono {manifest_checked} plików")
    if skipped:
        print(f"Pominięte przy tworzeniu pakietu (to nie błąd, powody w manifeście): {len(skipped)}")
    if problems:
        print("")
        print(f"NIEZGODNOŚCI ({len(problems)}):")
        for problem in problems:
            print(" - " + problem)
        return 1
    print("")
    print("WYNIK: ZGODNE. Zawartość pakietu jest taka, jak w chwili jego utworzenia.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
