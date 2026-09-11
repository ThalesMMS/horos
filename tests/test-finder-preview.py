#!/usr/bin/env python3
"""Finder Quick Look renders a supported DICOM fixture and names an unsupported encoding."""
import plistlib
import subprocess
import sys
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
preview = root / 'FinderPreview'
project = (root / 'Horos.xcodeproj/project.pbxproj').read_text()
info = (root / 'Horos/Info.plist').read_bytes()
failures = []

for name in ('FinderPreview.swift', 'PreviewViewController.swift', 'ThumbnailProvider.swift',
             'Preview-Info.plist', 'Thumbnail-Info.plist', 'FinderPreview.entitlements'):
    if not (preview / name).exists():
        failures.append('FinderPreview/%s is missing' % name)

for source in ((preview / 'FinderPreview.swift').read_text(),
               (preview / 'PreviewViewController.swift').read_text(),
               (preview / 'ThumbnailProvider.swift').read_text()):
    if 'Horos.app' in source or 'NSWorkspace.shared.open' in source or 'Bundle.main.bundleIdentifier' in source and 'horos' in source.lower() and 'FinderPreview' not in source:
        failures.append('the extension still talks to the Horos application')
    if 'import Horos' in source or 'DCMPix' in source or 'BrowserController' in source:
        failures.append('the extension still loads Horos types')

# The decoder is an extension process. It must not be compiled into Horos.app.
horos_at = project.find('AB28B42C05B7921E00A9906C /* Sources */')
horos_files = project.find('files = (', horos_at)
horos_sources = project[horos_files:project.find(');', horos_files)]
if 'FinderPreview.swift' in horos_sources:
    failures.append('FinderPreview.swift is compiled into Horos, so preview would start the app')

if 'HorosFinderPreview' not in project or 'HorosFinderThumbnail' not in project:
    failures.append('the Xcode project has no Finder preview or thumbnail target')
if 'com.apple.product-type.app-extension' not in project:
    failures.append('the Finder preview is not an app extension')
if 'Copy Embedded Plugins' not in project or 'HorosFinderPreview.appex in Copy Embedded Plugins' not in project:
    failures.append('the preview extension is not copied into Horos.app/Contents/PlugIns')
if 'HorosFinderThumbnail.appex in Copy Embedded Plugins' not in project:
    failures.append('the thumbnail extension is not copied into Horos.app/Contents/PlugIns')

for marker in ('A1410C010000000000000001', 'A1410C020000000000000002',
               'A1410C030000000000000003', 'A1410C040000000000000004'):
    at = project.find(marker)
    if at < 0 or 'DEVELOPMENT_TEAM = "$(HOROS_DEVELOPMENT_TEAM)"' not in project[at:at + 900]:
        failures.append('a Finder preview configuration no longer follows HOROS_DEVELOPMENT_TEAM')

preview_plist = plistlib.loads((preview / 'Preview-Info.plist').read_bytes())
thumb_plist = plistlib.loads((preview / 'Thumbnail-Info.plist').read_bytes())
if preview_plist['NSExtension']['NSExtensionPointIdentifier'] != 'com.apple.quicklook.preview':
    failures.append('the preview bundle is not a Quick Look preview extension')
if thumb_plist['NSExtension']['NSExtensionPointIdentifier'] != 'com.apple.quicklook.thumbnail':
    failures.append('the thumbnail bundle is not a Quick Look thumbnail extension')
if 'org.nema.dicom' not in preview_plist['NSExtension']['NSExtensionAttributes']['QLSupportedContentTypes']:
    failures.append('the preview extension does not claim org.nema.dicom')
if 'org.nema.dicom' not in thumb_plist['NSExtension']['NSExtensionAttributes']['QLSupportedContentTypes']:
    failures.append('the thumbnail extension does not claim org.nema.dicom')

horos_info = plistlib.loads(info)
types = horos_info.get('UTImportedTypeDeclarations') or []
if not any(item.get('UTTypeIdentifier') == 'org.nema.dicom' for item in types):
    failures.append('Horos no longer declares org.nema.dicom')
dicom_docs = [item for item in horos_info.get('CFBundleDocumentTypes', [])
              if 'dcm' in item.get('CFBundleTypeExtensions', [])]
if not dicom_docs or 'org.nema.dicom' not in dicom_docs[0].get('LSItemContentTypes', []):
    failures.append('the DICOM document type is not bound to org.nema.dicom')

if failures:
    print('FAIL:')
    for item in failures:
        print(' ', item)
    sys.exit(1)

