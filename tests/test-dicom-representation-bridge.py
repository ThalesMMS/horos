#!/usr/bin/env python3
"""Exercise the built codec bridge with independent pixels and nested metadata.

Usage: PYTHON test-dicom-representation-bridge.py DECOMPRESS_HELPER
Requires pydicom, numpy and imagecodecs; all data is synthetic and temporary.
"""
from pathlib import Path
import hashlib
import importlib.util
import plistlib
import subprocess
import sys
import tempfile

if len(sys.argv) != 2:
    print('skipped: needs the built Decompress helper and pydicom/numpy/imagecodecs', file=sys.stderr)
    raise SystemExit(2)

import imagecodecs
import numpy as np
import pydicom
from pydicom.encaps import generate_frames

root = Path(__file__).resolve().parents[1]
helper = Path(sys.argv[1]).resolve()
spec = importlib.util.spec_from_file_location('fixture', root/'tools/generate-dimse-matrix-fixture.py')
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)

def pixels(ds):
    decoder = {'1.2.840.10008.1.2.4.90': imagecodecs.jpeg2k_decode,
               '1.2.840.10008.1.2.4.80': imagecodecs.jpegls_decode}.get(str(ds.file_meta.TransferSyntaxUID))
    values = np.stack([decoder(frame) for frame in generate_frames(ds.PixelData)]) if decoder else ds.pixel_array
    return hashlib.sha256(values.astype('<u2').tobytes()).hexdigest()

with tempfile.TemporaryDirectory(prefix='horos-representation-') as temporary:
    work = Path(temporary)
    manifest = fixture.generate(work/'source', include_jpeg2000=True)
    for entry in manifest['instances']:
        if entry['pixelSHA256'] is None:
            continue
        source = work/'source'/entry['file']
        original = source.read_bytes()
        expected = pydicom.dcmread(source)
        for name, compression, syntax in [('jpeg2000', 3, '1.2.840.10008.1.2.4.90'),
                                          ('jpegls', 4, '1.2.840.10008.1.2.4.80')]:
            output = work/(name+'-'+source.name)
            output.write_bytes(original)
            settings = work/'settings.plist'
            codec = [{'modality': 'default', 'compression': compression, 'quality': 0}]
            settings.write_bytes(plistlib.dumps({'CompressionSettings': codec,
                'CompressionSettingsLowRes': codec, 'DecompressMoveIfFail': False}))
            for mode in ('compress', 'decompressList'):
                result = subprocess.run([str(helper), 'sameAsDestination', 'SettingsPlist',
                    str(settings), mode, str(output)], capture_output=True, timeout=60)
                assert result.returncode == 0, (name, entry['file'], mode, result.stderr)
                actual = pydicom.dcmread(output)
                assert actual.file_meta.TransferSyntaxUID == (syntax if mode == 'compress' else '1.2.840.10008.1.2.1')
                assert pixels(actual) == entry['pixelSHA256'], (name, entry['file'], mode, 'pixels')
                for tag in ('SOPClassUID', 'SOPInstanceUID', 'StudyInstanceUID', 'SeriesInstanceUID',
                            'FrameOfReferenceUID', 'SpecificCharacterSet', 'PatientName', 'NumberOfFrames',
                            'SegmentSequence', 'SharedFunctionalGroupsSequence', 'PerFrameFunctionalGroupsSequence'):
                    assert getattr(actual, tag, None) == getattr(expected, tag, None), (name, entry['file'], mode, tag)
            assert source.read_bytes() == original
            print('PASS', name, entry['file'], 'encode/decode, independent pixels and metadata', flush=True)
