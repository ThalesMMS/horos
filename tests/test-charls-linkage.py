#!/usr/bin/env python3
"""One CharLS runs, its ABI is the same in every copy, and JPEG-LS decodes right.

Four archives in this build define the CharLS public API. The first part of this
test says which one the application ends up calling and fails if that becomes a
mixture; the second says the parameter block they pass across that boundary has
the same layout in every copy, which is what makes the mixture survivable; the
third decodes JPEG-LS with the application's own helper and compares against an
independent CharLS.
"""
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
failures = []
build = root / 'build/Build/Intermediates.noindex/Horos.build/Debug'


def exported(archive):
    """Symbols an archive defines."""
    listed = subprocess.run(['nm', '-g', str(archive)], capture_output=True, text=True)
    return {line.split()[-1] for line in listed.stdout.splitlines()
            if len(line.split()) >= 3 and line.split()[-2] in 'TDSBW'}


def present(binary):
    listed = subprocess.run(['nm', '-g', str(binary)], capture_output=True, text=True)
    return {line.split()[-1] for line in listed.stdout.splitlines() if line.split()}


# ---------------------------------------------------- 1. who actually runs
copies = {
    'CharLS': build / 'CharLS.build/Install/lib/libCharLS.a',              # the project's submodule
    'dcmtkcharls': build / 'DCMTK.build/Install/lib/libdcmtkcharls.a',     # pinned DCMTK, CharLS 1.x
    'gdcmcharls': build / 'GDCM.build/Install/lib/libgdcmcharls.a',        # GDCM, CharLS 2.x
}
symbols = {}
for name, archive in copies.items():
    if not archive.exists():
        print('skip: %s is not built' % name)
        sys.exit(2)
    symbols[name] = exported(archive)
    if '_JpegLsDecode' not in symbols[name]:
        failures.append('%s does not define JpegLsDecode; this test is stale' % name)

# What tells them apart.
fingerprints = {name: symbols[name] - set().union(*(v for k, v in symbols.items() if k != name))
                for name in symbols}
for name, unique in fingerprints.items():
    if not unique:
        failures.append('%s has no symbol of its own, so it cannot be identified' % name)

shared = set.intersection(*symbols.values())
print('%d symbols are defined by all three CharLS copies, including %s'
      % (len(shared), ', '.join(sorted(s for s in shared if s.startswith('_JpegLs')))))

application = root / 'build/Build/Products/Debug/Horos.app/Contents/MacOS/Horos'
helper = root / 'build/Build/Products/Debug/Horos.app/Contents/Resources/Decompress'
for binary in (application, helper):
    if not binary.exists():
        print('skip: %s is not built' % binary.name)
        sys.exit(2)
    # Zero public CharLS calls is valid when dead stripping removes the host's
    # 2.x path. DCMTK's codec is local and cannot satisfy an external 2.x call.
    defining = [line for line in subprocess.check_output(['nm', '-g', str(binary)], text=True)
                .splitlines() if line.endswith(' T _JpegLsDecode')]
    if len(defining) > 1:
        failures.append('%s exports multiple global JPEG-LS decoders' % binary.name)
    print('%s: %d global CharLS API definitions; DCMTK codec is private' % (binary.name, len(defining)))

# DCMTK's 1.x adapter and codec are partially linked before their private
# definitions are localized. No 1.x reference can bind to GDCM's 2.x API.
isolated = build / 'DCMTK.build/Install/lib/libhorosdcmjpls.a'
if not isolated.is_file():
    print('skipped: rebuild the isolated DCMTK JPEG-LS archive')
    raise SystemExit(2)
if exported(isolated) & symbols['dcmtkcharls']:
    failures.append('isolated DCMTK JPEG-LS still exports codec symbols')
undefined = subprocess.check_output(['nm', '-u', str(isolated)], text=True)
if any(name in undefined for name in ('_JpegLsDecode', '_JpegLsEncode', '_JpegLsReadHeader')):
    failures.append('DCMTK JPEG-LS still resolves its codec outside the isolated object')
project = (root / 'Horos.xcodeproj/project.pbxproj').read_text()
if '"-ldcmjpls"' in project or '"-ldcmtkcharls"' in project:
    failures.append('the host must link the isolated archive, not the colliding stock archives')

