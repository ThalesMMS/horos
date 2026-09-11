#!/usr/bin/env python3
"""List the menu and button titles the sources build with NSLocalizedString.

A title that is not a key of a localized catalog stays English in that language,
whatever the rest of the menu does, and nothing else in the build says so: the
English catalog does not need the key, because NSLocalizedString falls back to
it. This is the list to check the catalogs against.
"""
import argparse
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "Horos/Sources"

# Product names that are the same in every language.
UNTRANSLATED = {"iPhoto", "Horos", "OsiriX", "DICOM", "PACS"}

# A title does not have to be written inside initWithTitle:. Two menu items
# added in 2026-09 held theirs in a local called `title` and were invisible to
# this check until the catalogs were already short of them, so a name ending in
# "title" counts as one too.
OBJC = re.compile(
    r'(?:initWithTitle:|setTitle:|itemWithTitle:|addItemWithTitle:'
    r'|\b\w*[Tt]itle\s*=)\s*'
    r'NSLocalizedString\(\s*@"((?:\\.|[^"\\])*)"', re.S)
SWIFT = re.compile(
    r'(?:\btitle\b\s*[:=]|\b\w*[Tt]itle\s*=|addItem\(withTitle:)\s*'
    r'NSLocalizedString\(\s*"((?:\\.|[^"\\])*)"', re.S)


def titles():
    """Every literal used as a menu or button title, with where it came from."""
    found = {}
    for path in sorted(SOURCES.rglob("*")):
        if path.suffix not in (".m", ".mm", ".swift"):
            continue
        # These sources are not all UTF-8, and the ones that are carry real
        # ellipses in their titles. Read the encoding each file actually uses.
        raw = path.read_bytes()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("latin1")
        pattern = SWIFT if path.suffix == ".swift" else OBJC
        for match in pattern.finditer(text):
            # A commented-out menu item builds nothing.
            line = text.rfind("\n", 0, match.start()) + 1
            if text[line:match.start()].lstrip().startswith("//"):
                continue
            try:
                title = json.loads('"' + match[1] + '"')
            except ValueError:
                continue
            if title and title not in UNTRANSLATED:
                found.setdefault(title, path.name)
    return found


def catalog(language):
    path = ROOT / f"Horos/Resources/{language}.lproj/Localizable.strings"
    return json.loads(subprocess.check_output(
        ["plutil", "-convert", "json", "-o", "-", str(path)]))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--language", action="append", default=None)
    arguments = parser.parse_args()
    languages = arguments.language or ["it-IT", "es"]
    found = titles()
    missing = {}
    for language in languages:
        keys = catalog(language)
        absent = sorted(title for title in found if title not in keys)
        if absent:
            missing[language] = absent
    if not arguments.check:
        for title, source in sorted(found.items()):
            print(f"{title}\t{source}")
        return
    if missing:
        for language, absent in missing.items():
            for title in absent:
                print(f"{language}: {title!r} ({found[title]}) is not in the catalog")
        raise SystemExit(
            "Menu titles built with NSLocalizedString must be catalog keys, or "
            "they stay English. Add them, or list a product name in UNTRANSLATED.")
    print(f"{len(found)} menu titles present in {', '.join(languages)}")


if __name__ == "__main__":
    main()
