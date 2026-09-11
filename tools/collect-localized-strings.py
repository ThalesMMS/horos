#!/usr/bin/env python3
"""List NSLocalizedString keys used by the current host sources.

Menu titles are a subset of this list; tools/collect-menu-strings.py stays the
check for titles built in code. This collector is the catalog contract for
alerts, progress, preferences and the rest of the host flow.
"""
import argparse
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TREES = (
    ROOT / "Horos/Sources",
    ROOT / "Preference Panes",
    ROOT / "Nitrogen/Sources",
)

OBJC = re.compile(
    r'NSLocalizedString(?:FromTable)?\(\s*@"((?:\\.|[^"\\])*)"', re.S)
SWIFT = re.compile(r'NSLocalizedString\(\s*"((?:\\.|[^"\\])*)"', re.S)


def keys():
    found = {}
    for tree in TREES:
        if not tree.exists():
            continue
        for path in sorted(tree.rglob("*")):
            if path.suffix not in {".m", ".mm", ".h", ".swift"}:
                continue
            raw = path.read_bytes()
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                text = raw.decode("latin1")
            pattern = SWIFT if path.suffix == ".swift" else OBJC
            for match in pattern.finditer(text):
                line = text.rfind("\n", 0, match.start()) + 1
                if text[line:match.start()].lstrip().startswith("//"):
                    continue
                try:
                    key = json.loads('"' + match[1] + '"')
                except ValueError:
                    continue
                if key:
                    found.setdefault(key, path.name)
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
    found = keys()
    if not arguments.check:
        for key, source in sorted(found.items()):
            print(f"{key}\t{source}")
        return
    missing = {}
    for language in languages:
        present = catalog(language)
        absent = sorted(key for key in found if key not in present)
        if absent:
            missing[language] = absent
    if missing:
        for language, absent in missing.items():
            for key in absent:
                print(f"{language}: {key!r} ({found[key]}) is not in the catalog")
        raise SystemExit(
            "Host NSLocalizedString keys must be catalog entries, or they stay "
            "English. Add them, or document a residual English value.")
    print(f"{len(found)} source keys present in {', '.join(languages)}")


if __name__ == "__main__":
    main()
