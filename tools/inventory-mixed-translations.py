#!/usr/bin/env python3
"""Catalog values that are half translated: English words left inside a sentence (#638).

Some Spanish entries were made by replacing words one at a time, which leaves the
sentence half English - "The remote database index está empty." - and sometimes says
the opposite of the original: "Cannot decompress images in a distant database." came
out as "Sin se puede decompress images in a distant database."

A value is reported when it carries an English word that belongs to no Spanish
sentence: the function words and verbs below, whole words, case-insensitively. Values
that are the English sentence itself are not reported - a residual English value is
`tools/host-localization-residual.py`'s subject and `tests/test-localization-residual.py`
covers it.

    python3 tools/inventory-mixed-translations.py [--language es] [--check]

`--check` exits non-zero when anything is reported, and is what the test runs.
"""
import argparse
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# English words no Spanish sentence carries. Words both languages share (no, a, e, sin,
# total, error, final, series, ...) and technical names (DICOM, PACS, plugin) are not here.
ENGLISH_WORDS = {
    "the", "this", "that", "these", "those", "there", "their", "them", "they", "its",
    "is", "are", "was", "were", "be", "been", "being", "am",
    "have", "has", "had", "having", "do", "does", "did", "doing",
    "cannot", "can", "could", "would", "should", "shall", "will", "won't", "don't",
    "and", "or", "but", "if", "then", "else", "while", "when", "where", "which", "who", "whose",
    "with", "without", "from", "into", "onto", "about", "after", "before", "during", "between",
    "of", "in", "on", "to", "for", "at", "by", "as", "than", "too", "very", "only", "also",
    "not", "never", "always", "already", "again", "still", "yet", "more", "most", "less", "least",
    "some", "any", "all", "each", "every", "both", "other", "another", "such", "same",
    "you", "your", "yours", "we", "our", "ours", "it",
    "file", "files", "folder", "image", "images", "study", "studies", "database",
    "window", "windows", "server", "screen", "drive", "disc", "disk", "user", "users",
    "empty", "full", "available", "unavailable", "missing", "unknown", "current", "new", "old",
    "open", "opened", "close", "closed", "save", "saved", "saving", "load", "loaded", "loading",
    "delete", "deleted", "remove", "removed", "add", "added", "send", "sent", "receive", "received",
    "ignored", "belongs", "locating", "decompress", "failed", "failure", "success", "please",
    "select", "selected", "choose", "chosen", "click", "press", "wait", "waiting", "retry",
    "download", "downloading", "upload", "export", "import", "created", "creating", "written",
    "read", "reading", "write", "writing", "start", "started", "stop", "stopped", "finish",
    "filter", "filters", "name", "names", "list", "lists", "report", "reports", "album", "albums",
    "comment", "comments", "thumbnails", "values", "value", "type", "types", "level", "mode",
    "number", "numbers", "point", "points", "path", "install", "installed", "instance", "host",
    "threshold", "volume", "object", "objects", "apply", "first", "entire", "content", "readable",
    "generated", "restarting", "activated", "needed", "memory", "consistency", "subtraction",
    "conversion", "editing", "normally", "routing", "rule", "rules", "keys", "text", "hour", "hours",
    "last", "just", "interesting", "cases", "requires", "volumic", "possible", "compute", "give",
    "enter", "whole", "port", "tags", "printers", "migration", "assistant", "dynamic", "high",
    "initial", "radius", "raw", "data", "paused", "incomplete", "flip", "forgotten", "password",
    "angle", "echo", "listener", "default", "protocol", "route", "removal", "removing", "bone",
    "arranging", "finding", "dumping", "downloading", "drag", "place", "holders", "display",
    "displayed", "distant", "free", "space", "cleanup", "index", "site", "help", "reslicing",
}
# Names a Spanish sentence keeps as they are, spelled exactly like this: an application,
# a folder Horos makes, a DICOM attribute. They are matched with their capitals.
NAMES = {"Numbers", "Pages", "Word", "Mail", "Finder", "Photos", "Data", "Instance", "Class",
         "Keys", "Report", "Text", "Level", "List", "Index", "Path", "Mode", "Angle", "Volume"}
# Letters and accents, hyphens inside a word kept: "días" is one word, and so is the
# product name "On-Demand", which is not "on" plus "demand".
WORD = re.compile(r"[^\W\d_]+(?:-[^\W\d_]+)*", re.UNICODE)


def catalog(language):
    path = ROOT / f"Horos/Resources/{language}.lproj/Localizable.strings"
    return json.loads(subprocess.check_output(["plutil", "-convert", "json", "-o", "-", str(path)]))


def residual_module():
    spec = importlib.util.spec_from_file_location("residual", ROOT / "tools/host-localization-residual.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def mixed(language):
    """Entries of `language` whose value carries English words, with the English original."""
    english = catalog("en")
    residual = residual_module()
    found = {}
    for key, value in catalog(language).items():
        original = english.get(key, key)
        if value in (key, original) or residual.is_residual(key, original):
            continue
        # A name keeps its capitals; the same word in lower case is an English leftover.
        kept = {word.lower() for word in WORD.findall(value) if word in NAMES}
        words = {word.lower() for word in WORD.findall(value)}
        left = sorted((words & ENGLISH_WORDS) - kept)
        if left:
            found[key] = {"value": value, "english": original, "words": left}
    return found


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--language", action="append", default=None)
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args()
    languages = arguments.language or ["es", "it-IT"]
    total = 0
    for language in languages:
        found = mixed(language)
        total += len(found)
        for key, entry in sorted(found.items()):
            print(f"{language}: {key!r}\n    english: {entry['english']!r}\n    value:   {entry['value']!r}"
                  f"\n    english words left: {', '.join(entry['words'])}")
        print(f"{language}: {len(found)} mixed of {len(catalog(language))}")
    if arguments.check and total:
        raise SystemExit("A catalog value is half English. Translate the sentence, or leave the English one "
                         "and list it in tools/host-localization-residual.py.")


if __name__ == "__main__":
    main()
