#!/usr/bin/env python3
"""A viewer drag must fulfil a JPEG file promise only after the file exists."""
from pathlib import Path
import subprocess, tempfile
root = Path(__file__).resolve().parents[1]
code = r'''
import AppKit
import Foundation

@main struct Test {
 static func main() throws {
  _ = NSApplication.shared

  let image = NSImage(size: NSSize(width: 8, height: 8))
  image.lockFocus()
  NSColor.red.setFill()
  NSBezierPath(rect: NSRect(x: 0, y: 0, width: 8, height: 8)).fill()
  image.unlockFocus()
  guard let tiff = image.tiffRepresentation, !tiff.isEmpty else {
    preconditionFailure("need a TIFF bitmap for the promise")
  }

  let promise = DraggedImagePromise(tiffData: tiff, study: "DOE/JANE", series: "../../etc")
  precondition(promise.suggestedFileName == "DOE JANE - etc.jpg",
               "hostile DICOM text leaked into the promised name: \(promise.suggestedFileName)")
  precondition(promise.suggestedFileName.hasSuffix(".jpg"))
  precondition(DraggedImagePromise.promisedContentType == "public.jpeg")

  let folder = URL(fileURLWithPath: NSTemporaryDirectory())
      .appendingPathComponent("horos-drag-promise-\(UUID().uuidString)")
  try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
  defer { try? FileManager.default.removeItem(at: folder) }

  let dest = folder.appendingPathComponent(promise.suggestedFileName)
  try promise.writeJPEG(to: dest)
  precondition(FileManager.default.fileExists(atPath: dest.path), "destination never received a file")
  guard let written = NSImage(contentsOf: dest), written.size.width > 0 else {
    preconditionFailure("destination received a path that is not a complete image")
  }

  // An empty encode must not leave a file the drop location would treat as real.
  let empty = DraggedImagePromise(tiffData: Data(), study: "Empty", series: "Fail")
  let missing = folder.appendingPathComponent("must-not-exist.jpg")
  do {
    try empty.writeJPEG(to: missing)
    preconditionFailure("an empty TIFF must not fulfil the promise")
  } catch {
    precondition(!FileManager.default.fileExists(atPath: missing.path),
                 "failed promise left \(missing.lastPathComponent)")
  }

  let provider = NSFilePromiseProvider(fileType: DraggedImagePromise.promisedContentType, delegate: promise)
  precondition(promise.filePromiseProvider(provider, fileNameForType: "public.jpeg")
               == promise.suggestedFileName)

  let fulfilled = folder.appendingPathComponent("from-delegate.jpg")
  let lock = DispatchSemaphore(value: 0)
  var writeError: Error?
  promise.filePromiseProvider(provider, writePromiseTo: fulfilled) { error in
    writeError = error
    lock.signal()
  }
  precondition(lock.wait(timeout: .now() + 2) == .success, "file promise write never finished")
  precondition(writeError == nil, "file promise write failed: \(String(describing: writeError))")
  precondition(FileManager.default.fileExists(atPath: fulfilled.path))

  print("PASS: JPEG file promise writes a complete image and leaves no file when encode fails")
 }
}
'''
with tempfile.TemporaryDirectory(prefix='horos-drag-promise-') as folder:
    p = Path(folder)
    (p / 'test.swift').write_text(code)
    subprocess.run(['xcrun', 'swiftc', '-swift-version', '5', '-parse-as-library',
                    str(root / 'Horos/Sources/DraggedImageFile.swift'),
                    str(root / 'Horos/Sources/DraggedImagePromise.swift'),
                    str(p / 'test.swift'), '-framework', 'Foundation', '-framework', 'AppKit',
                    '-o', str(p / 'test')], check=True)
    subprocess.run([str(p / 'test')], check=True)
