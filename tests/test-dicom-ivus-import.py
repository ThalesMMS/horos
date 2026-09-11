#!/usr/bin/env python3
"""Volcano-reported IVUS: detect, diagnose, thumbnail — never blame the vendor.

Upstream horosproject/horos#365 crashed while the first library row built its
series icon (thumbnail → DCMPix loadDICOMDCMFramework) and then again on every
relaunch. The sample was requested and never published. A file that would crash
the thumbnail stack is refused before it is merged out of INCOMING, and a file
already in the database is given a placeholder icon so the next open does not
retry the crash. The manufacturer is a fact in the header, not a cause.
"""
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
failures = []

database = (root / 'Horos/Sources/DicomDatabase.mm').read_bytes().decode('latin1')
if 'HorosEnhancedImportTriage' not in database or 'mayMergeIntoIncoming' not in database:
    failures.append('incoming scan no longer asks the Enhanced stack gate (#83)')
if 'HorosIVUSImportTriage' not in database or 'appliesToFile' not in database:
    failures.append('incoming scan still merges an IVUS/US object without asking the isolated IVUS gate')

series = (root / 'Horos/Sources/DicomSeries.m').read_bytes().decode('latin1')
thumb_start = series.find('-(NSData*)thumbnail')
if thumb_start < 0:
    thumb_start = series.find('- (NSData*)thumbnail')
thumb_end = series.find('- (NSString*) modalities', thumb_start) if thumb_start >= 0 else -1
if thumb_end < 0 and thumb_start >= 0:
    thumb_end = thumb_start + 12000
thumb = series[thumb_start:thumb_end] if thumb_start >= 0 else ''
if 'HorosIVUSImportTriage' not in thumb:
    failures.append('DicomSeries thumbnail still opens DCMPix before asking the IVUS gate')
elif '[dcmPix CheckLoad]' in thumb and thumb.find('HorosIVUSImportTriage') > thumb.find('[dcmPix CheckLoad]'):
    failures.append('DicomSeries thumbnail still calls CheckLoad before the IVUS gate')

pix = (root / 'Horos/Sources/DCMPix.m').read_bytes().decode('latin1')
load = pix[pix.find('- (BOOL)loadDICOMDCMFramework'):pix.find('- (BOOL)loadDICOMDCMFramework') + 2200]
if 'HorosIVUSImportTriage' not in load:
    failures.append('loadDICOMDCMFramework still decodes an unloadable IVUS before the isolated gate')
thumb_fn = pix[pix.find('- (NSImage*) generateThumbnailImageWithWW:'):pix.find('- (NSImage*) generateThumbnailImageWithWW:') + 900]
if 'generateThumbnailImageWithWW' not in pix:
    failures.append('generateThumbnailImageWithWW is gone')
elif 'width < 1' not in thumb_fn and 'width <= 0' not in thumb_fn:
    failures.append('thumbnail generation still divides a zero-size frame into PREVIEWSIZE')

if 'EnhancedImportTriage.swift' not in (root / 'Horos.xcodeproj/project.pbxproj').read_text():
    failures.append('EnhancedImportTriage.swift was removed from the Xcode project')
if 'GSPSDocument.swift' not in (root / 'Horos.xcodeproj/project.pbxproj').read_text():
    failures.append('GSPSDocument.swift was removed from the Xcode project')

source = root / 'Horos/Sources/IVUSImportTriage.swift'
if not source.is_file():
    failures.append('IVUSImportTriage.swift is missing')
    for failure in failures:
        print('FAIL: %s' % failure)
    sys.exit(1)

project = (root / 'Horos.xcodeproj/project.pbxproj').read_text()
if 'IVUSImportTriage.swift' not in project:
    failures.append('IVUSImportTriage.swift is not in the Xcode project')

generator = root / 'tools/generate-ivus-fixture.py'
if not generator.is_file():
    failures.append('the IVUS fixture generator is missing')

