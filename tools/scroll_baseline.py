"""Reusable #304 scroll/IOAccel methodology: fixtures, phases, host index math."""
from __future__ import annotations

import json
import math
import platform
import resource
import statistics
import subprocess
import sys
import time
import uuid
from pathlib import Path

AXIAL = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0]
CATALOG_SLICES = (100, 500, 1250)
UID_ROOT = 'urn:horos:scroll-baseline:'


def uid(name: str) -> str:
    return '2.25.' + str(uuid.uuid5(uuid.NAMESPACE_URL, UID_ROOT + name).int)


def catalog_series() -> list[dict]:
    series = []
    for modality in ('CT', 'MR'):
        study = uid(f'study-{modality.lower()}')
        for count in CATALOG_SLICES:
            name = f'{modality.lower()}-{count}'
            series.append({
                'name': name,
                'modality': modality,
                'slices': count,
                'spacing_mm': 0.5,
                'size': 64,
                'orientation': list(AXIAL),
                'study_uid': study,
                'series_uid': uid(f'series-{name}'),
                'frame_of_reference': uid(f'for-{name}'),
            })
    shared = uid('for-sync')
    for name in ('sync-a-100', 'sync-b-100'):
        series.append({
            'name': name,
            'modality': 'CT',
            'slices': 100,
            'spacing_mm': 0.5,
            'size': 64,
            'orientation': list(AXIAL),
            'study_uid': uid('study-sync'),
            'series_uid': uid(f'series-{name}'),
            'frame_of_reference': shared,
        })
    return series


def catalog_plan() -> dict:
    return {
        'issue': 304,
        'skip_slices': False,
        'spacing_mm': 0.5,
        'size': 64,
        'orientation': list(AXIAL),
        'series': catalog_series(),
    }


def wheel_sign(reversed: bool, flipped: bool) -> float:
    return (-1.0 if reversed else 1.0) * (-1.0 if flipped else 1.0)


def image_index_by_adding_scroll(current: int, change: float) -> tuple[int, int]:
    if not math.isfinite(change):
        return current, 0
    # Match HorosImageIndexByAddingScroll: truncate toward zero, clamp to short.
    next_index = max(-32768, min(32767, current + math.trunc(change)))
    increment = max(-32768, min(32767, next_index - current))
    return int(next_index), int(increment)


def wheel_step(current: int, delta_y: float, *, precise: bool, reversed: bool,
               flipped: bool, rows: int = 1, columns: int = 1,
               compact: bool = False) -> tuple[int, int]:
    """Ordinary 2D wheel/trackpad step from DCMView.scrollWheel:.

    Classic wheel events replace deltaY with scrollingDeltaY before this
    function; pass that value as delta_y. Precise trackpad events keep deltaY.
    The precise flag documents the path; it does not change the arithmetic.
    """
    del precise
    change = wheel_sign(reversed, flipped) * delta_y / 2.5
    if change > 0:
        if compact:
            change = 1
        elif change < 1:
            change = 1
    else:
        if compact:
            change = -1
        elif change > -1:
            change = -1
    return image_index_by_adding_scroll(current, rows * columns * change)


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    rank = (q / 100.0) * (len(ordered) - 1)
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return float(ordered[low])
    return float(ordered[low] * (high - rank) + ordered[high] * (rank - low))


def summarize(values: list[float]) -> dict:
    return {
        'n': len(values),
        'min': min(values) if values else 0.0,
        'max': max(values) if values else 0.0,
        'mean': statistics.fmean(values) if values else 0.0,
        'p50': percentile(values, 50),
        'p95': percentile(values, 95),
    }


def host_context(revision: str | None = None) -> dict:
    if revision is None:
        git = subprocess.run(['git', 'rev-parse', 'HEAD'], capture_output=True,
                             text=True)
        revision = git.stdout.strip() if git.returncode == 0 else 'unknown'
    cpu = subprocess.run(['sysctl', '-n', 'machdep.cpu.brand_string'],
                         capture_output=True, text=True)
    version = subprocess.run(['sw_vers', '-productVersion'], capture_output=True,
                             text=True)
    build = subprocess.run(['sw_vers', '-buildVersion'], capture_output=True,
                           text=True)
    return {
        'revision': revision,
        'architecture': platform.machine(),
        'os': f'macOS {version.stdout.strip()} {build.stdout.strip()}'.strip(),
        'cpu': cpu.stdout.strip(),
        'python': sys.version.split()[0],
        'scale': 1.0,
        'orientation': list(AXIAL),
        'spacing_mm': 0.5,
        'scroll_wheel_reversed': True,
        'loop_scroll_wheel': False,
        'synchronization': 'slice-location',
        'intel_in_scope': False,
    }


def gpu_context() -> dict:
    probe = subprocess.run(
        ['system_profiler', 'SPDisplaysDataType', '-json'],
        capture_output=True, text=True)
    name = 'unknown'
    if probe.returncode == 0 and probe.stdout.strip():
        try:
            data = json.loads(probe.stdout)
            cards = data.get('SPDisplaysDataType') or []
            if cards:
                name = cards[0].get('sppci_model') or cards[0].get('_name') or name
        except json.JSONDecodeError:
            pass
    return {
        'name': name,
        'sampled': False,
        'note': 'chip identity only until a presentation probe uploads a texture',
    }


