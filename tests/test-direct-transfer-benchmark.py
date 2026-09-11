#!/usr/bin/env python3
"""Same synthetic instances over HOROSFT and DIMSE C-STORE; record arm64 cost."""
from __future__ import annotations

import json
import os
import platform
import resource
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

root = Path(__file__).resolve().parents[1]
SKIP = 2


def fail(message):
    print('FAIL:', message, file=sys.stderr)
    raise SystemExit(1)


def find_dcmtk_bin():
    env = os.environ.get('DCMTK_BIN')
    candidates = []
    if env:
        candidates.append(Path(env))
    for base in (root, root.parent / 'horos-workbench'):
        candidates.append(base / 'build/Build/Intermediates.noindex/Horos.build/Debug/DCMTK.build/Install/bin')
        candidates.append(base / 'build/Build/Intermediates.noindex/Horos.build/Debug/DCMTK.build/CMake/bin')
    for directory in candidates:
        if (directory / 'storescu').is_file() and (directory / 'storescp').is_file():
            return directory
    return None


def even(data, pad=b'\x00'):
    return data if len(data) % 2 == 0 else data + pad


def ui(value):
    return even(value.encode('ascii'), b'\x00')


def lo(value):
    return even(value.encode('ascii'), b' ')


def element(group, elem, vr, value):
    tag = group.to_bytes(2, 'little') + elem.to_bytes(2, 'little')
    if vr in ('OB', 'OW', 'OF', 'UN', 'UT'):
        body = even(value)
        return tag + vr.encode('ascii') + b'\x00\x00' + len(body).to_bytes(4, 'little') + body
    body = value if isinstance(value, (bytes, bytearray)) else value.encode('ascii')
    if vr == 'UI':
        body = even(body, b'\x00')
    else:
        body = even(body, b' ')
    return tag + vr.encode('ascii') + len(body).to_bytes(2, 'little') + body


def write_secondary_capture(path, sop, study, series, pixels, rows, columns):
    file_meta = b''.join([
        element(0x0002, 0x0001, 'OB', b'\x00\x01'),
        element(0x0002, 0x0002, 'UI', ui('1.2.840.10008.5.1.4.1.1.7')),
        element(0x0002, 0x0003, 'UI', ui(sop)),
        element(0x0002, 0x0010, 'UI', ui('1.2.840.10008.1.2.1')),
        element(0x0002, 0x0012, 'UI', ui('1.2.826.0.1.3680043.8.498.379')),
        element(0x0002, 0x0013, 'SH', lo('HOROS379')),
    ])
    file_meta = element(0x0002, 0x0000, 'UL', len(file_meta).to_bytes(4, 'little')) + file_meta
    dataset = b''.join([
        element(0x0008, 0x0016, 'UI', ui('1.2.840.10008.5.1.4.1.1.7')),
        element(0x0008, 0x0018, 'UI', ui(sop)),
        element(0x0008, 0x0060, 'CS', lo('OT')),
        element(0x0010, 0x0010, 'PN', lo('ANON^BENCHMARK')),
        element(0x0010, 0x0020, 'LO', lo('BENCH379')),
        element(0x0020, 0x000D, 'UI', ui(study)),
        element(0x0020, 0x000E, 'UI', ui(series)),
        element(0x0020, 0x0013, 'IS', lo(sop.rsplit('.', 1)[-1])),
        element(0x0028, 0x0002, 'US', (1).to_bytes(2, 'little')),
        element(0x0028, 0x0004, 'CS', lo('MONOCHROME2')),
        element(0x0028, 0x0010, 'US', rows.to_bytes(2, 'little')),
        element(0x0028, 0x0011, 'US', columns.to_bytes(2, 'little')),
        element(0x0028, 0x0100, 'US', (8).to_bytes(2, 'little')),
        element(0x0028, 0x0101, 'US', (8).to_bytes(2, 'little')),
        element(0x0028, 0x0102, 'US', (7).to_bytes(2, 'little')),
        element(0x0028, 0x0103, 'US', (0).to_bytes(2, 'little')),
        element(0x7FE0, 0x0010, 'OB', pixels),
    ])
    path.write_bytes(b'\x00' * 128 + b'DICM' + file_meta + dataset)


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def parse_time_l(stderr):
    user = sys_time = rss = None
    for line in stderr.splitlines():
        if ' real ' in line and ' user ' in line and ' sys' in line:
            parts = line.split()
            user = float(parts[2])
            sys_time = float(parts[4])
        if 'maximum resident set size' in line:
            rss = int(line.split()[0])
    if user is None or rss is None:
        fail('could not parse /usr/bin/time -l:\n' + stderr)
    return user + sys_time, rss