if not (root / 'docs/ivus-import-validation.md').is_file():
    failures.append('the local validation record is not in docs/ivus-import-validation.md')

main = r'''
import Foundation

let root = URL(fileURLWithPath: CommandLine.arguments[1])
func path(_ name: String) -> String { root.appendingPathComponent(name).path }

var failures = 0
func check(_ condition: Bool, _ message: String) {
    if !condition {
        fputs("FAIL \(message)\n", stderr)
        failures += 1
    }
}

let compatible = IVUSImportTriage.assessPath(path("compatible.dcm"))
check(IVUSImportTriage.detectDICOM(atPath: path("compatible.dcm")), "detection missed a DICOM preamble")
check(compatible.detectedDICOM, "assessment did not mark the IVUS cine as DICOM")
check(compatible.appliesToFile, "Ultrasound Multi-frame was not treated as IVUS-shaped")
check(compatible.rows == 32 && compatible.columns == 32, "rows/columns \(compatible.rows)x\(compatible.columns)")
check(compatible.frames == 4, "frames \(compatible.frames)")
check(compatible.bitsAllocated == 8, "bits \(compatible.bitsAllocated)")
check(compatible.hasUltrasoundRegions, "Sequence of Ultrasound Regions was not read")
check(compatible.hasIVUSAcquisition, "IVUS Acquisition was not read")
check(abs(compatible.physicalDeltaX - 0.002) < 0.000001, "physical delta X \(compatible.physicalDeltaX)")
check(abs(compatible.physicalDeltaY - 0.002) < 0.000001, "physical delta Y \(compatible.physicalDeltaY)")
check(compatible.pixelDataBytes == 32 * 32 * 4, "pixel bytes \(compatible.pixelDataBytes)")
check(compatible.thumbnailCompatible, "a complete IVUS cine was refused a thumbnail")
check(compatible.mayMergeIntoIncoming, "a complete IVUS cine was kept out of incoming")
check(compatible.recordedError == nil || compatible.recordedError!.isEmpty, "a valid file recorded \(compatible.recordedError ?? "")")
check(compatible.manufacturer == "Synthetic Imaging", "manufacturer should be recorded as metadata, got \(compatible.manufacturer ?? "nil")")
check(!(compatible.recordedError ?? "").localizedCaseInsensitiveContains("volcano"), "a valid file blamed Volcano")

let volcano = IVUSImportTriage.assessPath(path("volcano-shaped.dcm"))
check(volcano.mayMergeIntoIncoming, "a Volcano-shaped but valid IVUS cine was blocked")
check(volcano.thumbnailCompatible, "a Volcano-shaped but valid IVUS cine was refused a thumbnail")
check(volcano.manufacturer == "Volcano Corporation", "Volcano manufacturer was dropped")
check(volcano.hasIVUSAcquisition, "Volcano-shaped fixture lost IVUS Acquisition")
check(!(volcano.incompatibilityReasons.joined()).localizedCaseInsensitiveContains("volcano"),
      "incompatibility blamed the manufacturer")

let zero = IVUSImportTriage.assessPath(path("zero-rows.dcm"))
check(zero.detectedDICOM && zero.appliesToFile, "a zero-row IVUS was not detected")
check(!zero.thumbnailCompatible, "zero rows were called thumbnail-safe")
check(!zero.mayMergeIntoIncoming, "a zero-row IVUS was merged into incoming")
check((zero.recordedError ?? "").contains("row") || (zero.recordedError ?? "").contains("size"),
      "zero-row error was vague: \(zero.recordedError ?? "nil")")
check(!(zero.recordedError ?? "").localizedCaseInsensitiveContains("volcano"),
      "zero-row error named the manufacturer")

let empty = IVUSImportTriage.assessPath(path("empty-pixels.dcm"))
check(empty.detectedDICOM && empty.appliesToFile, "empty-pixel IVUS was not read")
check(!empty.mayMergeIntoIncoming, "an IVUS without Pixel Data was merged into incoming")
check(empty.recordedError != nil && !(empty.recordedError!.isEmpty),
      "missing Pixel Data produced no specific error")
check(!(empty.recordedError ?? "").localizedCaseInsensitiveContains("volcano"),
      "missing pixels were blamed on the manufacturer")

let palette = IVUSImportTriage.assessPath(path("palette-without-lut.dcm"))
check(palette.detectedDICOM && palette.appliesToFile, "palette IVUS was not read")
check(!palette.hasPaletteLUT, "a file without LUT descriptors was said to have a palette")
check(!palette.thumbnailCompatible && !palette.mayMergeIntoIncoming,
      "PALETTE COLOR without a LUT was allowed into incoming")
check((palette.recordedError ?? "").localizedCaseInsensitiveContains("palette"),
      "palette error was vague: \(palette.recordedError ?? "nil")")

let implicit = IVUSImportTriage.assessPath(path("implicit-le.dcm"))
check(implicit.detectedDICOM && implicit.appliesToFile, "Implicit VR IVUS was not read")
check(implicit.rows == 16 && implicit.columns == 16, "implicit rows/columns \(implicit.rows)x\(implicit.columns)")
check(implicit.hasUltrasoundRegions && implicit.hasIVUSAcquisition, "implicit IVUS lost regions or acquisition")
check(implicit.mayMergeIntoIncoming && implicit.thumbnailCompatible,
      "a complete Implicit VR IVUS was kept out of incoming")
check(implicit.transferSyntaxUID == "1.2.840.10008.1.2",
      "implicit transfer syntax \(implicit.transferSyntaxUID ?? "nil")")

let ct = IVUSImportTriage.assessPath(path("ct-control.dcm"))
check(ct.detectedDICOM, "CT control was not recognised as DICOM")
check(!ct.appliesToFile, "a CT object was treated as IVUS-shaped")
check(ct.mayMergeIntoIncoming, "the IVUS gate blocked a CT that it does not apply to")

check(!IVUSImportTriage.detectDICOM(atPath: path("not-dicom.bin")), "a text file was called DICOM")
let noise = IVUSImportTriage.assessPath(path("not-dicom.bin"))
check(!noise.detectedDICOM && !noise.appliesToFile && !noise.mayMergeIntoIncoming,
      "noise was allowed into incoming")

if failures > 0 { exit(1) }
print("PASS isolated IVUS detection, region read, thumbnail gate and incoming merge")
'''

