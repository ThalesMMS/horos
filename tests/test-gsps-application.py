#!/usr/bin/env python3
"""Synthetic GSPS applies VOI, transform and annotations; a missing reference is flagged.

The Horos series 'presentation state' is a zoom/window remembered on the database
object. That is not a DICOM Grayscale Softcopy Presentation State. This test
builds the documented subset in JSON (the same shape a GSPS file is flattened
to), applies it in Swift, and checks coordinates, matching and that the stored
pixels are not rewritten.
"""
from pathlib import Path
import json
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = root / 'Horos/Sources/GSPSDocument.swift'
if not source.is_file():
    raise SystemExit('FAIL: Horos/Sources/GSPSDocument.swift is missing')

GSPS = '1.2.840.10008.5.1.4.1.1.11.1'
COLOR = '1.2.840.10008.5.1.4.1.1.11.2'
IMAGE = '1.2.840.10008.5.1.4.1.1.2'
SOP = '1.2.826.0.1.3680043.8.498.gsps-image'
MISSING = '1.2.826.0.1.3680043.8.498.gsps-absent'
FRAME_SOP = '1.2.826.0.1.3680043.8.498.gsps-frames'

HARNESS = r'''
import Foundation

func die(_ message: String) -> Never {
    FileHandle.standardError.write(Data("FAIL: \(message)\n".utf8))
    exit(1)
}

guard let path = CommandLine.arguments.dropFirst().first else {
    die("usage: gsps-test <case.json>")
}
let data = try Data(contentsOf: URL(fileURLWithPath: path))
guard let root = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
    die("case is not an object")
}
guard let gspsJSON = root["gsps"] else { die("missing gsps") }
let gspsData = try JSONSerialization.data(withJSONObject: gspsJSON)
guard let document = GSPSDocument(json: gspsData) else {
    die("GSPSDocument rejected the object")
}

if let expectSOP = root["expectUnsupportedSOP"] as? Bool, expectSOP {
    guard document.isSupportedSOPClass == false else { die("color PS was accepted as GSPS") }
}

var images: [GSPSAvailableImage] = []
if let raw = root["images"] as? [[String: Any]] {
    for item in raw {
        let image = GSPSAvailableImage()
        image.sopInstanceUID = item["sopInstanceUID"] as? String ?? ""
        image.frameNumber = (item["frameNumber"] as? NSNumber)?.intValue ?? 1
        image.columns = (item["columns"] as? NSNumber)?.intValue ?? 0
        image.rows = (item["rows"] as? NSNumber)?.intValue ?? 0
        if let b64 = item["pixels"] as? String,
           let pixels = Data(base64Encoded: b64) {
            image.pixelFingerprint = pixels
        }
        images.append(image)
    }
}

let result = document.apply(to: images)
var payload: [String: Any] = [
    "supportedSOP": document.isSupportedSOPClass,
    "sopClassUID": document.sopClassUID,
    "subset": GSPSDocument.documentedSubset,
    "unsupported": result.unsupportedFeatures,
    "missing": result.missingReferences.map { ref -> [String: Any] in
        ["sopInstanceUID": ref.sopInstanceUID, "frames": ref.frameNumbers]
    },
    "pixelsUnchanged": result.originalPixelsUnchanged,
    "presentations": result.presentations.map { pres -> [String: Any] in
        var item: [String: Any] = [
            "sopInstanceUID": pres.sopInstanceUID,
            "frameNumber": pres.frameNumber,
            "hasVOI": pres.hasVOI,
            "windowCenter": pres.windowCenter,
            "windowWidth": pres.windowWidth,
            "rotationDegrees": pres.rotationDegrees,
            "horizontalFlip": pres.horizontalFlip,
            "annotations": pres.annotations.map { a -> [String: Any] in
                [
                    "kind": a.kind,
                    "text": a.text ?? "",
                    "points": a.points.map { [$0.x, $0.y] },
                ]
            },
        ]
        if let area = pres.displayedArea {
            item["displayedArea"] = [
                "column": area.column,
                "row": area.row,
                "width": area.width,
                "height": area.height,
                "sizeMode": area.sizeMode,
            ]
        }
        return item
    },
]
if let before = images.first?.pixelFingerprint, let after = result.pixelFingerprints.first {
    payload["fingerprintEqual"] = before == after
}
try FileHandle.standardOutput.write(JSONSerialization.data(withJSONObject: payload, options: [.prettyPrinted]))
print()
'''


