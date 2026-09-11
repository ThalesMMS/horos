#!/usr/bin/env python3
"""DICOM send recedes Key Images and SC independently (#490)."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
code = r'''
import Foundation

func check(_ condition: @autoclosure () -> Bool, _ message: String) {
    precondition(condition(), message)
}

check(SendWhatFilter.allImages == 0, "all images is 0")
check(SendWhatFilter.keyImages == 1, "key images is 1")
check(SendWhatFilter.secondaryCapture == 2, "SC is 2")
check(SendWhatFilter.isKnown(0) && SendWhatFilter.isKnown(1) && SendWhatFilter.isKnown(2),
      "0/1/2 are known")
check(!SendWhatFilter.isKnown(3) && !SendWhatFilter.isKnown(-1), "3 and -1 are unknown")

check(SendWhatFilter.resolvedIndex(0, hasKeyImages: false, hasSecondaryCaptures: false) == 0,
      "all stays all")
check(SendWhatFilter.resolvedIndex(1, hasKeyImages: true, hasSecondaryCaptures: false) == 1,
      "key images stay when present even without SC")
check(SendWhatFilter.resolvedIndex(1, hasKeyImages: false, hasSecondaryCaptures: true) == 0,
      "key images recede without key images")
check(SendWhatFilter.resolvedIndex(1, hasKeyImages: false, hasSecondaryCaptures: false) == 0,
      "key images recede when neither category exists")
check(SendWhatFilter.resolvedIndex(2, hasKeyImages: true, hasSecondaryCaptures: false) == 0,
      "SC recedes without SC")
check(SendWhatFilter.resolvedIndex(2, hasKeyImages: false, hasSecondaryCaptures: true) == 2,
      "SC stays when present even without key images")
check(SendWhatFilter.resolvedIndex(2, hasKeyImages: true, hasSecondaryCaptures: true) == 2,
      "SC stays when both exist")
check(SendWhatFilter.resolvedIndex(3, hasKeyImages: true, hasSecondaryCaptures: true) == 0,
      "unknown recedes to all")
check(SendWhatFilter.resolvedIndex(-1, hasKeyImages: true, hasSecondaryCaptures: true) == 0,
      "negative recedes to all")

check(SendWhatFilter.filtersKeyImages(forIndex: 1), "1 filters key images")
check(!SendWhatFilter.filtersKeyImages(forIndex: 2), "2 does not filter key images")
check(SendWhatFilter.filtersSecondaryCapture(forIndex: 2), "2 filters SC")
check(!SendWhatFilter.filtersSecondaryCapture(forIndex: 1), "1 does not filter SC")

print("PASS: send what filter recedes Key Images and SC independently")
'''
with tempfile.TemporaryDirectory(prefix='horos-send-what-') as tmp:
    p = Path(tmp)
    (p / 'main.swift').write_text(code)
    subprocess.run([
        'xcrun', 'swiftc',
        str(root / 'Horos/Sources/SendWhatFilter.swift'),
        str(p / 'main.swift'), '-o', str(p / 'test')
    ], check=True)
    subprocess.run([str(p / 'test')], check=True)