def measure_command(command, cwd=None):
    before = resource.getrusage(resource.RUSAGE_CHILDREN)
    started = time.perf_counter()
    result = subprocess.run(['/usr/bin/time', '-l', *command], cwd=cwd,
                            capture_output=True, text=True)
    elapsed = time.perf_counter() - started
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    _, rss = parse_time_l(result.stderr)
    cpu = (after.ru_utime + after.ru_stime) - (before.ru_utime + before.ru_stime)
    inner = subprocess.CompletedProcess(
        command, result.returncode, result.stdout, result.stderr)
    return inner, {
        'latency_s': elapsed,
        'cpu_s': cpu,
        'max_rss_bytes': rss,
    }


def wait_port(host, port, timeout=5):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.05)
    fail(f'nothing listened on {host}:{port}')


def compile_horosft(tmpdir):
    source = tmpdir / 'main.swift'
    source.write_text(r'''import Foundation

let arguments = CommandLine.arguments
let token = arguments[1]
let incoming = URL(fileURLWithPath: arguments[2], isDirectory: true)
let files = Array(arguments.dropFirst(3))
do {
    let listener = DirectTransferListener(token: token)
    try listener.start(interface: .loopbackIPv4)
    defer { listener.stop() }
    let sent = try DirectTransferClient.send(
        files: files,
        host: "127.0.0.1",
        port: Int(listener.port),
        token: token,
        expectedUIDs: files.map { (URL(fileURLWithPath: $0).lastPathComponent as NSString).deletingPathExtension },
        cancelled: false
    )
    precondition(sent.outcome == DirectTransferPolicy.outcomeSuccess, sent.outcome)
    _ = try listener.takeReceivedFiles(into: incoming)
    print("HOROSFT_OK \(listener.port)")
} catch {
    fputs("HOROSFT failed: \(error)\n", stderr)
    exit(1)
}
''')
    binary = tmpdir / 'horosft-send'
    compiled = subprocess.run([
        'xcrun', 'swiftc',
        str(root / 'Horos/Sources/HorosDirectTransfer.swift'),
        str(source), '-o', str(binary),
    ], capture_output=True, text=True)
    if compiled.returncode != 0:
        fail('swiftc failed:\n' + compiled.stderr)
    return binary


