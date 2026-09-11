#!/usr/bin/env python3
"""Measure the #304 scroll baseline without omitting slices.

    python3 tools/measure-scroll-baseline.py <series-dir> --report report.json
    python3 tools/measure-scroll-baseline.py <catalog-dir> --catalog --report report.json

Refuses --stride or any request that would skip images to make a number look
better. Phases are input, I/O, decode, prepare and present. Event→frame is
their sum for every slice.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scroll_baseline import (  # noqa: E402
    measure_series, same_frame_of_reference, sync_destination_index,
)


def attach_sync(report: dict, source: Path, destination: Path | None) -> None:
    if destination is None:
        return
    mapped = [sync_destination_index(source, destination, index)
              for index in range(report['visited_slices'])]
    report['sync'] = {
        'kind': 'slice-location',
        'paired': True,
        'same_frame_of_reference': same_frame_of_reference(source, destination),
        'destination': str(destination),
        'mapped_indices': mapped,
        'visited_slices': len(mapped),
        'omitted_slices': 0,
    }


def upload_textures(report: dict, frames: int, rows: int, columns: int,
                    probe: Path) -> None:
    if not probe.is_file() or frames <= 0:
        return
    compiled = Path(tempfile.mkdtemp(prefix='horos-scroll-gl-')) / 'probe'
    build = [
        'xcrun', 'clang', '-fobjc-arc', '-DGL_SILENCE_DEPRECATION',
        '-framework', 'OpenGL', '-framework', 'AppKit',
        str(probe), '-o', str(compiled),
    ]
    built = subprocess.run(build, capture_output=True, text=True)
    if built.returncode != 0:
        report['gpu']['note'] = 'GL probe failed to compile: ' + built.stderr[-200:]
        return
    run = subprocess.run(
        [str(compiled), str(columns), str(rows), str(min(frames, 32))],
        capture_output=True, text=True)
    if run.returncode != 0:
        report['gpu']['note'] = 'GL probe failed: ' + (run.stderr or run.stdout)[-200:]
        return
    try:
        uploaded = json.loads(run.stdout)
    except json.JSONDecodeError:
        report['gpu']['note'] = 'GL probe returned no JSON'
        return
    report['gpu'].update(uploaded)
    report['gpu']['sampled'] = True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--report', type=Path)
    parser.add_argument('--catalog', action='store_true')
    parser.add_argument('--device', choices=('wheel', 'trackpad', 'both'),
                        default='both')
    parser.add_argument('--sync-with', type=Path)
    parser.add_argument('--no-ioaccel-log', action='store_true')
    parser.add_argument('--no-gl', action='store_true')
    parser.add_argument('--stride', type=int)
    arguments = parser.parse_args()
    if arguments.stride is not None:
        raise SystemExit('refusing to omit slices: --stride is not allowed')
    del arguments.device  # both devices are always recorded; flag is documentary
    if arguments.catalog:
        series_dirs = sorted(path for path in arguments.directory.iterdir()
                             if path.is_dir() and any(path.glob('*.dcm')))
        if not series_dirs:
            raise SystemExit(f'{arguments.directory} has no series directories')
        reports = []
        for path in series_dirs:
            item = measure_series(path, capture_logs=not arguments.no_ioaccel_log)
            if 'sync-a' in path.name:
                partner = arguments.directory / 'sync-b-100'
                if partner.is_dir():
                    attach_sync(item, path, partner)
            reports.append(item)
        payload = {
            'catalog': True,
            'series': reports,
            'visited_slices': sum(item['visited_slices'] for item in reports),
            'omitted_slices': 0,
        }
    else:
        payload = measure_series(arguments.directory,
                                 capture_logs=not arguments.no_ioaccel_log)
        attach_sync(payload, arguments.directory, arguments.sync_with)
        if not arguments.no_gl:
            probe = Path(__file__).resolve().parent / 'scroll-baseline-gl-probe.m'
            upload_textures(payload, payload['visited_slices'],
                            payload['buffers']['rows'],
                            payload['buffers']['columns'], probe)
    text = json.dumps(payload, indent=2)
    if arguments.report:
        arguments.report.write_text(text + '\n')
    else:
        sys.stdout.write(text + '\n')


if __name__ == '__main__':
    main()