program = r'''
import AppKit
import Foundation

func pixels(_ image: NSImage) -> (Int, Int, [UInt8]) {
    let tiff = image.tiffRepresentation!
    let rep = NSBitmapImageRep(data: tiff)!
    var values = [UInt8]()
    for y in 0..<rep.pixelsHigh {
        for x in 0..<rep.pixelsWide {
            var pixel = [Int](repeating: 0, count: 5)
            rep.getPixel(&pixel, atX: x, y: y)
            values.append(UInt8(clamping: pixel[0]))
        }
    }
    return (rep.pixelsWide, rep.pixelsHigh, values)
}

func expectImage(_ url: URL, left: Int, right: Int, file: String) {
    switch FinderPreview.load(url) {
    case .failure(let reason):
        fputs("FAIL: \(file) should render: \(reason.sentence)\n", stderr)
        exit(1)
    case .image(let image):
        let (width, height, values) = pixels(image)
        if width != 32 || height != 32 {
            fputs("FAIL: \(file) size \(width)x\(height)\n", stderr)
            exit(1)
        }
        let leftPixel = Int(values[8 * 32 + 8])
        let rightPixel = Int(values[8 * 32 + 24])
        if abs(leftPixel - left) > 2 || abs(rightPixel - right) > 2 {
            fputs("FAIL: \(file) pixels \(leftPixel) \(rightPixel) expected \(left) \(right)\n", stderr)
            exit(1)
        }
    }
}

func expectFailure(_ url: URL, contains: [String], file: String) {
    switch FinderPreview.load(url) {
    case .image:
        fputs("FAIL: \(file) rendered an image for an unsupported encoding\n", stderr)
        exit(1)
    case .failure(let reason):
        let text = reason.sentence
        for needle in contains {
            if !text.contains(needle) {
                fputs("FAIL: \(file) sentence \(text) does not name \(needle)\n", stderr)
                exit(1)
            }
        }
        if text.count > 120 {
            fputs("FAIL: \(file) sentence is not a Finder-scale message: \(text)\n", stderr)
            exit(1)
        }
    }
}

let folder = URL(fileURLWithPath: CommandLine.arguments[1], isDirectory: true)
expectImage(folder.appendingPathComponent("supported-explicit.dcm"), left: 40, right: 200, file: "explicit")
expectImage(folder.appendingPathComponent("supported-implicit.dcm"), left: 40, right: 200, file: "implicit")
expectFailure(folder.appendingPathComponent("unsupported-jpegls.dcm"),
              contains: ["1.2.840.10008.1.2.4.80", "not supported"],
              file: "jpegls")
expectFailure(folder.appendingPathComponent("not-dicom.dcm"),
              contains: ["not a DICOM"],
              file: "not-dicom")

let named = FinderPreview.unsupportedTransferSyntax("1.2.840.10008.1.2.4.90")
if !named.contains("1.2.840.10008.1.2.4.90") || !named.lowercased().contains("not supported") {
    fputs("FAIL: unsupported sentence does not name the UID\n", stderr)
    exit(1)
}

print("PASS: supported Explicit and Implicit VR fixtures render the step; JPEG-LS and a non-DICOM file fail with a named reason")
'''

with tempfile.TemporaryDirectory(prefix='horos-finder-preview-') as folder:
    work = Path(folder)
    fixtures = work / 'fixtures'
    subprocess.run([sys.executable, str(root / 'tools/generate-finder-preview-fixture.py'),
                    str(fixtures)], check=True)
    (work / 'main.swift').write_text(program)
    compile = subprocess.run(['xcrun', 'swiftc',
                              str(preview / 'FinderPreview.swift'), str(work / 'main.swift'),
                              '-framework', 'AppKit', '-o', str(work / 'test')],
                             capture_output=True, text=True)
    if compile.returncode != 0:
        print(compile.stderr)
        raise SystemExit(compile.returncode)
    subprocess.run([str(work / 'test'), str(fixtures)], check=True)
    controller = r'''
import AppKit
import Foundation
import Quartz

@main
struct PreviewControllerCheck {
    static func main() {
        _ = NSApplication.shared
        let folder = URL(fileURLWithPath: CommandLine.arguments[1], isDirectory: true)
        let supported = PreviewViewController()
        wait(supported, folder.appendingPathComponent("supported-explicit.dcm"))
        let image = supported.view.subviews.compactMap { $0 as? NSImageView }.first
        if image?.image == nil || image?.isHidden == true {
            fputs("FAIL: supported fixture did not appear in the preview view\n", stderr)
            exit(1)
        }
        let unsupported = PreviewViewController()
        wait(unsupported, folder.appendingPathComponent("unsupported-jpegls.dcm"))
        let label = unsupported.view.subviews.compactMap { $0 as? NSTextField }.first
        if label?.isHidden == true || !(label?.stringValue.contains("1.2.840.10008.1.2.4.80") ?? false) {
            fputs("FAIL: unsupported encoding was not named in the preview: \(label?.stringValue ?? "nil")\n", stderr)
            exit(1)
        }
        print("PASS: preview controller shows the supported image and names the unsupported transfer syntax")
    }

    static func wait(_ controller: PreviewViewController, _ url: URL) {
        _ = controller.view
        let done = DispatchSemaphore(value: 0)
        controller.preparePreviewOfFile(at: url) { error in
            if error != nil { fputs("FAIL: preview handler returned \(error!)\n", stderr); exit(1) }
            done.signal()
        }
        if done.wait(timeout: .now() + 2) == .timedOut {
            fputs("FAIL: preview did not finish\n", stderr); exit(1)
        }
    }
}
'''
    (work / 'controller.swift').write_text(controller)
    subprocess.run(['xcrun', 'swiftc',
                    str(preview / 'FinderPreview.swift'),
                    str(preview / 'PreviewViewController.swift'),
                    str(work / 'controller.swift'),
                    '-framework', 'AppKit', '-framework', 'Quartz',
                    '-o', str(work / 'controller')], check=True)
    subprocess.run([str(work / 'controller'), str(fixtures)], check=True)
    subprocess.run(['xcrun', 'swiftc', '-parse-as-library',
                    str(preview / 'FinderPreview.swift'),
                    str(preview / 'ThumbnailProvider.swift'),
                    '-framework', 'AppKit', '-framework', 'QuickLookThumbnailing',
                    '-emit-library', '-module-name', 'HorosFinderThumbnail',
                    '-o', str(work / 'libThumbnail.dylib')], check=True)