with tempfile.TemporaryDirectory(prefix='horos-ivus-') as folder:
    work = Path(folder)
    if generator.is_file() and source.is_file():
        built = subprocess.run([sys.executable, str(generator), str(work)],
                               capture_output=True, text=True)
        if built.returncode:
            failures.append('fixture generator failed: %s' % (built.stderr or built.stdout)[-800:])
        else:
            (work / 'main.swift').write_text(main)
            compile_cmd = subprocess.run(
                ['swiftc', str(root / 'Horos/Sources/DICOMTriageMetadata.swift'), str(source), str(work / 'main.swift'), '-o', str(work / 'test')],
                capture_output=True, text=True)
            if compile_cmd.returncode:
                failures.append('IVUSImportTriage.swift does not compile:\n%s'
                                % compile_cmd.stderr[-1500:])
            else:
                ran = subprocess.run([str(work / 'test'), str(work)],
                                     capture_output=True, text=True)
                if ran.returncode:
                    failures.append(ran.stderr.strip() or ran.stdout.strip() or 'triage helper failed')
                else:
                    print(ran.stdout.strip())
    elif not source.is_file():
        print('skipped fixture helper until IVUSImportTriage.swift exists')

for failure in failures:
    print('FAIL: %s' % failure)
sys.exit(1 if failures else 0)
