#!/usr/bin/env python3
"""Bruker-reported Enhanced MR: detect, read, thumbnail — never blame the vendor.

Upstream horosproject/horos#500 attached EnIm1.dcm (Enhanced MR, 256×256×3,
Explicit VR LE) and two crash logs. Both died with EXC_ARITHMETIC / divide-by-
zero on matrixLoadIcons → DicomSeries thumbnail → DCMPix loadDICOMDCMFramework.
The manufacturer is a fact in the header, not a cause: a file that would crash
the thumbnail stack is refused before it is merged out of INCOMING, and a file
the current stack can load is imported with its pixels and functional groups.

This exercises the isolated Swift triage against synthetic fixtures (no PHI)
and the call sites that must consult it.
"""
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
failures = []

database = (root / 'Horos/Sources/DicomDatabase.mm').read_bytes().decode('latin1')
if 'HorosEnhancedImportTriage' not in database or 'mayMergeIntoIncoming' not in database:
    failures.append('incoming scan still merges a DICOM without asking the isolated stack gate')

pix = (root / 'Horos/Sources/DCMPix.m').read_bytes().decode('latin1')
thumb = pix[pix.find('- (NSImage*) generateThumbnailImageWithWW:'):pix.find('- (NSImage*) generateThumbnailImageWithWW:') + 900]
if 'generateThumbnailImageWithWW' not in pix:
    failures.append('generateThumbnailImageWithWW is gone')
elif 'width < 1' not in thumb and 'width <= 0' not in thumb:
    failures.append('thumbnail generation still divides a zero-size frame into PREVIEWSIZE')
if 'bitsStored <= 0 || self->bitsStored > bitsAllocated' not in pix:
    failures.append('the BitsStored clamp that turned a missing value into divide-by-zero is gone')

source = root / 'Horos/Sources/EnhancedImportTriage.swift'
if not source.is_file():
    failures.append('EnhancedImportTriage.swift is missing')
    for failure in failures:
        print('FAIL: %s' % failure)
    sys.exit(1)

generator = root / 'tools/generate-bruker-enhanced-fixture.py'
if not generator.is_file():
    failures.append('the Bruker/Enhanced fixture generator is missing')

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

let compatible = EnhancedImportTriage.assessPath(path("compatible.dcm"))
check(EnhancedImportTriage.detectDICOM(atPath: path("compatible.dcm")), "detection missed a DICOM preamble")
check(compatible.detectedDICOM, "assessment did not mark the Enhanced MR as DICOM")
check(compatible.isEnhanced, "SharedFunctionalGroupsSequence was not read as enhanced")
check(compatible.rows == 32 && compatible.columns == 32, "rows/columns \(compatible.rows)x\(compatible.columns)")
check(compatible.frames == 3, "frames \(compatible.frames)")
check(compatible.bitsAllocated == 16 && compatible.bitsStored == 16, "bits \(compatible.bitsAllocated)/\(compatible.bitsStored)")
check(abs(compatible.pixelSpacingX - 0.234375) < 0.0001, "pixel spacing X \(compatible.pixelSpacingX)")
check(abs(compatible.pixelSpacingY - 0.234375) < 0.0001, "pixel spacing Y \(compatible.pixelSpacingY)")
check(compatible.hasSharedFunctionalGroups && compatible.hasPerFrameFunctionalGroups, "functional groups missing")
check(compatible.pixelDataBytes == 32 * 32 * 3 * 2, "pixel bytes \(compatible.pixelDataBytes)")
check(compatible.thumbnailCompatible, "a complete Enhanced MR was refused a thumbnail")
check(compatible.mayMergeIntoIncoming, "a complete Enhanced MR was kept out of incoming")
check(compatible.recordedError == nil || compatible.recordedError!.isEmpty, "a valid file recorded \(compatible.recordedError ?? "")")
check(compatible.manufacturer == "Synthetic Imaging", "manufacturer should be recorded as metadata, got \(compatible.manufacturer ?? "nil")")
check(!(compatible.recordedError ?? "").localizedCaseInsensitiveContains("bruker"), "a valid file blamed Bruker")

let brukerShaped = EnhancedImportTriage.assessPath(path("bruker-shaped.dcm"))
check(brukerShaped.mayMergeIntoIncoming, "a Bruker-shaped but valid Enhanced MR was blocked")
check(brukerShaped.manufacturer == "Bruker BioSpin MRI GmbH", "Bruker manufacturer was dropped")
check(!(brukerShaped.incompatibilityReasons.joined()).localizedCaseInsensitiveContains("bruker"),
      "incompatibility blamed the manufacturer")

let zero = EnhancedImportTriage.assessPath(path("zero-rows.dcm"))
check(zero.detectedDICOM, "a zero-row DICOM was not detected")
check(zero.isEnhanced, "zero-row fixture lost its enhanced groups")
check(!zero.thumbnailCompatible, "zero rows were called thumbnail-safe")
check(!zero.mayMergeIntoIncoming, "a zero-row file was merged into incoming")
check((zero.recordedError ?? "").contains("row") || (zero.recordedError ?? "").contains("size"),
      "zero-row error was vague: \(zero.recordedError ?? "nil")")
check(!(zero.recordedError ?? "").localizedCaseInsensitiveContains("bruker"),
      "zero-row error named the manufacturer")

let empty = EnhancedImportTriage.assessPath(path("empty-pixels.dcm"))
check(empty.detectedDICOM && empty.isEnhanced, "empty-pixel fixture was not read")
check(empty.recordedError != nil && !(empty.recordedError!.isEmpty),
      "missing Pixel Data produced no specific error")
check(!(empty.recordedError ?? "").localizedCaseInsensitiveContains("bruker"),
      "missing pixels were blamed on the manufacturer")

check(!EnhancedImportTriage.detectDICOM(atPath: path("not-dicom.bin")), "a text file was called DICOM")
let noise = EnhancedImportTriage.assessPath(path("not-dicom.bin"))
check(!noise.detectedDICOM && !noise.mayMergeIntoIncoming, "noise was allowed into incoming")

if failures > 0 { exit(1) }
print("PASS isolated detection, enhanced read, thumbnail gate and incoming merge")
'''

with tempfile.TemporaryDirectory(prefix='horos-bruker-') as folder:
    work = Path(folder)
    if generator.is_file():
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
                failures.append('EnhancedImportTriage.swift does not compile:\n%s'
                                % compile_cmd.stderr[-1500:])
            else:
                ran = subprocess.run([str(work / 'test'), str(work)],
                                     capture_output=True, text=True)
                if ran.returncode:
                    failures.append(ran.stderr.strip() or ran.stdout.strip() or 'triage helper failed')
                else:
                    print(ran.stdout.strip())
    else:
        print('skipped fixture helper until the generator exists')

for failure in failures:
    print('FAIL: %s' % failure)
sys.exit(1 if failures else 0)
