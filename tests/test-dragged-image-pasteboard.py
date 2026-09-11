#!/usr/bin/env python3
"""Runtime pasteboard types for a viewer image drag, and the DCMView wiring."""
from pathlib import Path
import subprocess, tempfile
root = Path(__file__).resolve().parents[1]
view = (root / 'Horos/Sources/DCMView.m').read_bytes().decode('latin1')

def require(condition, message):
    if not condition:
        raise SystemExit(f'FAIL: {message}')

start = view.index('- (void) startDrag:(NSTimer*)theTimer')
ended = view.index('- (void)deleteMouseDownTimer', start)
block = view[start:ended]
require('HorosDraggedImagePromise' in block,
        'startDrag must hand the destination an NSFilePromiseProvider-backed item')
require('kUTTypeImage' not in block,
        'an abstract image UTI does not tell Finder or a browser to expect JPEG')
require('NSPasteboardTypeString' not in block,
        'do not advertise a string type the provider never fulfils')
require('_dragInProgress = NO' not in block.split('@catch')[0],
        'clearing _dragInProgress before the session ends lets WW/WL run during export')

timer = view[view.index('- (void)deleteMouseDownTimer'):view.index('//part of Dragging Source Protocol')]
require('_dragInProgress = NO' not in timer,
        'deleteMouseDownTimer must not end an export session already in progress')
require('draggingSession:' in view and 'endedAtPoint:' in view,
        'the export session must end in draggingSession:endedAtPoint:')
require('HorosViewerImageDrag' in view and 'sourceOperationMaskOutsideApplication' in view,
        'external drops must use the Copy mask Finder and browsers accept')
require('DraggedImagePromise.swift' in
        (root / 'Horos.xcodeproj/project.pbxproj').read_text(encoding='utf-8'),
        'the file-promise type must be compiled into Horos')

code = r'''
import AppKit
import Foundation

@main struct Test {
 static func main() {
  _ = NSApplication.shared
  let image = NSImage(size: NSSize(width: 4, height: 4))
  image.lockFocus()
  NSColor.blue.setFill()
  NSBezierPath(rect: NSRect(x: 0, y: 0, width: 4, height: 4)).fill()
  image.unlockFocus()
  let tiff = image.tiffRepresentation!
  let promise = DraggedImagePromise(tiffData: tiff, study: "QA", series: "Axial")

  let needed = [
    NSPasteboard.PasteboardType.tiff.rawValue,
    "com.apple.pasteboard.promised-file-url",
    "com.apple.pasteboard.promised-file-content-type",
    DraggedImagePromise.promisedContentType,
  ]
  for type in needed {
    precondition(DraggedImagePromise.advertisedTypeIdentifiers.contains(type),
                 "missing advertised type \(type)")
  }

  let types = Set(promise.writableTypes(for: NSPasteboard.general).map(\.rawValue))
  precondition(types.contains(NSPasteboard.PasteboardType.tiff.rawValue),
               "browser destinations need a bitmap: \(types)")
  precondition(types.contains(where: { $0.contains("promised-file") }),
               "Finder needs a file promise: \(types)")

  let board = NSPasteboard.withUniqueName()
  board.clearContents()
  precondition(board.writeObjects([promise]), "pasteboard rejected the drag item")
  let declared = Set((board.types ?? []).map(\.rawValue))
  precondition(declared.contains(NSPasteboard.PasteboardType.tiff.rawValue),
               "runtime pasteboard omitted TIFF: \(declared)")
  precondition(declared.contains(where: { $0.contains("promised-file") }),
               "runtime pasteboard omitted the file promise: \(declared)")
  let bitmap = board.data(forType: .tiff)
  precondition((bitmap?.count ?? 0) > 0, "TIFF promise was empty")
  precondition(NSImage(data: bitmap!)?.size.width ?? 0 > 0, "TIFF was not a complete image")

  print("PASS: runtime pasteboard carries TIFF plus a JPEG file promise; DCMView keeps the session")
 }
}
'''
with tempfile.TemporaryDirectory(prefix='horos-drag-pasteboard-') as folder:
    p = Path(folder)
    (p / 'test.swift').write_text(code)
    subprocess.run(['xcrun', 'swiftc', '-swift-version', '5', '-parse-as-library',
                    str(root / 'Horos/Sources/DraggedImageFile.swift'),
                    str(root / 'Horos/Sources/DraggedImagePromise.swift'),
                    str(p / 'test.swift'), '-framework', 'Foundation', '-framework', 'AppKit',
                    '-o', str(p / 'test')], check=True)
    subprocess.run([str(p / 'test')], check=True)
