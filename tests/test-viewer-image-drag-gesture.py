#!/usr/bin/env python3
"""Export-drag from the viewer must not steal WW/WL, scroll or ROI."""
from pathlib import Path
import subprocess, tempfile
root = Path(__file__).resolve().parents[1]
code = r'''
import AppKit
import Foundation

@main struct Test {
 static func main() {
  // A press that moves is clinical manipulation: cancel the export wait.
  precondition(ViewerImageDrag.shouldCancelWait(deltaX: 1, deltaY: 0))
  precondition(ViewerImageDrag.shouldCancelWait(deltaX: 0, deltaY: -2))
  precondition(!ViewerImageDrag.shouldCancelWait(deltaX: 0, deltaY: 0))

  // Clinical tools run while idle or waiting; not during the file-promise session.
  precondition(!ViewerImageDrag.shouldIgnoreClinicalDrag(in: .idle))
  precondition(!ViewerImageDrag.shouldIgnoreClinicalDrag(in: .waitingToExport))
  precondition(ViewerImageDrag.shouldIgnoreClinicalDrag(in: .exporting))

  // Finder and browsers accept Copy. Generic alone is why drops died after Mojave.
  precondition(ViewerImageDrag.sourceOperationMask(outsideApplication: true) == NSDragOperation.copy.rawValue)
  precondition(ViewerImageDrag.sourceOperationMask(outsideApplication: false) == NSDragOperation.generic.rawValue)

  // mouseUp / timer teardown must not end a session that already started.
  precondition(!ViewerImageDrag.clearsExportSessionWhenCancellingWait)

  print("PASS: export drag waits for a still press, yields to clinical move, and holds the session until drop")
 }
}
'''
with tempfile.TemporaryDirectory(prefix='horos-drag-gesture-') as folder:
    p = Path(folder)
    (p / 'test.swift').write_text(code)
    subprocess.run(['xcrun', 'swiftc', '-swift-version', '5', '-parse-as-library',
                    str(root / 'Horos/Sources/ViewerImageDrag.swift'),
                    str(p / 'test.swift'), '-framework', 'Foundation', '-framework', 'AppKit',
                    '-o', str(p / 'test')], check=True)
    subprocess.run([str(p / 'test')], check=True)
