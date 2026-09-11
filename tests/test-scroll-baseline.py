#!/usr/bin/env python3
"""Contract for the #304 scroll/IOAccel baseline: fixtures, phases, no skipped slices."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
try:
    import numpy
    import pydicom
except ImportError as error:
    print('need pydicom and numpy to exercise the scroll baseline tools:', error,
          file=sys.stderr)
    sys.exit(2)

generate = root / 'tools' / 'generate-scroll-baseline-fixture.py'
measure = root / 'tools' / 'measure-scroll-baseline.py'
for path in (generate, measure):
    if not path.is_file():
        print(f'FAIL: missing {path.relative_to(root)}', file=sys.stderr)
        sys.exit(1)

sys.path.insert(0, str(root / 'tools'))
import scroll_baseline as probe  # noqa: E402


def run(args):
    return subprocess.run([sys.executable, *args], cwd=root, text=True,
                          capture_output=True)


def test_plan_lists_required_catalog():
    result = run([str(generate), '--plan'])
    assert result.returncode == 0, result.stderr
    plan = json.loads(result.stdout)
    names = {item['name']: item for item in plan['series']}
    for name, modality, slices in (
            ('ct-100', 'CT', 100), ('ct-500', 'CT', 500), ('ct-1250', 'CT', 1250),
            ('mr-100', 'MR', 100), ('mr-500', 'MR', 500), ('mr-1250', 'MR', 1250),
            ('sync-a-100', 'CT', 100), ('sync-b-100', 'CT', 100)):
        item = names[name]
        assert item['modality'] == modality
        assert item['slices'] == slices
        assert item['spacing_mm'] == 0.5
        assert item['size'] == 64
        assert item['orientation'] == [1.0, 0.0, 0.0, 0.0, 1.0, 0.0]
    assert names['sync-a-100']['frame_of_reference'] == names['sync-b-100']['frame_of_reference']
    assert names['sync-a-100']['series_uid'] != names['sync-b-100']['series_uid']
    assert plan['skip_slices'] is False


def test_generator_writes_half_millimetre_axial_series():
    with tempfile.TemporaryDirectory(prefix='horos-scroll-fix-') as folder:
        dest = Path(folder) / 'ct'
        result = run([str(generate), str(dest), '--modality', 'CT', '--slices', '8',
                      '--spacing', '0.5', '--size', '64'])
        assert result.returncode == 0, result.stderr
        files = sorted(dest.glob('*.dcm'))
        assert len(files) == 8
        occupied = Path(folder) / 'again'
        occupied.mkdir()
        (occupied / 'keep').write_text('x')
        refused = run([str(generate), str(occupied), '--modality', 'MR', '--slices', '4'])
        assert refused.returncode != 0
        first = pydicom.dcmread(files[0])
        last = pydicom.dcmread(files[-1])
        assert first.Modality == 'CT'
        assert first.Rows == first.Columns == 64
        assert float(first.SliceThickness) == 0.5
        assert float(first.SpacingBetweenSlices) == 0.5
        assert [float(v) for v in first.ImageOrientationPatient] == [1, 0, 0, 0, 1, 0]
        assert [float(v) for v in last.ImagePositionPatient] == [0, 0, 3.5]
        uids = {pydicom.dcmread(path).SOPInstanceUID for path in files}
        assert len(uids) == 8
        pixels = first.pixel_array
        assert pixels.shape == (64, 64)
        assert int(pixels[0, 0]) != int(pixels[-1, -1])


def test_measurer_visits_every_slice_and_reports_required_metrics():
    with tempfile.TemporaryDirectory(prefix='horos-scroll-measure-') as folder:
        dest = Path(folder) / 'mr'
        created = run([str(generate), str(dest), '--modality', 'MR', '--slices', '6',
                       '--spacing', '0.5'])
        assert created.returncode == 0, created.stderr
        report_path = Path(folder) / 'report.json'
        measured = run([str(measure), str(dest), '--report', str(report_path),
                        '--device', 'both', '--no-ioaccel-log'])
        assert measured.returncode == 0, measured.stderr + measured.stdout
        report = json.loads(report_path.read_text())
        assert report['visited_slices'] == 6
        assert report['omitted_slices'] == 0
        assert report['instance_numbers'] == [1, 2, 3, 4, 5, 6]
        for key in ('event_to_frame_ms', 'input_ms', 'io_ms', 'decode_ms',
                    'prepare_ms', 'present_ms', 'cpu', 'gpu', 'buffers',
                    'memory', 'cache', 'lost_input', 'wheel', 'trackpad',
                    'sync', 'mpr_control', 'ioaccel', 'host'):
            assert key in report, key
        for series in (report['event_to_frame_ms'], report['io_ms'],
                       report['decode_ms'], report['prepare_ms'], report['present_ms']):
            assert series['n'] == 6
            assert series['p50'] <= series['p95']
        assert report['cache']['cold']['n'] == 6
        assert report['cache']['hot']['n'] == 6
        assert report['wheel']['events']
        assert report['trackpad']['events']
        assert report['lost_input']['dropped'] >= 0
        assert report['host']['architecture'] == 'arm64'
        assert report['gpu']['sampled'] in (True, False)
        assert report['ioaccel']['historical_descriptor_is_not_proof'] is True


def test_measurer_refuses_to_drop_slices_for_a_prettier_number():
    with tempfile.TemporaryDirectory(prefix='horos-scroll-skip-') as folder:
        dest = Path(folder) / 'ct'
        created = run([str(generate), str(dest), '--modality', 'CT', '--slices', '5',
                       '--spacing', '0.5'])
        assert created.returncode == 0, created.stderr
        skipped = run([str(measure), str(dest), '--stride', '2'])
        assert skipped.returncode != 0
        assert 'omit' in (skipped.stderr + skipped.stdout).lower() or \
            'stride' in (skipped.stderr + skipped.stdout).lower()


def test_wheel_and_trackpad_use_the_host_index_formula():
    source = (root / 'Horos' / 'Sources' / 'DCMView.m').read_text(encoding='latin1')
    start = source.index('static short HorosImageIndexByAddingScroll')
    end = source.index('static NSInteger HorosMovieIndexForScroll', start)
    helper = source[start:end]
    assert 'trunc(change)' in helper
    # Ordinary 1×1 viewer, Scroll Wheel Reversed on, data not flipped: a
    # positive deltaY (wheel up, natural off) retreats. Trackpad precise
    # events keep deltaY; classic wheel replaces it with scrollingDeltaY.
    index, increment = probe.wheel_step(10, -2.5, precise=False, reversed=True,
                                        flipped=False)
    assert increment == 1 and index == 11
    index, increment = probe.wheel_step(10, -0.4, precise=True, reversed=True,
                                        flipped=False)
    assert increment == 1 and index == 11
    index, increment = probe.wheel_step(10, 8.0, precise=True, reversed=True,
                                        flipped=False)
    assert increment == -3 and index == 7


def test_sync_maps_by_slice_location_without_assuming_a_shared_cause():
    with tempfile.TemporaryDirectory(prefix='horos-scroll-sync-') as folder:
        dest = Path(folder)
        a = dest / 'a'
        b = dest / 'b'
        assert run([str(generate), str(a), '--modality', 'CT', '--slices', '4',
                    '--spacing', '0.5', '--name', 'sync-a',
                    '--frame-of-reference', 'shared']).returncode == 0
        assert run([str(generate), str(b), '--modality', 'CT', '--slices', '4',
                    '--spacing', '0.5', '--name', 'sync-b',
                    '--frame-of-reference', 'shared']).returncode == 0
        mapped = probe.sync_destination_index(a, b, source_index=2)
        assert mapped == 2
        assert probe.same_frame_of_reference(a, b) is True


def test_mpr_control_is_a_full_walk_of_the_same_volume():
    with tempfile.TemporaryDirectory(prefix='horos-scroll-mpr-') as folder:
        dest = Path(folder) / 'ct'
        assert run([str(generate), str(dest), '--modality', 'CT', '--slices', '5',
                    '--spacing', '0.5']).returncode == 0
        control = probe.measure_mpr_control(dest)
        assert control['visited_slices'] == 5
        assert control['omitted_slices'] == 0
        assert control['kind'] == 'sequential-index-walk'
        assert 'native-mpr2d-window' not in control['kind']


def test_required_catalog_ids_are_stable():
    catalog = json.loads((root / 'docs' / 'scroll-baseline-catalog.json').read_text())
    ids = {item['id'] for item in catalog['entries']}
    for required in ('S304-FIX-CT-100', 'S304-FIX-CT-500', 'S304-FIX-CT-1250',
                     'S304-FIX-MR-100', 'S304-FIX-MR-500', 'S304-FIX-MR-1250',
                     'S304-FIX-SYNC', 'S304-MET-EVENT-FRAME', 'S304-B283-IOACCEL',
                     'S304-CMD-GENERATE', 'S304-CMD-MEASURE', 'S304-ETAPA-B'):
        assert required in ids, required
    assert catalog['issue'] == 304
    assert catalog['reuse'] == '#367'
    assert catalog['etapa_b_owners'] == [373, 385]


test_plan_lists_required_catalog()
test_generator_writes_half_millimetre_axial_series()
test_measurer_visits_every_slice_and_reports_required_metrics()
test_measurer_refuses_to_drop_slices_for_a_prettier_number()
test_wheel_and_trackpad_use_the_host_index_formula()
test_sync_maps_by_slice_location_without_assuming_a_shared_cause()
test_mpr_control_is_a_full_walk_of_the_same_volume()
test_required_catalog_ids_are_stable()
print('PASS: scroll baseline fixtures, phases, sync, MPR control and catalog ids')
