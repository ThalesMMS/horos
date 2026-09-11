#!/usr/bin/env python3
"""A dragged image must land on a real file with a name the drop location accepts."""
from pathlib import Path
import subprocess, tempfile
root = Path(__file__).resolve().parents[1]
code = r'''
import Foundation

@main struct Test {
 static func main() throws {
  // Free text out of the DICOM data cannot become a path component unexamined.
  let hostile = DraggedImageFile.name(study: "DOE/JANE", series: "../../etc")
  precondition(!hostile.contains("/"), "a separator would nest or escape the drop location: \(hostile)")
  precondition(!hostile.hasPrefix("."), "a leading dot hides the file: \(hostile)")
  precondition(!hostile.contains(":"), "a colon is a separator in some destinations: \(hostile)")

  // Readable names survive.
  precondition(DraggedImageFile.name(study: "Doe, Jane", series: "Axial CT")
               == "Doe, Jane - Axial CT")
  // Either half alone is enough; neither falls back to a fixed name.
  precondition(DraggedImageFile.name(study: "Doe", series: nil) == "Doe")
  precondition(DraggedImageFile.name(study: nil, series: "Axial") == "Axial")
  precondition(DraggedImageFile.name(study: nil, series: nil) == "Horos")
  precondition(DraggedImageFile.name(study: "///", series: "   ") == "Horos")
  // A very long description cannot overrun the destination's name limit.
  let long = DraggedImageFile.name(study: String(repeating: "A", count: 500),
                                   series: String(repeating: "B", count: 500))
  precondition(long.utf8.count < 255, "name is \(long.utf8.count) bytes")

  // Successive drops of the same series do not overwrite each other.
  let folder = URL(fileURLWithPath: NSTemporaryDirectory())
      .appendingPathComponent("horos-drag-\(UUID().uuidString)")
  try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
  defer { try? FileManager.default.removeItem(at: folder) }

  var seen = Set<String>()
  for _ in 0..<5 {
    guard let url = DraggedImageFile.url(in: folder, name: "Doe - Axial", pathExtension: "jpg") else {
      preconditionFailure("ran out of names with five files")
    }
    precondition(url.pathExtension == "jpg")
    precondition(!seen.contains(url.path), "handed out \(url.lastPathComponent) twice")
    precondition(!FileManager.default.fileExists(atPath: url.path))
    seen.insert(url.path)
    try Data([0x42]).write(to: url)
  }
  precondition(seen.count == 5)

  // The name stays inside the directory it was given.
  let escaped = DraggedImageFile.url(in: folder, name: DraggedImageFile.name(study: "../../evil", series: nil),
                                     pathExtension: "jpg")!
  precondition(escaped.deletingLastPathComponent().standardizedFileURL.path
               == folder.standardizedFileURL.path, "escaped to \(escaped.path)")

  print("PASS: separators, dots, colons and overlong text are removed from the name; repeated drops get distinct files inside the drop location")
 }
}
'''
with tempfile.TemporaryDirectory(prefix='horos-drag-name-') as folder:
    p = Path(folder)
    (p / 'test.swift').write_text(code)
    subprocess.run(['xcrun', 'swiftc', '-swift-version', '5', '-parse-as-library',
                    str(root / 'Horos/Sources/DraggedImageFile.swift'),
                    str(p / 'test.swift'), '-framework', 'Foundation',
                    '-o', str(p / 'test')], check=True)
    subprocess.run([str(p / 'test')], check=True)
