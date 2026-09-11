#!/usr/bin/env python3
"""Every host NSLocalizedString key must exist in the Italian and Spanish catalogs."""
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
tool = root / "tools/collect-localized-strings.py"
subprocess.run([sys.executable, str(tool), "--check"], check=True)
print("PASS: host source keys are present in the Italian and Spanish catalogs")
