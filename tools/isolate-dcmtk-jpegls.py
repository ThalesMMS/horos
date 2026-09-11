#!/usr/bin/env python3
"""Keep DCMTK's CharLS 1 ABI local to its JPEG-LS adapter on macOS.

GDCM and the host's CharLS 2 export the same C names and many C++ templates with
different layouts. Partial linking resolves the stock DCMTK adapter against its
own codec, then localizes every codec definition. No upstream source is changed.
"""
import argparse
from pathlib import Path
import subprocess
import tempfile


def definitions(path):
    output = subprocess.check_output(['xcrun', 'nm', '-g', str(path)], text=True)
    return {line.split()[-1] for line in output.splitlines()
            if len(line.split()) >= 3 and line.split()[-2] in 'TDSBW'}


def isolate(directory, architecture, deployment):
    codec = directory / 'libdcmtkcharls.a'
    adapter = directory / 'libdcmjpls.a'
    private = definitions(codec)
    if '_JpegLsDecode' not in private:
        raise RuntimeError('The pinned DCMTK CharLS symbol inventory changed')
    sdk = subprocess.check_output(['xcrun', '--sdk', 'macosx', '--show-sdk-version'], text=True).strip()
    with tempfile.TemporaryDirectory(prefix='horos-jpegls-', dir=directory) as temporary:
        temporary = Path(temporary)
        symbols = temporary / 'private-symbols.txt'
        symbols.write_text('\n'.join(sorted(private)) + '\n')
        object_file = temporary / 'dcmtk-jpegls.o'
        subprocess.run(['xcrun', 'ld', '-r', '-arch', architecture, '-platform_version',
                        'macos', deployment, sdk, '-all_load', str(adapter), str(codec),
                        '-unexported_symbols_list', str(symbols), '-o', str(object_file)], check=True)
        if private & definitions(object_file):
            raise RuntimeError('The isolated JPEG-LS object still exports CharLS symbols')
        archive = temporary / 'libhorosdcmjpls.a'
        subprocess.run(['xcrun', 'libtool', '-static', '-o', str(archive), str(object_file)], check=True)
        archive.replace(directory / archive.name)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--architecture', required=True, choices=['arm64'])
    parser.add_argument('--deployment', required=True)
    args = parser.parse_args()
    isolate(args.directory, args.architecture, args.deployment)
