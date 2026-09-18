#!/usr/bin/env python3
"""A/A and A/B of the shared-database server's parsing and transfer (Δ4 protocol, #614, #637).

Builds tools/probe-shared-database-server.m twice from the app's objects of one
configuration: once with BonjourPublisher.o recompiled at the baseline revision
with the app's own clang command, once with the candidate's. Every other object
is the same file in both. Each invocation starts one server, runs the workload
over loopback and stops it:

  setva_ms       200 SETVA requests, connect to close, one observation each
  strings_ms     50 DCMSE requests carrying 2000 relative paths
  fetch_ms_per_mib   20 DICOM fetches of 8 x 4 MiB files of DATABASE.noindex, by
                     name as the client asks for them, time per MiB received
  linked_fetch_ms_per_mib  20 DICOM fetches of 8 x 4 MiB files linked in place,
                     by absolute path (the probe's index lists them)
  upload_ms_per_mib  10 SENDD uploads of 4 x 8 MiB files, time per MiB sent

(HOROS_SDB_BENCH_COUNTS=60,10,5,5,5 reproduces the request counts of campaign 1 of
#614, whose fetches read absolute paths outside the database; since #637 the server
serves those only when the index links them.) The server
runs with its recorder quiet, so its own output does not weigh on the timings.

    python3 tools/measure-shared-database-server.py \
        --baseline efb2b0cef --candidate <sha> --configuration Debug \
        --out local-validation/delta4/614-Debug

Release objects come from `--objects-root` (a checkout built in Release).
"""
import argparse
import json
import os
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

# HorosDatabaseServer is the listener since #615; N2Connection and N2ConnectionListener the one before,
# so a baseline revision still links.
OBJECTS = ["BonjourPublisher", "N2Connection", "N2ConnectionListener", "N2Locker", "N2Debug", "NSException+N2",
           "SharedDatabaseAuthorization", "SharedDatabaseWire", "SharedDatabaseRequests", "HorosDatabaseServer"]
# Transfers are timed per MiB, not as throughput: for a throughput the p95 is the
# fastest 5 %, which guards nothing; for time per MiB it is the slow tail.
HIGHER = []
# Requests per invocation. Campaign 1 of #614 used 60/10/5/5, which left the
# fetch throughput and the p95 of SETVA and DCMSE unable to resolve 5-10 %.
SETVA_REQUESTS, DCMSE_REQUESTS, FETCH_REQUESTS, UPLOAD_REQUESTS, LINKED_REQUESTS = (
    int(value) for value in os.environ.get("HOROS_SDB_BENCH_COUNTS", "200,50,20,10,20").split(","))


def stock_files(work: Path, linked_folder: Path, count=8, size=4 << 20):
    """The same 4 MiB files in a server's DATABASE.noindex, by name, and linked in
    place outside it, listed in the probe's index."""
    folder = work / "DATABASE.noindex" / "10000"
    folder.mkdir(parents=True, exist_ok=True)
    linked_folder.mkdir(parents=True, exist_ok=True)
    names, linked = [], []
    for index in range(count):
        data = os.urandom(size)
        (folder / f"{index + 1}.dcm").write_bytes(data)
        names.append(f"{index + 1}.dcm")
        path = linked_folder / f"linked-{index}.dcm"
        if not path.exists():
            path.write_bytes(data)
        linked.append(str(path))
    (work / "index.json").write_text(json.dumps({"linked": linked}))
    return names, linked


def fetch_request(paths):
    return b"DICOM\0" + i32(len(paths)) + b"".join(text(p) for p in paths) + b"".join(text("dst.dcm") for _ in paths)


def i32(value):
    return struct.pack(">i", value)


def text(value):
    raw = value.encode() + b"\0"
    return i32(len(raw)) + raw


