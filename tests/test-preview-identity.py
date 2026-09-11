#!/usr/bin/env python3
"""The database preview shows the frame it was asked for (#380 D).

Object level: `HorosPreviewIdentity` refuses to reuse pixels loaded elsewhere
unless the file, the frame, the series and the size all match; refuses to
preview an instance that carries no frame (SR, SEG, presentation state,
encapsulated PDF); and refuses a whole-series preview that would mix series,
sizes or repeat a frame.

Source level: the browser matches a loaded frame by path *and* frame number —
it used to take any frame of the file when frame 0 was requested — and every
call that reuses a loaded frame passes the identity it expects.
"""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
driver = r'''
import Foundation
func expect(_ ok: Bool, _ reason: String) { if !ok { fatalError(reason) } }
func frame(_ path: String, _ f: Int, series: String = "1.2.series", sop: String = "1.2.840.10008.5.1.4.1.1.2",
           modality: String = "CT", rows: Int = 512, columns: Int = 512, count: Int = 1, id: Int = 1) -> PreviewFrame {
    PreviewFrame(path: path, sopInstanceUID: path + "#\(f)", seriesInstanceUID: series, sopClassUID: sop,
                 modality: modality, frameNumber: f, frameCount: count, rows: rows, columns: columns, seriesID: id)
}

// 1. Reuse: the same file at another frame is not the requested frame.
let wanted = frame("/a/multi.dcm", 0, count: 16)
expect(PreviewIdentity.refusalForReusing(frame("/a/multi.dcm", 0, count: 16), asRequested: wanted) == nil, "the same frame is reusable")
let other = PreviewIdentity.refusalForReusing(frame("/a/multi.dcm", 7, count: 16), asRequested: wanted)
expect(other?.contains("is not frame 0") == true, "another frame of the same file is refused: \(other ?? "accepted")")
expect(PreviewIdentity.refusalForReusing(frame("/b/other.dcm", 0), asRequested: wanted)?.contains("cannot stand for") == true, "another file refused")
expect(PreviewIdentity.refusalForReusing(frame("/a/multi.dcm", 0, series: "9.9", count: 16), asRequested: wanted)?.contains("belongs to series") == true,
       "the same file indexed under another series is refused")
expect(PreviewIdentity.refusalForReusing(frame("/a/multi.dcm", 0, count: 16, id: 3), asRequested: wanted)?.contains("series number") == true,
       "another series number refused")
expect(PreviewIdentity.refusalForReusing(frame("/a/multi.dcm", 0, rows: 256, count: 16), asRequested: wanted)?.contains("256") == true,
       "a differently sized frame is refused")

// 2. Previewable: SR, SEG, presentation states and encapsulated PDF carry no frame.
expect(PreviewIdentity.isPreviewable(frame("/a/ct.dcm", 0)), "a CT frame is previewable")
expect(PreviewIdentity.refusalForPreviewing(frame("/a/sr.dcm", 0, modality: "SR"))?.contains("no displayable frame") == true, "SR by modality")
expect(PreviewIdentity.refusalForPreviewing(frame("/a/seg.dcm", 0, modality: "SEG"))?.contains("no displayable frame") == true, "SEG by modality")
expect(PreviewIdentity.refusalForPreviewing(frame("/a/sr.dcm", 0, sop: "1.2.840.10008.5.1.4.1.1.88.11"))?.contains("SOP class") == true, "SR by SOP class")
expect(PreviewIdentity.refusalForPreviewing(frame("/a/seg.dcm", 0, sop: "1.2.840.10008.5.1.4.1.1.66.4"))?.contains("SOP class") == true, "SEG by SOP class")
expect(PreviewIdentity.refusalForPreviewing(frame("/a/ps.dcm", 0, sop: "1.2.840.10008.5.1.4.1.1.11.1"))?.contains("SOP class") == true, "presentation state")
expect(PreviewIdentity.refusalForPreviewing(frame("/a/pdf.dcm", 0, sop: "1.2.840.10008.5.1.4.1.1.104.1"))?.contains("SOP class") == true, "encapsulated PDF")
expect(PreviewIdentity.refusalForPreviewing(frame("/a/ct.dcm", 0, rows: 0))?.contains("no dimensions") == true, "a frame without dimensions")
expect(PreviewIdentity.refusalForPreviewing(frame("/a/multi.dcm", 16, count: 16))?.contains("outside") == true, "a frame past the end")

// 3. Series preview: one series, one geometry, no repeats.
let series = (0..<8).map { frame("/a/\($0).dcm", 0) }
expect(PreviewIdentity.refusalForSeriesPreview(series) == nil, "a single coherent series previews")
expect(PreviewIdentity.refusalForSeriesPreview([]) != nil, "an empty preview is refused")
var mixed = series; mixed[3] = frame("/a/3.dcm", 0, series: "9.9.9")
expect(PreviewIdentity.refusalForSeriesPreview(mixed)?.contains("mix series") == true, "mixed series refused")
var resized = series; resized[5] = frame("/a/5.dcm", 0, rows: 256, columns: 256)
expect(PreviewIdentity.refusalForSeriesPreview(resized)?.contains("mix") == true, "mixed sizes refused")
var repeated = series; repeated[6] = frame("/a/2.dcm", 0)
expect(PreviewIdentity.refusalForSeriesPreview(repeated)?.contains("twice") == true, "a repeated frame refused")
var withSEG = series; withSEG[1] = frame("/a/seg.dcm", 0, modality: "SEG")
expect(PreviewIdentity.refusalForSeriesPreview(withSEG)?.contains("no displayable frame") == true, "a SEG inside a series preview is refused")
let multiframe = (0..<16).map { frame("/a/multi.dcm", $0, count: 16) }
expect(PreviewIdentity.refusalForSeriesPreview(multiframe) == nil, "every frame of one multiframe file is one series")

print("PASS: preview reuse needs file, frame, series and size; SR/SEG/PS/PDF carry no frame; a series preview may not mix series, sizes or repeat a frame")
'''
with tempfile.TemporaryDirectory(prefix='horos-preview-identity-') as folder:
    tmp = Path(folder)
    (tmp / 'main.swift').write_text(driver)
    subprocess.run(['xcrun', 'swiftc', str(root / 'Horos/Sources/PreviewIdentity.swift'), str(tmp / 'main.swift'),
                    '-o', str(tmp / 'test')], check=True)
    subprocess.run([str(tmp / 'test')], check=True)

browser = (root / 'Horos/Sources/BrowserController.m').read_bytes().decode('latin1')
project = (root / 'Horos.xcodeproj/project.pbxproj').read_text()
assert 'if( frameNumber == 0)\n                    i = [[vFileList valueForKey: @"completePath"] indexOfObject: pathToFind];' not in browser, \
    'frame 0 must not match on the path alone'
assert browser.count('expectedFrame') >= 6, 'every reuse site must pass the identity it expects'
assert 'refusalForReusing: loaded asRequested: expectedFrame' in browser, 'the reuse must go through HorosPreviewIdentity'
assert 'HorosPreviewFrameForImage' in browser, 'the expected identity is built from the database row'
assert '[matrixLoadIconsThread cancel]' in browser, 'a new selection must cancel the running icon thread'
assert sum('PreviewIdentity.swift' in line for line in project.splitlines()) == 4, 'PreviewIdentity.swift is not fully registered in the Xcode project'
print('preview wiring: frame-exact reuse through the shared identity, expected identity at every call, icon thread cancelled on selection')