def read_series(directory: Path) -> list[Path]:
    files = sorted(directory.glob('*.dcm'))
    if not files:
        raise SystemExit(f'{directory} has no DICOM files')
    return files


def _dataset(path: Path):
    import pydicom
    return pydicom.dcmread(path, force=True)


def same_frame_of_reference(first: Path, second: Path) -> bool:
    a = _dataset(next(path for path in read_series(first)))
    b = _dataset(next(path for path in read_series(second)))
    return str(getattr(a, 'FrameOfReferenceUID', '')) == str(
        getattr(b, 'FrameOfReferenceUID', ''))


def sync_destination_index(source: Path, destination: Path, source_index: int) -> int:
    src = [_dataset(path) for path in read_series(source)]
    dst = [_dataset(path) for path in read_series(destination)]
    src.sort(key=lambda item: int(item.InstanceNumber))
    dst.sort(key=lambda item: int(item.InstanceNumber))
    location = float(src[source_index].SliceLocation)
    nearest = min(range(len(dst)),
                  key=lambda index: abs(float(dst[index].SliceLocation) - location))
    return nearest


def measure_mpr_control(directory: Path) -> dict:
    files = read_series(directory)
    times = []
    for path in files:
        started = time.perf_counter()
        dataset = _dataset(path)
        pixels = dataset.pixel_array
        _ = pixels.astype('float32')
        times.append((time.perf_counter() - started) * 1000.0)
    return {
        'kind': 'sequential-index-walk',
        'visited_slices': len(files),
        'omitted_slices': 0,
        'event_to_frame_ms': summarize(times),
        'native_mpr2d_window': False,
        'note': ('MPR2DView.scrollWheelInt moves the original-view crosshair; '
                 'this control is a full sequential walk of the same volume, '
                 'not a launched MPR window.'),
    }


def _windowed_bytes(pixels, intercept: float, slope: float,
                    center: float, width: float) -> bytes:
    import numpy
    hu = pixels.astype(numpy.float32) * slope + intercept
    low = center - width / 2.0
    scale = 255.0 / width if width else 1.0
    clipped = numpy.clip((hu - low) * scale, 0, 255).astype(numpy.uint8)
    return clipped.tobytes()


def _phase_times(path: Path, cached=None) -> tuple[dict, object]:
    import pydicom
    phases = {}
    started = time.perf_counter()
    raw = path.read_bytes()
    phases['io_ms'] = (time.perf_counter() - started) * 1000.0
    started = time.perf_counter()
    dataset = pydicom.dcmread(path, force=True)
    pixels = dataset.pixel_array
    phases['decode_ms'] = (time.perf_counter() - started) * 1000.0
    intercept = float(getattr(dataset, 'RescaleIntercept', 0) or 0)
    slope = float(getattr(dataset, 'RescaleSlope', 1) or 1)
    center = float(getattr(dataset, 'WindowCenter', 40) or 40)
    if isinstance(center, (list, tuple)):
        center = float(center[0])
    width = float(getattr(dataset, 'WindowWidth', 400) or 400)
    if isinstance(width, (list, tuple)):
        width = float(width[0])
    started = time.perf_counter()
    display = pixels.astype('float32') * slope + intercept
    phases['prepare_ms'] = (time.perf_counter() - started) * 1000.0
    started = time.perf_counter()
    present = _windowed_bytes(pixels, intercept, slope, center, width)
    phases['present_ms'] = (time.perf_counter() - started) * 1000.0
    started = time.perf_counter()
    index, increment = wheel_step(max(int(dataset.InstanceNumber) - 2, 0), -2.5,
                                  precise=False, reversed=True, flipped=False)
    phases['input_ms'] = (time.perf_counter() - started) * 1000.0
    phases['event_to_frame_ms'] = (phases['input_ms'] + phases['io_ms']
                                   + phases['decode_ms'] + phases['prepare_ms']
                                   + phases['present_ms'])
    phases['instance_number'] = int(dataset.InstanceNumber)
    phases['bytes_read'] = len(raw)
    phases['present_bytes'] = len(present)
    phases['rows'] = int(dataset.Rows)
    phases['columns'] = int(dataset.Columns)
    del cached, index, increment, display
    return phases, dataset


def lost_input(present_p50_ms: float, event_hz: float, burst: int = 60) -> dict:
    interval_ms = 1000.0 / event_hz if event_hz else 0.0
    dropped = 0
    if present_p50_ms > interval_ms and interval_ms:
        # One presented frame occupies the thread; later events in that
        # window coalesce to the last one, matching a busy scrollWheel:.
        dropped = max(0, burst - max(1, math.floor(burst * interval_ms / present_p50_ms)))
    return {
        'event_hz': event_hz,
        'present_p50_ms': present_p50_ms,
        'burst': burst,
        'dropped': dropped,
        'note': 'coalesced while presentation occupies the thread; not a lost HID packet',
    }


