#!/usr/bin/env python3
"""Run malformed files through the shipped parser and a sanitized upstream build."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile
from dcmtk_build import ROOT, dcmtk_flags

flags = dcmtk_flags()
source = ROOT / 'DCMTK'
driver = ROOT / 'tools/exercise-dicom-parser.cc'
assert '-DDCMTK_MAX_SEQUENCE_NESTING=16' in (ROOT / 'Horos/Scripts/DCMTK/CMake.sh').read_text()


def checked(command, **kwargs):
    result = subprocess.run(command, capture_output=True, **kwargs)
    if result.returncode:
        print((result.stdout + result.stderr).decode('latin1')[-5000:])
        raise SystemExit(1)
    return result


with tempfile.TemporaryDirectory(prefix='horos-parser-') as directory:
    directory = Path(directory)
    corpus = directory / 'corpus'
    checked([sys.executable, str(ROOT / 'tools/generate-malformed-dicom-fixture.py'), str(corpus)])
    files = sorted(str(path) for path in corpus.glob('*.dcm'))
    shipped = directory / 'shipped'
    checked(['xcrun', 'clang++', '-std=c++11', str(driver), *flags, '-o', str(shipped)])
    sanitizer = directory / 'sanitizer'
    cmake = ['cmake', '-S', str(source), '-B', str(sanitizer), '-DCMAKE_BUILD_TYPE=Debug',
             '-DCMAKE_POLICY_VERSION_MINIMUM=3.5', '-DCMAKE_CXX_STANDARD=11',
             '-DDCMTK_ENABLE_STL=ON', '-DDCMTK_ENABLE_CXX11=ON', '-DBUILD_SHARED_LIBS=OFF',
             '-DDCMTK_DEFAULT_DICT=builtin', '-DDCMTK_WITH_OPENSSL=OFF', '-DDCMTK_WITH_XML=OFF',
             '-DDCMTK_WITH_TIFF=OFF', '-DDCMTK_WITH_PNG=OFF', '-DDCMTK_WITH_SNDFILE=OFF',
             '-DDCMTK_WITH_OPENJPEG=OFF', '-DDCMTK_WITH_ICONV=OFF', '-DDCMTK_WITH_ICU=OFF',
             '-DDCMTK_WITH_ZLIB=ON', '-DDCMTK_ENABLE_MANPAGES=OFF', '-DBUILD_APPS=OFF',
             '-DCMAKE_CXX_FLAGS=-fsanitize=address,undefined -fno-omit-frame-pointer -DDCMTK_MAX_SEQUENCE_NESTING=16',
             '-DCMAKE_C_FLAGS=-fsanitize=address,undefined -fno-omit-frame-pointer',
             '-DCMAKE_EXE_LINKER_FLAGS=-fsanitize=address,undefined']
    checked(cmake)
    checked(['cmake', '--build', str(sanitizer), '--target', 'dcmdata', '--parallel', '8'])
    instrumented = directory / 'instrumented'
    includes = ['-I' + str(sanitizer / 'config/include')]
    includes += ['-I' + str(source / module / 'include') for module in ('dcmdata', 'ofstd', 'oflog', 'oficonv')]
    libraries = [str(sanitizer / 'lib' / ('lib' + module + '.a')) for module in ('dcmdata', 'oflog', 'ofstd', 'oficonv')]
    checked(['xcrun', 'clang++', '-std=c++11', '-fsanitize=address,undefined',
             '-fno-sanitize-recover=all', str(driver), *includes, *libraries,
             '-lz', '-liconv', '-o', str(instrumented)])
    for binary in (shipped, instrumented):
        result = checked([str(binary), *files], timeout=120,
                         env={**os.environ, 'ASAN_OPTIONS': 'halt_on_error=1:allocator_may_return_null=1',
                              'UBSAN_OPTIONS': 'halt_on_error=1', 'DCMDICTPATH': ''})
        output = (result.stdout + result.stderr).decode('latin1')
        rows = [line for line in result.stdout.decode('latin1').splitlines() if ' rows=' in line]
        assert len(rows) == len(files), output[-3000:]
        assert any('ordinary.dcm' in line and 'rows=4' in line for line in rows)
        assert any('nested-2000-deep.dcm' in line and 'Maximum sequence nesting depth exceeded' in line for line in rows), rows
        assert 'ERROR: AddressSanitizer' not in output and 'runtime error:' not in output
    print('PASS: shipped and ASan/UBSan parsers read the malformed corpus safely, preserve the control and refuse excessive nesting')
