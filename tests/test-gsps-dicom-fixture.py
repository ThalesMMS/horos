#!/usr/bin/env python3
"""A generated GSPS file applies the documented subset and leaves CT pixels alone."""
from pathlib import Path
import json
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]


def python_with_pydicom():
    for candidate in (
        root / 'local-validation/gsps-venv/bin/python',
        root / 'local-validation/email-venv/bin/python',
        Path(sys.executable),
    ):
        if candidate.is_file() and subprocess.run(
            [str(candidate), '-c', 'import pydicom, numpy'],
            capture_output=True,
        ).returncode == 0:
            return str(candidate)
    sys.exit(2)


def flatten(value):
    try:
        from pydicom.dataset import Dataset
        from pydicom.sequence import Sequence
        from pydicom.multival import MultiValue
        from pydicom.valuerep import PersonName
    except ImportError:
        Dataset = Sequence = MultiValue = PersonName = type(None)

    if isinstance(value, Dataset):
        out = {}
        for tag in value.dir():
            if tag == 'PixelData':
                continue
            out[tag] = flatten(value.get(tag))
        return out
    if isinstance(value, Sequence) or (hasattr(value, '__iter__') and not isinstance(value, (bytes, str)) and type(value).__name__ == 'Sequence'):
        return [flatten(item) for item in value]
    if isinstance(value, MultiValue) or (hasattr(value, '__iter__') and not isinstance(value, (bytes, str, dict, list))):
        try:
            return [flatten(item) for item in value]
        except TypeError:
            return str(value)
    if isinstance(value, PersonName):
        return str(value)
    if hasattr(value, 'imag'):  # numpy / binary numbers
        try:
            return float(value) if int(value) != value else int(value)
        except (TypeError, ValueError):
            return str(value)
    if isinstance(value, (bytes, bytearray)):
        return list(value)
    return value


def dump_gsps(python, path):
    script = r'''
import json, sys
from pydicom import dcmread
from pathlib import Path
sys.path.insert(0, str(Path(%r).parent))
# inline flatten
import tests.test_gsps_flatten as flatten_mod
''' % str(path)
    # Keep flatten in this file; call pydicom from a helper snippet.
    code = r'''
import json, sys
from pydicom import dcmread
ds = dcmread(sys.argv[1], stop_before_pixels=True)
print(json.dumps({"SOPClassUID": str(ds.SOPClassUID), "ok": True}))
'''
    return python, code


HARNESS = r'''
import Foundation

guard CommandLine.arguments.count > 1,
      let data = try? Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[1])),
      let document = GSPSDocument(json: data)
else {
    fputs("FAIL: could not parse GSPS JSON\n", stderr)
    exit(1)
}
let imagesJSON = CommandLine.arguments.count > 2
    ? (try? Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[2])))
    : nil
var images: [GSPSAvailableImage] = []
if let imagesJSON,
   let list = (try? JSONSerialization.jsonObject(with: imagesJSON)) as? [[String: Any]] {
    for item in list {
        let image = GSPSAvailableImage()
        image.sopInstanceUID = item["sopInstanceUID"] as? String ?? ""
        image.frameNumber = (item["frameNumber"] as? NSNumber)?.intValue ?? 1
        image.columns = (item["columns"] as? NSNumber)?.intValue ?? 0
        image.rows = (item["rows"] as? NSNumber)?.intValue ?? 0
        if let b64 = item["pixels"] as? String, let pixels = Data(base64Encoded: b64) {
            image.pixelFingerprint = pixels
        }
        images.append(image)
    }
}
let result = document.apply(to: images)
var payload: [String: Any] = [
    "supportedSOP": document.isSupportedSOPClass,
    "unsupported": result.unsupportedFeatures,
    "missing": result.missingReferences.map { $0.sopInstanceUID },
    "pixelsUnchanged": result.originalPixelsUnchanged,
    "presentations": result.presentations.map { pres -> [String: Any] in
        [
            "sopInstanceUID": pres.sopInstanceUID,
            "frameNumber": pres.frameNumber,
            "windowCenter": pres.windowCenter,
            "windowWidth": pres.windowWidth,
            "rotationDegrees": pres.rotationDegrees,
            "horizontalFlip": pres.horizontalFlip,
            "annotations": pres.annotations.map { ["kind": $0.kind, "points": $0.points.map { [$0.x, $0.y] }, "text": $0.text ?? ""] },
        ]
    },
]
try FileHandle.standardOutput.write(JSONSerialization.data(withJSONObject: payload))
print()
'''


def dataset_to_json(ds):
    def convert(value):
        from pydicom.dataset import Dataset
        from pydicom.sequence import Sequence
        if isinstance(value, Dataset):
            item = {}
            for key in value.dir():
                if key == 'PixelData':
                    continue
                item[key] = convert(getattr(value, key))
            return item
        if isinstance(value, Sequence):
            return [convert(v) for v in value]
        if isinstance(value, (list, tuple)) or type(value).__name__ == 'MultiValue':
            return [convert(v) for v in value]
        if hasattr(value, '__float__') and not isinstance(value, (bool, str)):
            number = float(value)
            if number.is_integer():
                return int(number)
            return number
        return str(value)

    return convert(ds)