def gesture_walk(count: int, *, precise: bool) -> dict:
    events = []
    index = 0
    # Trackpad: several small precise deltas per slice. Wheel: one notch.
    deltas = ((-0.4,) * 4) if precise else (-2.5,)
    while index < count - 1:
        for delta in deltas:
            nxt, increment = wheel_step(index, delta, precise=precise,
                                        reversed=True, flipped=False)
            nxt = max(0, min(count - 1, nxt))
            events.append({
                'from': index,
                'to': nxt,
                'increment': increment,
                'delta_y': delta,
                'precise': precise,
            })
            if nxt == index:
                index += 1
                break
            index = nxt
            if index >= count - 1:
                break
    return {
        'device': 'trackpad' if precise else 'wheel',
        'events': events,
        'visited_end': index == count - 1 or count <= 1,
    }


def capture_ioaccel(since: str | None = None) -> dict:
    command = [
        'log', 'show', '--style', 'compact', '--last', since or '2m',
        '--predicate',
        'eventMessage CONTAINS[c] "IOAccel" OR eventMessage CONTAINS[c] "IOAccelerator"',
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    sample = lines[:8]
    return {
        'command': command,
        'captured': result.returncode == 0,
        'line_count': len(lines),
        'sample': sample,
        'stderr': result.stderr.strip()[:400],
        'historical_descriptor_is_not_proof': True,
        'note': ('A descriptor message is a log line, not a leak, driver '
                 'verdict or current regression.'),
    }


def measure_series(directory: Path, *, capture_logs: bool = True) -> dict:
    files = read_series(directory)
    cold = []
    hot = []
    instances = []
    bytes_read = 0
    present_bytes = 0
    rows = columns = 0
    for path in files:
        phases, dataset = _phase_times(path)
        cold.append(phases)
        instances.append(phases['instance_number'])
        bytes_read += phases['bytes_read']
        present_bytes = phases['present_bytes']
        rows = phases['rows']
        columns = phases['columns']
        started = time.perf_counter()
        pixels = dataset.pixel_array
        intercept = float(getattr(dataset, 'RescaleIntercept', 0) or 0)
        slope = float(getattr(dataset, 'RescaleSlope', 1) or 1)
        center = float(getattr(dataset, 'WindowCenter', 40) or 40)
        width = float(getattr(dataset, 'WindowWidth', 400) or 400)
        if isinstance(center, (list, tuple)):
            center = float(center[0])
        if isinstance(width, (list, tuple)):
            width = float(width[0])
        _windowed_bytes(pixels, intercept, slope, center, width)
        hot.append((time.perf_counter() - started) * 1000.0)
    def column(name):
        return [item[name] for item in cold]
    present = summarize(column('present_ms'))
    usage = resource.getrusage(resource.RUSAGE_SELF)
    gpu = gpu_context()
    ioaccel = capture_ioaccel() if capture_logs else {
        'captured': False,
        'line_count': 0,
        'sample': [],
        'historical_descriptor_is_not_proof': True,
        'note': 'log capture skipped by request',
    }
    dominant = max(
        (('io', summarize(column('io_ms'))['p50']),
         ('decode', summarize(column('decode_ms'))['p50']),
         ('prepare', summarize(column('prepare_ms'))['p50']),
         ('present', present['p50'])),
        key=lambda item: item[1],
    )
    return {
        'directory': str(directory),
        'visited_slices': len(files),
        'omitted_slices': 0,
        'instance_numbers': instances,
        'input_ms': summarize(column('input_ms')),
        'io_ms': summarize(column('io_ms')),
        'decode_ms': summarize(column('decode_ms')),
        'prepare_ms': summarize(column('prepare_ms')),
        'present_ms': present,
        'event_to_frame_ms': summarize(column('event_to_frame_ms')),
        'cache': {
            'cold': summarize(column('event_to_frame_ms')),
            'hot': summarize(hot),
        },
        'cpu': {
            'user_s': usage.ru_utime,
            'system_s': usage.ru_stime,
        },
        'gpu': gpu,
        'buffers': {
            'decoded_frames_kept': len(files),
            'presentation_frames_kept': 1,
            'present_bytes': present_bytes,
            'rows': rows,
            'columns': columns,
            'note': 'single presentation buffer, like one DCMView texture',
        },
        'memory': {
            'max_rss_bytes': usage.ru_maxrss,
            'bytes_read': bytes_read,
        },
        'lost_input': lost_input(present['p50'], 120),
        'wheel': gesture_walk(len(files), precise=False),
        'trackpad': gesture_walk(len(files), precise=True),
        'sync': {
            'kind': 'slice-location',
            'paired': False,
            'identity_index': True,
            'note': 'same-series control; pair two FoR-sharing series for two-viewer sync',
        },
        'mpr_control': measure_mpr_control(directory),
        'ioaccel': ioaccel,
        'dominant_phase': {'name': dominant[0], 'p50_ms': dominant[1]},
        'host': host_context(),
    }