def main():
    if platform.machine() != 'arm64':
        print('skipped: Intel is out of scope; this measurement is arm64-only', file=sys.stderr)
        raise SystemExit(SKIP)
    dcmtk = find_dcmtk_bin()
    if dcmtk is None:
        print('skipped: needs the already-built DCMTK storescu/storescp: STORESCU', file=sys.stderr)
        raise SystemExit(SKIP)

    storescu = dcmtk / 'storescu'
    storescp = dcmtk / 'storescp'
    arch = subprocess.check_output(['lipo', '-archs', str(storescu)], text=True).strip()
    if arch != 'arm64':
        fail(f'storescu is {arch}, not arm64')

    rows = columns = 256
    count = 16
    pixels_each = rows * columns
    study = '1.2.826.0.1.3680043.8.498.379.1'
    series = '1.2.826.0.1.3680043.8.498.379.2'

    with tempfile.TemporaryDirectory(prefix='horos-379-bench-') as tmp:
        tmpdir = Path(tmp)
        send_dir = tmpdir / 'send'
        horos_recv = tmpdir / 'horosft-recv'
        dimse_recv = tmpdir / 'dimse-recv'
        send_dir.mkdir()
        horos_recv.mkdir()
        dimse_recv.mkdir()
        files = []
        total_bytes = 0
        for index in range(1, count + 1):
            sop = f'1.2.826.0.1.3680043.8.498.379.3.{index}'
            path = send_dir / f'{sop}.dcm'
            pixels = bytes((index * 17 + n) % 256 for n in range(pixels_each))
            write_secondary_capture(path, sop, study, series, pixels, rows, columns)
            files.append(path)
            total_bytes += path.stat().st_size

        binary = compile_horosft(tmpdir)
        horos_run, horos_res = measure_command(
            [str(binary), 'bench-token', str(horos_recv), *[str(path) for path in files]]
        )
        if horos_run.returncode != 0:
            fail('HOROSFT send failed:\n' + horos_run.stderr + horos_run.stdout)
        received_horos = sorted(p.name for p in horos_recv.iterdir() if p.suffix == '.dcm')
        if received_horos != sorted(p.name for p in files):
            fail(f'HOROSFT inventory {received_horos}')

        port = free_port()
        scp = subprocess.Popen(
            [str(storescp), '+xa', '-aet', 'STORESCP', '-od', str(dimse_recv), str(port)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        try:
            wait_port('127.0.0.1', port)
            dimse_run, dimse_res = measure_command(
                [str(storescu), '-aet', 'STORESCU', '-aec', 'STORESCP',
                 '127.0.0.1', str(port), *[str(path) for path in files]]
            )
        finally:
            scp.terminate()
            try:
                scp.wait(timeout=3)
            except subprocess.TimeoutExpired:
                scp.kill()
                scp.wait(timeout=1)
        if dimse_run.returncode != 0:
            fail('DIMSE C-STORE failed:\n' + dimse_run.stderr + dimse_run.stdout)
        received_dimse = [p for p in dimse_recv.rglob('*') if p.is_file()]
        if len(received_dimse) < count:
            fail(f'DIMSE received {len(received_dimse)} files, expected {count}')

    def pack(name, metrics):
        latency = metrics['latency_s']
        return {
            'transport': name,
            'latency_s': round(latency, 6),
            'throughput_mib_s': round((total_bytes / (1024 * 1024)) / latency, 4) if latency > 0 else 0,
            'cpu_s': round(metrics['cpu_s'], 6),
            'max_rss_bytes': int(metrics['max_rss_bytes']),
        }

    report = {
        'issue': 379,
        'architecture': 'arm64',
        'host': platform.machine(),
        'os': f'{platform.system()} {platform.release()} {platform.mac_ver()[0]}',
        'storescu': subprocess.check_output([str(storescu), '--version'], text=True).splitlines()[0],
        'file_count': count,
        'bytes': total_bytes,
        'inputs': 'synthetic Secondary Capture, no PHI, generated at runtime',
        'horosft': pack('HOROSFT1', horos_res),
        'dimse': pack('DIMSE C-STORE', dimse_res),
        'note': 'Same files, loopback IPv4. Gain is not assumed.',
    }
    for side in (report['horosft'], report['dimse']):
        if side['latency_s'] <= 0 or side['cpu_s'] < 0 or side['max_rss_bytes'] <= 0:
            fail(f'missing resource sample for {side["transport"]}: {side}')
        if side['throughput_mib_s'] <= 0:
            fail(f'throughput was not computed for {side["transport"]}')

    print(json.dumps(report, indent=2))
    doc = (root / 'docs/direct-transfer-benchmark.md').read_text(encoding='utf-8')
    for token in ('arm64', 'HOROSFT', 'C-STORE', 'Throughput', 'Latency', 'CPU', 'RSS'):
        if token not in doc:
            fail(f'benchmark document is missing {token}')
    recorded = json.loads((root / 'docs/direct-transfer-benchmark.json').read_text(encoding='utf-8'))
    if recorded.get('architecture') != 'arm64':
        fail('recorded benchmark is not arm64')
    for side in ('horosft', 'dimse'):
        sample = recorded[side]
        if not all(key in sample for key in ('latency_s', 'throughput_mib_s', 'cpu_s', 'max_rss_bytes')):
            fail(f'recorded {side} is missing a resource field')
    print('PASS: arm64 HOROSFT and DIMSE C-STORE measured on the same synthetic inputs')
    return report


if __name__ == '__main__':
    main()
