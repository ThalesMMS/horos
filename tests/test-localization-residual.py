#!/usr/bin/env python3
"""English-identical catalog values must be on the residual list."""
import importlib.util
import json
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "residual", root / "tools/host-localization-residual.py")
residual = importlib.util.module_from_spec(spec)
spec.loader.exec_module(residual)


def load(path):
    return json.loads(subprocess.check_output(
        ["plutil", "-convert", "json", "-o", "-", str(path)]))


en = load(root / "Horos/Resources/en.lproj/Localizable.strings")
ascii_keys = residual.english_comments()
assert set(ascii_keys) <= residual.ASCII_OVERLAYS, ascii_keys

unexpected = []
for language, folder in (("es", "es"), ("it-IT", "it-IT")):
    catalog = load(root / f"Horos/Resources/{folder}.lproj/Localizable.strings")
    assert en.keys() <= catalog.keys(), language
    for key, value in catalog.items():
        english = en.get(key, key)
        if value in (key, english) and not residual.is_residual(key, english):
            unexpected.append(f"{language}: {key!r}")

assert not unexpected, "unlisted English fallback:\n" + "\n".join(unexpected[:40])
print("PASS: residual English values are listed; ASCII overlay comments match")