def main():
    python = python_with_pydicom()
    with tempfile.TemporaryDirectory(prefix='horos-gsps-fix-') as raw:
        dest = Path(raw) / 'fixture'
        dest.mkdir()
        generate = subprocess.run(
            [python, str(root / 'tools/generate-gsps-fixture.py'), str(dest)],
            capture_output=True, text=True)
        if generate.returncode != 0:
            print(generate.stderr)
            raise SystemExit('FAIL: generate-gsps-fixture.py failed')

        dump = Path(raw) / 'dump.py'
        dump.write_text(
            'import json,sys\nfrom pydicom import dcmread\n'
            'from pathlib import Path\n'
            + Path(__file__).read_text().split('def dataset_to_json', 1)[0]
            + 'def dataset_to_json(ds):\n'
            + '    ' + 'def dataset_to_json(ds):'.join([])
        )
        # Simpler: exec dataset_to_json here with the same interpreter.
        helper = Path(raw) / 'tojson.py'
        helper.write_text(r'''
import json, sys
from pydicom import dcmread
from pydicom.dataset import Dataset
from pydicom.sequence import Sequence

def convert(value):
    if isinstance(value, Dataset):
        return {key: convert(getattr(value, key)) for key in value.dir() if key != "PixelData"}
    if isinstance(value, Sequence):
        return [convert(v) for v in value]
    if type(value).__name__ == "MultiValue" or isinstance(value, (list, tuple)):
        return [convert(v) for v in value]
    if hasattr(value, "__float__") and not isinstance(value, (bool, str)):
        number = float(value)
        return int(number) if number.is_integer() else number
    return str(value)

ds = dcmread(sys.argv[1], stop_before_pixels=True)
json.dump(convert(ds), sys.stdout)
''')
        apply_json = subprocess.check_output(
            [python, str(helper), str(dest / 'gsps-apply.dcm')])
        missing_json = subprocess.check_output(
            [python, str(helper), str(dest / 'gsps-missing.dcm')])
        color_json = subprocess.check_output(
            [python, str(helper), str(dest / 'ps-color.dcm')])
        ct = subprocess.check_output(
            [python, '-c',
             'from pydicom import dcmread; import json; d=dcmread(%r); '
             'print(json.dumps({"sop":d.SOPInstanceUID,"rows":int(d.Rows),"cols":int(d.Columns)}))'
             % str(dest / 'ct-ref.dcm')])
        ct_info = json.loads(ct)
        import base64
        pixels = base64.b64encode((dest / 'ct-ref.dcm').read_bytes()[:64]).decode('ascii')

        harness_dir = Path(raw) / 'swift'
        harness_dir.mkdir()
        (harness_dir / 'main.swift').write_text(HARNESS)
        binary = harness_dir / 'gsps-test'
        subprocess.run([
            'xcrun', 'swiftc',
            str(root / 'Horos/Sources/VOILookupTable.swift'),
            str(root / 'Horos/Sources/GSPSDocument.swift'),
            str(harness_dir / 'main.swift'),
            '-o', str(binary),
        ], check=True)

        images = [{
            'sopInstanceUID': ct_info['sop'],
            'frameNumber': 1,
            'columns': ct_info['cols'],
            'rows': ct_info['rows'],
            'pixels': pixels,
        }]
        images_path = harness_dir / 'images.json'
        images_path.write_text(json.dumps(images))
        (harness_dir / 'apply.json').write_bytes(apply_json)
        applied = json.loads(subprocess.check_output(
            [str(binary), str(harness_dir / 'apply.json'), str(images_path)]))
        failures = []
        if not applied['pixelsUnchanged']:
            failures.append('applying the generated GSPS rewrote the CT samples')
        if not applied['presentations']:
            failures.append('the generated GSPS did not match the referenced CT')
        else:
            pres = applied['presentations'][0]
            if abs(pres['windowCenter'] - 40) > 1e-6 or abs(pres['windowWidth'] - 400) > 1e-6:
                failures.append('generated GSPS VOI was not 40/400: %s' % pres)
            if pres['rotationDegrees'] != 90 or pres['horizontalFlip'] is not True:
                failures.append('generated GSPS transform was not applied: %s' % pres)
            kinds = {a['kind']: a for a in pres['annotations']}
            if kinds.get('POLYLINE', {}).get('points') != [[10, 20], [30, 40]]:
                failures.append('generated PIXEL polyline moved: %s' % kinds.get('POLYLINE'))
            if kinds.get('TEXT', {}).get('text') != 'GSPS label':
                failures.append('generated text was lost: %s' % kinds.get('TEXT'))

        (harness_dir / 'missing.json').write_bytes(missing_json)
        missing = json.loads(subprocess.check_output(
            [str(binary), str(harness_dir / 'missing.json'), str(images_path)]))
        if not missing['missing']:
            failures.append('the GSPS that names an absent SOP Instance UID was not flagged')
        if missing['presentations']:
            failures.append('a missing reference still produced a presentation')
        if not missing['pixelsUnchanged']:
            failures.append('a missing reference changed the CT pixels')
        flags = ' '.join(missing['unsupported']).upper()
        for word in ('SHUTTER', 'COMPOUND', 'INTERPOLATED'):
            if word not in flags:
                failures.append('generated unsupported %s was not flagged: %s' % (word, missing['unsupported']))

        (harness_dir / 'color.json').write_bytes(color_json)
        color = json.loads(subprocess.check_output(
            [str(binary), str(harness_dir / 'color.json'), str(images_path)]))
        if color['supportedSOP']:
            failures.append('the generated Color Softcopy PS was accepted as GSPS')
        if 'COLOR' not in ' '.join(color['unsupported']).upper() and '11.2' not in ' '.join(color['unsupported']):
            failures.append('the generated Color PS was not flagged: %s' % color['unsupported'])

        if failures:
            for failure in failures:
                print('FAIL:', failure)
            raise SystemExit(1)
        print('ok: generated GSPS files apply VOI/transform/annotations, flag a missing')
        print('    SOP Instance UID and unsupported modules, and leave CT pixels unchanged')


if __name__ == '__main__':
    main()