# ------------------------------------------ 2. the ABI they pass across
headers = {
    'CharLS': root / 'CharLS/src/publictypes.h',
    'dcmtkcharls': root / 'DCMTK/dcmjpls/libcharls/pubtypes.h',
    'gdcmcharls': root / 'GDCM/Utilities/gdcmcharls/publictypes.h',
}
probe = r'''
#include <cstdio>
#include <cstddef>
#include "HEADER"
int main() {
    printf("%zu %zu %zu %zu %zu %zu %zu %zu %zu %zu %zu\n",
           sizeof(JlsParameters),
           offsetof(JlsParameters, width), offsetof(JlsParameters, height),
           offsetof(JlsParameters, FIELD_BITS), offsetof(JlsParameters, FIELD_STRIDE),
           offsetof(JlsParameters, components), offsetof(JlsParameters, FIELD_ERROR),
           offsetof(JlsParameters, FIELD_ILV), offsetof(JlsParameters, outputBgr),
           offsetof(JlsParameters, custom), offsetof(JlsParameters, jfif));
    return 0;
}
'''
# The 1.x names differ from the 2.x names; the layout is what is being compared.
names = {
    'dcmtkcharls': {'FIELD_BITS': 'bitspersample', 'FIELD_STRIDE': 'bytesperline',
                    'FIELD_ERROR': 'allowedlossyerror', 'FIELD_ILV': 'ilv'},
}
default = {'FIELD_BITS': 'bitsPerSample', 'FIELD_STRIDE': 'stride',
           'FIELD_ERROR': 'allowedLossyError', 'FIELD_ILV': 'interleaveMode'}

layouts = {}
with tempfile.TemporaryDirectory() as directory:
    for name, header in headers.items():
        if not header.exists():
            failures.append('%s: %s is gone' % (name, header))
            continue
        source = probe.replace('HEADER', str(header))
        for placeholder, field in names.get(name, default).items():
            source = source.replace(placeholder, field)
        path = Path(directory) / ('%s.cc' % name)
        path.write_text(source)
        built = subprocess.run(['xcrun', 'clang++', '-std=c++14', str(path),
                                '-o', str(Path(directory) / name)],
                               capture_output=True, text=True)
        if built.returncode != 0:
            print(built.stderr)
            failures.append('%s: the parameter block could not be measured' % name)
            continue
        layouts[name] = subprocess.run([str(Path(directory) / name)],
                                       capture_output=True, text=True).stdout.strip()

if layouts.get('CharLS') != layouts.get('gdcmcharls'):
    failures.append('the host and GDCM CharLS 2 parameter layouts disagree')
for name, layout in sorted(layouts.items()):
    print('  %-14s %s' % (name, layout))
print('CharLS 2 shares its ABI with GDCM; the DCMTK CharLS 1 ABI is local to its adapter')

# ------------------------------------------------- 3. decoding is correct
venv = root / 'local-validation/dcmtk-venv/bin/python'
if not venv.exists():
    print('skip: no python environment with an independent JPEG-LS decoder')
