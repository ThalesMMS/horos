#!/usr/bin/env python3
"""Viewport display-to-world length is the geometric cause of zero MPR spacing."""
from pathlib import Path
import subprocess
import tempfile
root = Path(__file__).resolve().parents[1]
code = r'''
import Foundation

func expect(_ got: String, _ want: String) {
    precondition(got == want, "\(got) != \(want)")
}

// Two distinct display points that map to the same world point have length 0:
// VTK has no viewport yet. That is what getResolution logs on open, not a
// crash and not a reason to invent a spacing.
expect(CurvedMPRPathSession.diagnoseViewportWorldLength(0), "no viewport yet")
expect(CurvedMPRPathSession.diagnoseViewportWorldLength(1e-8), "no viewport yet")
expect(CurvedMPRPathSession.diagnoseViewportWorldLength(.nan), "not a number")
expect(CurvedMPRPathSession.diagnoseViewportWorldLength(1500), "out of range")
expect(CurvedMPRPathSession.diagnoseViewportWorldLength(0.42), "ready")

print("PASS: zero world length is no viewport yet; the warning stays a diagnosis")
'''
with tempfile.TemporaryDirectory(prefix='horos-curved-mpr-spacing-') as d:
    p = Path(d)
    (p / 'main.swift').write_text(code)
    subprocess.run([
        'xcrun', 'swiftc',
        str(root / 'Horos/Sources/CurvedMPRPath.swift'),
        str(p / 'main.swift'), '-o', str(p / 'test')
    ], check=True)
    subprocess.run([str(p / 'test')], check=True)
