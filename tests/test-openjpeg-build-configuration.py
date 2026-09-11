#!/usr/bin/env python3
"""Run the dependency's real configure step and check its C compiler behavior."""
import json
import os
from pathlib import Path
import platform
import shlex
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
cmake = shutil.which('cmake')
if platform.system() != 'Darwin' or not cmake or not shutil.which('pkg-config'):
    print('skipped: needs macOS, CMake and pkg-config')
    raise SystemExit(2)

with tempfile.TemporaryDirectory(prefix='horos-openjpeg-config-') as temporary:
    work = Path(temporary)
    environment = {**os.environ, 'PROJECT_DIR': str(ROOT), 'TARGET_NAME': 'OpenJPEG',
        'TARGET_TEMP_DIR': str(work), 'ARCHS': platform.machine(),
        'MACOSX_DEPLOYMENT_TARGET': '26.0', 'SDK_NAME': 'macosx',
        'OTHER_CFLAGS': '-fvisibility=default', 'OTHER_CPLUSPLUSFLAGS': '',
        'CLANG_CXX_LANGUAGE_STANDARD': '', 'CLANG_CXX_LIBRARY': ''}
    for configuration in ('Debug', 'Release'):
        # Reuse the directory: changing the configuration must invalidate the cache.
        subprocess.run(['/bin/bash', str(ROOT/'Horos/Scripts/OpenJPEG/CMake.sh')],
            cwd=ROOT, env={**environment, 'CONFIGURATION': configuration},
            check=True, capture_output=True, text=True, timeout=60)
        build = work/'CMake'
        subprocess.run([cmake, '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON', '.'], cwd=build,
            check=True, capture_output=True, text=True, timeout=60)
        entries = json.loads((build/'compile_commands.json').read_text())
        entry = next(row for row in entries if row['file'].endswith('/openjpeg.c'))
        command = shlex.split(entry['command'])
        output_index = command.index('-o')
        del command[output_index:output_index+2]
        command.remove('-c')
        macros = subprocess.check_output([*command, '-dM', '-E'],
            cwd=entry['directory'], text=True, timeout=30)
        optimized = '#define __OPTIMIZE__ 1' in macros
        if optimized != (configuration == 'Release'):
            raise SystemExit(f'{configuration}: unexpected C optimization: {entry["command"]}')
        print(f'PASS: {configuration} C compilation optimization={optimized}')