def run_case(tmpdir: Path, case: dict) -> dict:
    case_path = tmpdir / 'case.json'
    case_path.write_text(json.dumps(case))
    binary = tmpdir / 'gsps-test'
    if not binary.exists():
        subprocess.run([
            'xcrun', 'swiftc',
            str(root / 'Horos/Sources/VOILookupTable.swift'),
            str(source),
            str(tmpdir / 'main.swift'),
            '-o', str(binary),
        ], check=True)
    out = subprocess.run([str(binary), str(case_path)], check=True, capture_output=True, text=True)
    return json.loads(out.stdout)


def pixels(values):
    return __import__('base64').b64encode(bytes(values)).decode('ascii')


failures = []

with tempfile.TemporaryDirectory(prefix='horos-gsps-') as raw:
    tmp = Path(raw)
    (tmp / 'main.swift').write_text(HARNESS)

    subset = run_case(tmp, {
        'gsps': {
            'SOPClassUID': GSPS,
            'SOPInstanceUID': '1.2.gsps.1',
            'ReferencedSeriesSequence': [{
                'SeriesInstanceUID': '1.2.series',
                'ReferencedImageSequence': [{
                    'ReferencedSOPClassUID': IMAGE,
                    'ReferencedSOPInstanceUID': SOP,
                }],
            }],
        },
        'images': [],
    })
    text = subset['subset']
    for needle in (
        GSPS,
        'PIXEL',
        'DISPLAY',
        'POINT',
        'POLYLINE',
        'CIRCLE',
        'ELLIPSE',
        'Softcopy VOI LUT',
        'Displayed Area',
        'Spatial Transformation',
    ):
        if needle not in text:
            failures.append('documented subset does not name %r' % needle)

    original = [10, 20, 30, 40, 50, 60, 70, 80]
    applied = run_case(tmp, {
        'gsps': {
            'SOPClassUID': GSPS,
            'SOPInstanceUID': '1.2.gsps.apply',
            'ReferencedSeriesSequence': [{
                'SeriesInstanceUID': '1.2.series',
                'ReferencedImageSequence': [{
                    'ReferencedSOPClassUID': IMAGE,
                    'ReferencedSOPInstanceUID': SOP,
                    'ReferencedFrameNumber': [1],
                }],
            }],
            'ImageRotation': 90,
            'ImageHorizontalFlip': 'Y',
            'SoftcopyVOILUTSequence': [{
                'WindowCenter': [40],
                'WindowWidth': [400],
            }],
            'DisplayedAreaSelectionSequence': [{
                'DisplayedAreaTopLeftHandCorner': [11, 11],
                'DisplayedAreaBottomRightHandCorner': [20, 20],
                'PresentationSizeMode': 'SCALE TO FIT',
            }],
            'GraphicAnnotationSequence': [{
                'GraphicObjectSequence': [
                    {
                        'GraphicAnnotationUnits': 'PIXEL',
                        'GraphicDimensions': 2,
                        'NumberOfGraphicPoints': 2,
                        'GraphicData': [10, 20, 30, 40],
                        'GraphicType': 'POLYLINE',
                    },
                    {
                        'GraphicAnnotationUnits': 'DISPLAY',
                        'GraphicDimensions': 2,
                        'NumberOfGraphicPoints': 1,
                        'GraphicData': [0.5, 0.5],
                        'GraphicType': 'POINT',
                    },
                    {
                        'GraphicAnnotationUnits': 'PIXEL',
                        'GraphicDimensions': 2,
                        'NumberOfGraphicPoints': 2,
                        'GraphicData': [8, 8, 8, 12],
                        'GraphicType': 'CIRCLE',
                    },
                    {
                        'GraphicAnnotationUnits': 'PIXEL',
                        'GraphicDimensions': 2,
                        'NumberOfGraphicPoints': 4,
                        'GraphicData': [2, 6, 10, 6, 6, 4, 6, 8],
                        'GraphicType': 'ELLIPSE',
                    },
                ],
                'TextObjectSequence': [{
                    'AnchorPointAnnotationUnits': 'PIXEL',
                    'UnformattedTextValue': 'GSPS label',
                    'AnchorPoint': [10, 20],
                    'AnchorPointVisibility': 'Y',
                }],
            }],
        },
        'images': [{
            'sopInstanceUID': SOP,
            'frameNumber': 1,
            'columns': 32,
            'rows': 32,
            'pixels': pixels(original),
        }],
    })
    if not applied['pixelsUnchanged'] or not applied.get('fingerprintEqual', True):
        failures.append('applying GSPS rewrote the stored pixels')
    if applied['missing']:
        failures.append('a referenced image that was present was reported missing: %s' % applied['missing'])
    if len(applied['presentations']) != 1:
        failures.append('expected one presentation, got %s' % applied['presentations'])
    else:
        pres = applied['presentations'][0]
        if not pres['hasVOI'] or abs(pres['windowCenter'] - 40) > 1e-9 or abs(pres['windowWidth'] - 400) > 1e-9:
            failures.append('VOI window 40/400 was not applied: %s' % pres)
        if pres['rotationDegrees'] != 90 or pres['horizontalFlip'] is not True:
            failures.append('spatial transform 90° + horizontal flip was not applied: %s' % pres)
        area = pres.get('displayedArea') or {}
        if area.get('column') != 10 or area.get('row') != 10 or area.get('width') != 10 or area.get('height') != 10:
            failures.append('displayed area 11\\11-20\\20 (1-based) did not become pixel rect 10,10,10x10: %s' % area)
        kinds = {a['kind']: a for a in pres['annotations']}
        line = kinds.get('POLYLINE')
        if not line or line['points'] != [[10, 20], [30, 40]]:
            failures.append('PIXEL polyline did not keep column\\row coordinates: %s' % line)
        point = kinds.get('POINT')
        if not point or abs(point['points'][0][0] - 15) > 1e-9 or abs(point['points'][0][1] - 15) > 1e-9:
            failures.append('DISPLAY 0.5\\0.5 was not the centre of the displayed area: %s' % point)
        circle = kinds.get('CIRCLE')
        if not circle or circle['points'][0] != [8, 8]:
            failures.append('CIRCLE centre was not kept in pixel space: %s' % circle)
        ellipse = kinds.get('ELLIPSE')
        if not ellipse or [2, 6] not in ellipse['points']:
            failures.append('ELLIPSE axis endpoints were not kept: %s' % ellipse)
        text = kinds.get('TEXT')
        if not text or text.get('text') != 'GSPS label' or text['points'] != [[10, 20]]:
            failures.append('text anchor was not applied at PIXEL 10\\20: %s' % text)

    missing = run_case(tmp, {
        'gsps': {
            'SOPClassUID': GSPS,
            'SOPInstanceUID': '1.2.gsps.missing',
            'ReferencedSeriesSequence': [{
                'SeriesInstanceUID': '1.2.series',
                'ReferencedImageSequence': [{
                    'ReferencedSOPClassUID': IMAGE,
                    'ReferencedSOPInstanceUID': MISSING,
                }],
            }],
            'SoftcopyVOILUTSequence': [{'WindowCenter': [1], 'WindowWidth': [2]}],
            'DisplayShutterSequence': [{'ShutterShape': 'RECTANGULAR'}],
            'CompoundGraphicSequence': [{'CompoundGraphicType': 'RECTANGLE'}],
            'MaskSubtractionSequence': [{'MaskOperation': 'AVG_SUB'}],
            'GraphicAnnotationSequence': [{
                'GraphicObjectSequence': [{
                    'GraphicAnnotationUnits': 'PIXEL',
                    'GraphicData': [0, 0, 1, 1],
                    'GraphicType': 'INTERPOLATED',
                }],
            }],
        },
        'images': [{
            'sopInstanceUID': SOP,
            'frameNumber': 1,
            'columns': 8,
            'rows': 8,
            'pixels': pixels(original),
        }],
    })
    missing_uids = [m['sopInstanceUID'] for m in missing['missing']]
    if MISSING not in missing_uids:
        failures.append('a GSPS that names an absent SOP Instance UID was not flagged')
    if missing['presentations']:
        failures.append('a missing reference still produced a presentation: %s' % missing['presentations'])
    if not missing['pixelsUnchanged'] or not missing.get('fingerprintEqual', True):
        failures.append('a missing reference changed the original pixels')
    joined = ' '.join(missing['unsupported']).upper()
    for flag in ('SHUTTER', 'COMPOUND', 'MASK', 'INTERPOLATED'):
        if flag not in joined:
            failures.append('unsupported %s was not flagged: %s' % (flag, missing['unsupported']))

    color = run_case(tmp, {
        'expectUnsupportedSOP': True,
        'gsps': {
            'SOPClassUID': COLOR,
            'SOPInstanceUID': '1.2.gsps.color',
            'ReferencedSeriesSequence': [{
                'ReferencedImageSequence': [{
                    'ReferencedSOPInstanceUID': SOP,
                }],
            }],
        },
        'images': [{'sopInstanceUID': SOP, 'frameNumber': 1, 'columns': 8, 'rows': 8, 'pixels': pixels(original)}],
    })
    if color['supportedSOP']:
        failures.append('Color Softcopy Presentation State was treated as the documented GSPS subset')
    if 'COLOR' not in ' '.join(color['unsupported']).upper() and '1.2.840.10008.5.1.4.1.1.11.2' not in ' '.join(color['unsupported']):
        failures.append('an unsupported presentation-state SOP class was not flagged: %s' % color['unsupported'])

    frames = run_case(tmp, {
        'gsps': {
            'SOPClassUID': GSPS,
            'SOPInstanceUID': '1.2.gsps.frame',
            'ReferencedSeriesSequence': [{
                'ReferencedImageSequence': [{
                    'ReferencedSOPInstanceUID': FRAME_SOP,
                    'ReferencedFrameNumber': [2],
                }],
            }],
            'SoftcopyVOILUTSequence': [{'WindowCenter': [80], 'WindowWidth': [200]}],
        },
        'images': [
            {'sopInstanceUID': FRAME_SOP, 'frameNumber': 1, 'columns': 8, 'rows': 8, 'pixels': pixels(original)},
            {'sopInstanceUID': FRAME_SOP, 'frameNumber': 2, 'columns': 8, 'rows': 8, 'pixels': pixels(original)},
        ],
    })
    matched = {(p['sopInstanceUID'], p['frameNumber']) for p in frames['presentations']}
    if (FRAME_SOP, 2) not in matched:
        failures.append('frame 2 of a referenced multi-frame image was not matched')
    if (FRAME_SOP, 1) in matched:
        failures.append('frame 1 was presented although the GSPS named only frame 2')
    if not any(m['sopInstanceUID'] == FRAME_SOP and 1 in (m.get('frames') or []) for m in frames['missing']):
        # Frame 1 is available but not referenced; it is not a missing GSPS reference.
        pass
    if any(m['sopInstanceUID'] == FRAME_SOP and 2 in (m.get('frames') or []) for m in frames['missing']):
        failures.append('referenced frame 2 was reported missing while present')

if failures:
    for failure in failures:
        print('FAIL:', failure)
    raise SystemExit(1)
print('ok: documented GSPS subset applies VOI, 90°/flip, PIXEL and DISPLAY annotations,')
print('    flags unsupported modules and a missing SOP Instance UID, and leaves pixels unchanged')