else:
    check = subprocess.run([str(venv), '-c', 'import imagecodecs, pydicom, numpy'],
                           capture_output=True)
    if check.returncode != 0:
        print('skip: install imagecodecs, pydicom and numpy in local-validation/email-venv '
              'to check JPEG-LS decoding')
    else:
        with tempfile.TemporaryDirectory() as directory:
            script = r'''
import sys, numpy as np, pydicom, imagecodecs, subprocess
from pathlib import Path
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import UID
from pydicom.encaps import encapsulate

directory, helper, collection = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
failures = []

def dicom(pixels, near, name):
    """Wrap JPEG-LS encoded pixels in a DICOM the helper can read."""
    encoded = imagecodecs.jpegls_encode(pixels, level=near)
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = UID("1.2.840.10008.5.1.4.1.1.7")
    meta.MediaStorageSOPInstanceUID = UID("1.2.826.0.1.3680043.8.498.7001")
    meta.TransferSyntaxUID = UID("1.2.840.10008.1.2.4.80" if near == 0 else "1.2.840.10008.1.2.4.81")
    meta.ImplementationClassUID = UID("1.2.826.0.1.3680043.8.498.1")
    dataset = FileDataset(str(directory / name), {}, file_meta=meta, preamble=b"\0" * 128)
    dataset.SOPClassUID = meta.MediaStorageSOPClassUID
    dataset.SOPInstanceUID = meta.MediaStorageSOPInstanceUID
    dataset.StudyInstanceUID = UID("1.2.826.0.1.3680043.8.498.7002")
    dataset.SeriesInstanceUID = UID("1.2.826.0.1.3680043.8.498.7003")
    dataset.Modality = "OT"
    dataset.PatientName = "FIXTURE^JPEGLS"
    dataset.PatientID = "JLS-0001"
    dataset.Rows, dataset.Columns = pixels.shape
    dataset.SamplesPerPixel = 1
    dataset.PhotometricInterpretation = "MONOCHROME2"
    dataset.BitsAllocated = 8 if pixels.dtype == np.uint8 else 16
    dataset.BitsStored = dataset.BitsAllocated
    dataset.HighBit = dataset.BitsStored - 1
    dataset.PixelRepresentation = 0
    dataset.PixelData = encapsulate([encoded])
    dataset["PixelData"].is_undefined_length = True
    path = directory / name
    dataset.save_as(path, enforce_file_format=True)
    return path

def decoded(path, output):
    output.mkdir(exist_ok=True)
    for stale in output.iterdir():
        stale.unlink()
    run = subprocess.run([helper, str(output), "decompressList", str(path)],
                         capture_output=True, text=True)
    if run.returncode != 0:
        return None
    produced = output / path.name
    if not produced.exists():
        return None
    return pydicom.dcmread(produced)

# A round trip through the application's decoder, on data it did not produce.
rng = np.random.default_rng(20260909)
cases = [
    ("8 bit gradient, lossless", np.tile(np.arange(256, dtype=np.uint8), (64, 1)), 0),
    ("8 bit noise, lossless", rng.integers(0, 256, (64, 64), dtype=np.uint8), 0),
    ("16 bit ramp, lossless", (np.arange(128 * 128, dtype=np.uint16) % 4096).reshape(128, 128), 0),
    ("16 bit noise, lossless", rng.integers(0, 4096, (96, 96)).astype(np.uint16), 0),
    ("16 bit ramp, near-lossless 2", (np.arange(64 * 64, dtype=np.uint16) % 4096).reshape(64, 64), 2),
]
for label, pixels, near in cases:
    path = dicom(pixels, near, "roundtrip-%d.dcm" % len(label))
    out = decoded(path, directory / "out")
    if out is None:
        failures.append("%s: the helper did not decompress it" % label)
        continue
    if out.file_meta.TransferSyntaxUID != "1.2.840.10008.1.2.1":
        failures.append("%s: came back as %s" % (label, out.file_meta.TransferSyntaxUID.name))
        continue
    got = np.frombuffer(out.PixelData, dtype=pixels.dtype)[:pixels.size].reshape(pixels.shape)
    worst = int(np.abs(got.astype(int) - pixels.astype(int)).max())
    if near == 0:
        if worst != 0:
            failures.append("%s: %d off the original" % (label, worst))
    elif worst > near:
        failures.append("%s: %d off, more than the %d asked for" % (label, worst, near))
print("round trip: %d cases" % len(cases))

# And the real thing, when the example collection is here.
samples, checked = [], 0
if collection.is_dir():
    import struct
    def transfer_syntax(path):
        try:
            head = path.open("rb").read(4096)
        except OSError:
            return None
        if head[128:132] != b"DICM":
            return None
        i = head.find(b"\x02\x00\x10\x00UI")
        if i < 0:
            return None
        n = struct.unpack("<H", head[i + 6:i + 8])[0]
        return head[i + 8:i + 8 + n].rstrip(b"\x00 ").decode("ascii", "replace")
    for path in collection.rglob("*"):
        if len(samples) >= 6:
            break
        if path.is_file() and path.stat().st_size > 200:
            if transfer_syntax(path) in ("1.2.840.10008.1.2.4.80", "1.2.840.10008.1.2.4.81"):
                samples.append(path)

for path in samples:
    working = directory / ("sample-%d.dcm" % checked)
    working.write_bytes(path.read_bytes())
    source = pydicom.dcmread(working)
    out = decoded(working, directory / "out")
    if out is None:
        failures.append("a JPEG-LS sample did not decompress")
        continue
    frames = pydicom.encaps.decode_data_sequence(source.PixelData)
    reference = imagecodecs.jpegls_decode(frames[0])
    got = np.frombuffer(out.PixelData, dtype=reference.dtype)[:reference.size].reshape(reference.shape)
    if not np.array_equal(reference, got):
        failures.append("a JPEG-LS sample decoded differently from the reference")
    checked += 1
print("local samples: %d decoded byte for byte against an independent CharLS" % checked)

for failure in failures:
    print("FAIL: %s" % failure)
sys.exit(1 if failures else 0)
'''
            path = Path(directory) / 'decode.py'
            path.write_text(script)
            ran = subprocess.run([str(venv), str(path), directory, str(helper), str(Path(directory) / 'no-historical-samples')],
                                 capture_output=True, text=True)
            print(ran.stdout.strip())
            if ran.returncode != 0:
                if ran.stderr:
                    print(ran.stderr[-2000:])
                failures.append('JPEG-LS decoding did not match an independent decoder')

for failure in failures:
    print('FAIL: %s' % failure)
sys.exit(1 if failures else 0)