def client(probe: Path):
    work = Path(tempfile.mkdtemp(prefix="horos-sdb-bench-"))
    # A port found free can be taken before the server binds it: try another.
    for attempt in range(8):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        server = subprocess.Popen([str(probe), str(port), str(work)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL, env=dict(os.environ, HOROS_PROBE_QUIET="1"))
        ready = server.stdout.readline()
        if b'"ready"' in ready:
            break
        server.wait(timeout=5)
    else:
        raise SystemExit(f"the server could not listen: {ready!r}")
    try:

        def exchange(request):
            with socket.create_connection(("127.0.0.1", port), timeout=10) as s:
                s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                s.sendall(request)
                received = 0
                while chunk := s.recv(1 << 20):
                    received += len(chunk)
                return received

        # Drain recorder output so the server never blocks writing it.
        import threading
        threading.Thread(target=lambda: [None for _ in server.stdout], daemon=True).start()

        setva = b"SETVA\0" + text("x-coredata://bench/Study/p1") + text("benchmark value") + text("comment")
        for _ in range(5):
            exchange(setva)
        setva_ms = []
        for _ in range(SETVA_REQUESTS):
            t0 = time.perf_counter()
            exchange(setva)
            setva_ms.append((time.perf_counter() - t0) * 1000)

        paths = b"".join(text(f"{index}.dcm") for index in range(2000))
        dcmse = b"DCMSE\0" + text("PEER") + text("127.0.0.1") + text("11112") + text("1") + i32(2000) + paths
        strings_ms = []
        for _ in range(DCMSE_REQUESTS):
            t0 = time.perf_counter()
            exchange(dcmse)
            strings_ms.append((time.perf_counter() - t0) * 1000)

        names, linked = stock_files(work, work / "linked")
        fetch, linked_fetch = fetch_request(names), fetch_request(linked)
        fetch_ms_per_mib, linked_fetch_ms_per_mib = [], []
        for _ in range(FETCH_REQUESTS):
            t0 = time.perf_counter()
            received = exchange(fetch)
            fetch_ms_per_mib.append((time.perf_counter() - t0) * 1000 / (received / (1 << 20)))
        exchange(linked_fetch)
        for _ in range(LINKED_REQUESTS):
            t0 = time.perf_counter()
            received = exchange(linked_fetch)
            linked_fetch_ms_per_mib.append((time.perf_counter() - t0) * 1000 / (received / (1 << 20)))

        files = [os.urandom(8 << 20) for _ in range(4)]
        upload = b"SENDD\0" + i32(len(files)) + b"".join(i32(len(f)) + f for f in files)
        upload_ms_per_mib = []
        for _ in range(UPLOAD_REQUESTS):
            t0 = time.perf_counter()
            exchange(upload)
            upload_ms_per_mib.append((time.perf_counter() - t0) * 1000 / (len(upload) / (1 << 20)))
            shutil.rmtree(work / "uploads", ignore_errors=True)

        print(json.dumps({"setva_ms": setva_ms, "strings_ms": strings_ms, "fetch_ms_per_mib": fetch_ms_per_mib,
                          "linked_fetch_ms_per_mib": linked_fetch_ms_per_mib, "upload_ms_per_mib": upload_ms_per_mib}))
    finally:
        try:
            server.stdin.write(b"quit\n")
            server.stdin.flush()
        except BrokenPipeError:
            pass
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
        shutil.rmtree(work, ignore_errors=True)


def start_server(probe: Path, work: Path):
    """One probe server on a free loopback port; retried when the port is taken."""
    for attempt in range(8):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        server = subprocess.Popen([str(probe), str(port), str(work)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL, env=dict(os.environ, HOROS_PROBE_QUIET="1"))
        ready = server.stdout.readline()
        if b'"ready"' in ready:
            import threading
            threading.Thread(target=lambda: [None for _ in server.stdout], daemon=True).start()
            return server, port
        server.wait(timeout=5)
    raise SystemExit(f"the server could not listen: {ready!r}")


def stop_server(server):
    try:
        server.stdin.write(b"quit\n")
        server.stdin.flush()
    except BrokenPipeError:
        pass
    try:
        server.wait(timeout=5)
    except subprocess.TimeoutExpired:
        server.kill()


def interleaved_client(probe_a: Path, probe_b: Path):
    """Both servers up at once; every request alternates between them (ABBA).

    A scheduling burst then lands on both variants instead of on whichever
    process happened to be running, which is what kept the p95 of the
    sequential design from resolving 10 %.
    """
    works = [Path(tempfile.mkdtemp(prefix="horos-sdb-bench-a-")), Path(tempfile.mkdtemp(prefix="horos-sdb-bench-b-"))]
    servers = []
    try:
        for probe, work in zip((probe_a, probe_b), works):
            servers.append(start_server(probe, work))
        first = os.environ.get("HOROS_AB_FIRST", "A")
        start = 1 if first == "B" else 0
        ports = [port for _, port in servers]

        def exchange(port, request):
            with socket.create_connection(("127.0.0.1", port), timeout=10) as s:
                s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                s.sendall(request)
                received = 0
                while chunk := s.recv(1 << 20):
                    received += len(chunk)
                return received

        results = [{"setva_ms": [], "strings_ms": [], "fetch_ms_per_mib": [], "linked_fetch_ms_per_mib": [],
                    "upload_ms_per_mib": []} for _ in range(2)]

        def pairs(count, action):
            for index in range(count):
                for slot in range(2):
                    variant = start if (index % 2 == 0) == (slot == 0) else 1 - start
                    action(variant)

        setva = b"SETVA\0" + text("x-coredata://bench/Study/p1") + text("benchmark value") + text("comment")
        for port in ports:
            for _ in range(5):
                exchange(port, setva)

        def one_setva(v):
            t0 = time.perf_counter()
            exchange(ports[v], setva)
            results[v]["setva_ms"].append((time.perf_counter() - t0) * 1000)
        pairs(SETVA_REQUESTS, one_setva)

        paths = b"".join(text(f"{index}.dcm") for index in range(2000))
        dcmse = b"DCMSE\0" + text("PEER") + text("127.0.0.1") + text("11112") + text("1") + i32(2000) + paths

        def one_dcmse(v):
            t0 = time.perf_counter()
            exchange(ports[v], dcmse)
            results[v]["strings_ms"].append((time.perf_counter() - t0) * 1000)
        pairs(DCMSE_REQUESTS, one_dcmse)

        # Both servers read the same linked files; each has its own DATABASE.noindex.
        for work in works:
            names, linked = stock_files(work, works[0] / "linked")
        fetch, linked_fetch = fetch_request(names), fetch_request(linked)

        def one_fetch(v):
            t0 = time.perf_counter()
            received = exchange(ports[v], fetch)
            results[v]["fetch_ms_per_mib"].append((time.perf_counter() - t0) * 1000 / (received / (1 << 20)))
        pairs(FETCH_REQUESTS, one_fetch)

        for port in ports:
            exchange(port, linked_fetch)

        def one_linked_fetch(v):
            t0 = time.perf_counter()
            received = exchange(ports[v], linked_fetch)
            results[v]["linked_fetch_ms_per_mib"].append((time.perf_counter() - t0) * 1000 / (received / (1 << 20)))
        pairs(LINKED_REQUESTS, one_linked_fetch)

        files = [os.urandom(8 << 20) for _ in range(4)]
        upload = b"SENDD\0" + i32(len(files)) + b"".join(i32(len(f)) + f for f in files)

        def one_upload(v):
            t0 = time.perf_counter()
            exchange(ports[v], upload)
            results[v]["upload_ms_per_mib"].append((time.perf_counter() - t0) * 1000 / (len(upload) / (1 << 20)))
            shutil.rmtree(works[v] / "uploads", ignore_errors=True)
        pairs(UPLOAD_REQUESTS, one_upload)

        print(json.dumps({"A": results[0], "B": results[1]}))
    finally:
        for server, _ in servers:
            stop_server(server)
        for work in works:
            shutil.rmtree(work, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--client", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--interleaved-client", type=Path, nargs=2, help=argparse.SUPPRESS)
    parser.add_argument("--interleave", action="store_true",
                        help="run both servers at once and alternate every request between them")
    parser.add_argument("--baseline")
    parser.add_argument("--candidate", default="WORKTREE")
    parser.add_argument("--configuration", default="Debug", choices=("Debug", "Release"))
    parser.add_argument("--objects-root", type=Path, default=ROOT)
    parser.add_argument("--build-root", type=Path, help="checkout whose build log holds the compile command")
    parser.add_argument("--build-log", type=Path)
    parser.add_argument("--rounds", type=int, default=30)
    parser.add_argument("--limit", action="append", default=[])
    parser.add_argument("--out", type=Path)
    arguments = parser.parse_args()
    if arguments.client:
        return client(arguments.client)
    if arguments.interleaved_client:
        return interleaved_client(*arguments.interleaved_client)

    import ab_protocol
    import object_probe
    out = arguments.out
    out.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="horos-sdb-measure-"))
    objects = []
    for name in OBJECTS:
        obj = object_probe.app_object(name, arguments.configuration, arguments.objects_root.resolve())
        if obj is None:
            raise SystemExit(f"needs {name}.o built in {arguments.configuration} under {arguments.objects_root}")
        objects.append(obj)
    command = object_probe.compile_command("Horos/Sources/BonjourPublisher.m", arguments.configuration,
                                           root=(arguments.build_root or arguments.objects_root).resolve(),
                                           log=arguments.build_log)
    sdk = subprocess.run(["xcrun", "--show-sdk-path"], capture_output=True, text=True, check=True).stdout.strip()
    probes = {}
    for label, revision in (("baseline", arguments.baseline), ("candidate", arguments.candidate)):
        source = work / label / "BonjourPublisher.m"
        if revision == "WORKTREE":
            source.parent.mkdir(parents=True)
            shutil.copyfile(ROOT / "Horos/Sources/BonjourPublisher.m", source)
            shutil.copyfile(ROOT / "Horos/Sources/BonjourPublisher.h", source.parent / "BonjourPublisher.h")
        else:
            object_probe.revision_source("Horos/Sources/BonjourPublisher.m", revision, source)
            object_probe.revision_source("Horos/Sources/BonjourPublisher.h", revision, source.parent / "BonjourPublisher.h")
        obj = work / label / "BonjourPublisher.o"
        # The revision's own header first: its listener ivar changed type in #615.
        object_probe.compile_source(command[:1] + ["-iquote", str(source.parent)] + command[1:], source, obj)
        probe = work / f"probe-{label}"
        subprocess.run(["xcrun", "clang", "-fno-objc-arc", "-O2", "-g0", "-mmacosx-version-min=26.0",
                        str(ROOT / "tools/probe-shared-database-server.m"), str(obj)] + [str(o) for o in objects[1:]] +
                       ["-framework", "Cocoa", "-framework", "CoreData", "-framework", "Network", "-lc++", f"-L{sdk}/usr/lib/swift",
                        "-L/usr/lib/swift", "-Wl,-rpath,/usr/lib/swift", "-Wl,-undefined,dynamic_lookup", "-o", str(probe)],
                       check=True, capture_output=True)
        probes[label] = probe

    def argv(label):
        return [sys.executable, str(Path(__file__).resolve()), "--client", str(probes[label])]

    def joint(first, second):
        return [sys.executable, str(Path(__file__).resolve()), "--interleaved-client", str(probes[first]), str(probes[second])]

    plan = {"baseline_revision": arguments.baseline, "candidate_revision": arguments.candidate,
            "configuration": arguments.configuration, "objects_root": str(arguments.objects_root.resolve()),
            "compile_command": command, "rounds": arguments.rounds, "limits": arguments.limit,
            "protocol_version": ab_protocol.PROTOCOL_VERSION, "higher_is_better": HIGHER,
            "requests": [SETVA_REQUESTS, DCMSE_REQUESTS, FETCH_REQUESTS, UPLOAD_REQUESTS, LINKED_REQUESTS],
            "design": "interleaved: both servers at once, ABBA per request" if arguments.interleave
            else "sequential processes"}
    (out / "plan.json").write_text(json.dumps(plan, indent=1) + "\n")
    limits = ab_protocol._parse_limits(arguments.limit)
    if arguments.interleave:
        aa = ab_protocol.run_joint(joint("baseline", "baseline"), ["A", "B"], arguments.rounds, 1)
    else:
        aa = ab_protocol.run_protocol({"A": argv("baseline"), "A'": argv("baseline")}, arguments.rounds, 1)
    (out / "aa.json").write_text(json.dumps(aa) + "\n")
    tolerance = ab_protocol.calibrate(aa, limits, set(HIGHER), ab_protocol.DEFAULT_SEED, ab_protocol.DEFAULT_RESAMPLES)
    (out / "tolerance.json").write_text(json.dumps(tolerance, indent=1) + "\n")
    for key, value in tolerance["tolerances"].items():
        print(f"A/A {key}: tolerance {value['tolerance']:.4g} (limit {value['relevance_limit']}) "
              f"{'capable' if value['capable'] else 'INCAPABLE'}")
    if arguments.interleave:
        ab = ab_protocol.run_joint(joint("baseline", "candidate"), ["A", "B"], arguments.rounds, 1)
        ab["variants"] = {"A": {"revision": arguments.baseline}, "B": {"revision": arguments.candidate}}
    else:
        ab = ab_protocol.run_protocol({"baseline": argv("baseline"), "candidate": argv("candidate")}, arguments.rounds, 1)
    (out / "ab.json").write_text(json.dumps(ab) + "\n")
    analysis = ab_protocol.analyze(ab, tolerance, set(HIGHER), ab_protocol.DEFAULT_SEED, ab_protocol.DEFAULT_RESAMPLES)
    (out / "analysis.json").write_text(json.dumps(analysis, indent=1) + "\n")
    names = ("A", "B") if arguments.interleave else ("baseline", "candidate")
    table = ab_protocol.markdown(analysis, names).replace("| A | B |", "| baseline | candidate |", 1)
    (out / "table.md").write_text(table)
    print(table)
    shutil.rmtree(work, ignore_errors=True)
    return 0 if analysis["overall"] == "non-inferior" else 1


if __name__ == "__main__":
    raise SystemExit(main())
