#!/usr/bin/env python3
"""The shared-database server parses what it receives within the bytes it has (#614).

Runs the application's own server - O2DatabaseConnection over HorosDatabaseServer
(#615), or over N2ConnectionListener at a revision before it, linked from the
app's objects by tools/probe-shared-database-server.m, with the database replaced
by a recorder - and talks to it over loopback:

  * valid SETVA, ADDAL, REMAL, SENDD, DICOM, DCMSE and MFILE requests, SETVA split
    at every byte and the others at every boundary that matters, each mutating
    exactly once;
  * nil and "" kept apart (length 0 against a lone terminator);
  * negative and oversized lengths and counts, strings without a terminator,
    with an embedded one or not UTF-8, missing required strings and an unknown
    command: each closes the connection at once, mutates nothing, and the
    server still answers the next request;
  * a request cut off by the client releases its worker (its connection thread
    before #615);
  * with a password: sensitive commands refused without it or with a wrong
    one, accepted with it, fragmented or not;
  * what a request may reach (#637): DICOM, DCMSE and MFILE serve an image of
    DATABASE.noindex by its name or path, an older client's ROI and a file the
    index links an image to - looked up once, not per request - and close
    without answering anything for a path outside the database, with `..`, or of
    another shape, even after valid ones; SETVA writes only the keys the client
    sets, typed, and clearing reportURL deletes only a report of the database;
    DBSIZ answers an index of 4 GiB or more with the value that says so.

    python3 tests/test-shared-database-parser.py                 # the built objects
    python3 tests/test-shared-database-parser.py --revision REV  # BonjourPublisher.m at REV

The second form recompiles BonjourPublisher.m as it was at REV with the app's
flags; against the revision before #614, and before #637, it must fail.
"""
import argparse
import json
import os
import queue
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import object_probe  # noqa: E402

parser = argparse.ArgumentParser()
parser.add_argument("--revision")
parser.add_argument("--configuration", default="Debug")
arguments = parser.parse_args()

OBJECTS = ["BonjourPublisher", "N2Connection", "N2ConnectionListener", "N2Locker", "N2Debug", "NSException+N2",
           "SharedDatabaseAuthorization", "SharedDatabaseWire", "SharedDatabaseRequests", "HorosDatabaseServer"]
work = Path(tempfile.mkdtemp(prefix="horos-sdb-parser-"))
objects = []
for name in OBJECTS:
    obj = object_probe.app_object(name, arguments.configuration)
    if obj is None:
        print(f"needs a built {name}.o ({arguments.configuration})", file=sys.stderr)
        raise SystemExit(2)
    objects.append(obj)
if arguments.revision:
    command = object_probe.compile_command("Horos/Sources/BonjourPublisher.m", arguments.configuration)
    source = object_probe.revision_source("Horos/Sources/BonjourPublisher.m", arguments.revision,
                                          work / "BonjourPublisher.m")
    # The revision's own header first: the listener ivar changed type in #615.
    object_probe.revision_source("Horos/Sources/BonjourPublisher.h", arguments.revision, work / "BonjourPublisher.h")
    objects[0] = work / "BonjourPublisher.o"
    object_probe.compile_source(command[:1] + ["-iquote", str(work)] + command[1:], source, objects[0])

sdk = subprocess.run(["xcrun", "--show-sdk-path"], capture_output=True, text=True, check=True).stdout.strip()
probe = work / "probe"
subprocess.run(["xcrun", "clang", "-fno-objc-arc", "-O1", "-g0", "-mmacosx-version-min=26.0",
                str(ROOT / "tools/probe-shared-database-server.m")] + [str(o) for o in objects] +
               ["-framework", "Cocoa", "-framework", "CoreData", "-framework", "Network", "-lc++", f"-L{sdk}/usr/lib/swift", "-L/usr/lib/swift",
                "-Wl,-rpath,/usr/lib/swift", "-Wl,-undefined,dynamic_lookup", "-o", str(probe)],
               check=True, capture_output=True)
print(f"server under test: {objects[0]}")


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Server:
    def __init__(self, password=None):
        self.scratch = work / f"scratch-{'protected' if password else 'open'}"
        self.scratch.mkdir(exist_ok=True)
        self.port = free_port()
        env = dict(os.environ)
        env.pop("HOROS_PROBE_PASSWORD", None)
        if password:
            env["HOROS_PROBE_PASSWORD"] = password
        self.process = subprocess.Popen([str(probe), str(self.port), str(self.scratch)], stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=open(work / "server.log", "ab"), env=env)
        self.events = queue.Queue()
        threading.Thread(target=self._read, daemon=True).start()
        ready = self.next_event(10)
        assert ready and ready["event"] == "ready", ready

    def _read(self):
        for line in self.process.stdout:
            try:
                self.events.put(json.loads(line))
            except json.JSONDecodeError:
                pass

    def next_event(self, timeout):
        try:
            return self.events.get(timeout=timeout)
        except queue.Empty:
            return None

    def drain(self, settle=0.25):
        time.sleep(settle)
        found = []
        while True:
            try:
                found.append(self.events.get_nowait())
            except queue.Empty:
                return found

    def threads(self):
        self.drain(0)
        self.process.stdin.write(b"threads\n")
        self.process.stdin.flush()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            event = self.next_event(1)
            if event and event["event"] == "threads":
                return event["count"]
        return None

    def stop(self):
        try:
            self.process.stdin.write(b"quit\n")
            self.process.stdin.flush()
        except BrokenPipeError:
            pass
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()

    def alive(self):
        return self.process.poll() is None

    def exchange(self, chunks, delay=0.0, timeout=3.0, close_after_send=False):
        """Send chunks; return (response, closed by the server within timeout)."""
        if not self.alive():
            return b"", False
        try:
            return self._exchange(chunks, delay, timeout, close_after_send)
        except (ConnectionRefusedError, BrokenPipeError):
            return b"", False

    def _exchange(self, chunks, delay, timeout, close_after_send):
        with socket.create_connection(("127.0.0.1", self.port), timeout=5) as s:
            s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            for chunk in chunks:
                if chunk:
                    s.sendall(chunk)
                if delay:
                    time.sleep(delay)
            if close_after_send:
                return b"", True
            s.settimeout(timeout)
            response = bytearray()
            try:
                while True:
                    data = s.recv(1 << 20)
                    if not data:
                        return bytes(response), True
                    response.extend(data)
            except socket.timeout:
                return bytes(response), False
            except ConnectionResetError:
                return bytes(response), True


def i32(value):
    return struct.pack(">i", value)


def text(value):
    data = value.encode() + b"\0"
    return i32(len(data)) + data


NULL = i32(0)
failures = []


def check(condition, message):
    if not condition:
        failures.append(message)
        print("FAIL:", message)


def splits(data, positions):
    positions = sorted({p for p in positions if 0 < p < len(data)})
    pieces, last = [], 0
    for p in positions:
        pieces.append(data[last:p])
        last = p
    pieces.append(data[last:])
    return pieces


def mutations(events):
    return [e for e in events if e["event"] in ("setValue", "relationAdd", "relationRemove", "addFiles",
                                                "sendDICOMFiles", "archiveAnnotations")]


open_server = Server()
try:
    # Public commands still answer.
    response, closed = open_server.exchange([b"AUTHV\0"])
    check(response == i32(1) and closed, f"AUTHV answered {response!r}")
    response, closed = open_server.exchange([b"ISPWD\0"])
    check(response == i32(0) and closed, f"ISPWD answered {response!r}")
    open_server.drain()

    # SETVA split at every byte mutates exactly once, with the right values.
    setva = b"SETVA\0" + text("x-coredata://probe/Study/p1") + text("ré value") + text("comment")
    for cut in range(1, len(setva)):
        response, closed = open_server.exchange([setva[:cut], setva[cut:]], delay=0.02)
        events = mutations(open_server.drain(0.05))
        ok = closed and events == [{"event": "setValue", "object": "x-coredata://probe/Study/p1",
                                    "key": "comment", "value": "ré value"}]
        if not ok:
            check(False, f"SETVA split at {cut}: closed={closed} events={events}")
            break
    else:
        check(True, "")
    # Byte by byte, every boundary at once.
    response, closed = open_server.exchange([setva[i:i + 1] for i in range(len(setva))], delay=0.01)
    events = mutations(open_server.drain())
    check(closed and len(events) == 1 and events[0]["value"] == "ré value", f"SETVA byte by byte: {events}")

    # nil and "" stay apart.
    for label, value, expected in [("null", NULL, None), ("empty", text(""), "")]:
        request = b"SETVA\0" + text("x-coredata://probe/Study/p2") + value + text("comment")
        response, closed = open_server.exchange(splits(request, [10, 36, 40]), delay=0.02)
        events = mutations(open_server.drain())
        check(closed and events == [{"event": "setValue", "object": "x-coredata://probe/Study/p2",
                                     "key": "comment", "value": expected}],
              f"SETVA {label} value: closed={closed} events={events}")

    # ADDAL / REMAL: album parameters as the client sends them.
    plist = '{ albumStudies = ( "x-coredata://probe/Study/s1", "x-coredata://probe/Study/s2" ); albumUID = "x-coredata://probe/Album/a1"; }'
    for command, kind in (("ADDAL", "relationAdd"), ("REMAL", "relationRemove")):
        request = command.encode() + b"\0" + text(plist)
        response, closed = open_server.exchange(splits(request, [3, 8, 9, 50, len(request) - 1]), delay=0.02)
        events = mutations(open_server.drain())
        relations = [e for e in events if e["event"] == kind]
        check(closed and [r["object"] for r in relations] == ["x-coredata://probe/Study/s1", "x-coredata://probe/Study/s2"],
              f"{command}: closed={closed} events={events}")

    # SENDD: three files, split inside the count, a size, the data and between files.
    files = [os.urandom(1024), os.urandom(70_000), os.urandom(300_000)]
    request = b"SENDD\0" + i32(len(files)) + b"".join(i32(len(f)) + f for f in files)
    first = 6 + 4 + 4
    cuts = [2, 8, 12, first - 2, first + 512, first + 1024 + 2, first + 1024 + 4 + 35_000, len(request) - 1]
    response, closed = open_server.exchange(splits(request, cuts), delay=0.03)
    events = mutations(open_server.drain(0.5))
    added = [e for e in events if e["event"] == "addFiles"]
    check(closed and len(added) == 1 and added[0]["sizes"] == [len(f) for f in files] and not added[0]["generatedByOsiriX"],
          f"SENDD: closed={closed} events={events}")
    check(len(response) == 4 + 4 * len(files) and struct.unpack(">I", response[:4])[0] == len(files),
          f"SENDD response {response[:8]!r}… ({len(response)} bytes)")
    if added:
        uploaded = [Path(p).read_bytes() for p in added[0]["paths"]]
        check(uploaded == files, "SENDD: uploaded bytes differ")

    # DICOM: fetch two files of the database by absolute path.
    data_folder = open_server.scratch / "DATABASE.noindex" / "10000"
    data_folder.mkdir(parents=True, exist_ok=True)
    stored = []
    for index in range(2):
        path = data_folder / f"stored é {index}.dcm"
        path.write_bytes(os.urandom(5000 + index))
        stored.append(path)
    request = b"DICOM\0" + i32(2) + b"".join(text(str(p)) for p in stored) + text("dst/one.dcm") + text("dst/two.dcm")
    response, closed = open_server.exchange(splits(request, [7, 11, 20, 60, len(request) - 3]), delay=0.02)
    expected = i32(2)
    for path, destination in zip(stored, ("dst/one.dcm", "dst/two.dcm")):
        data = path.read_bytes()
        expected += i32(len(data)) + data + i32(len(destination) + 1) + destination.encode() + b"\0"
    check(closed and response == expected, f"DICOM response differs ({len(response)} of {len(expected)} bytes)")
    check(not mutations(open_server.drain()), "DICOM mutated something")
    # Bytes after a complete request are not part of it: the answer is intact.
    response, closed = open_server.exchange([request + os.urandom(256_000)], timeout=5)
    check(closed and response == expected, f"DICOM with trailing bytes: {len(response)} of {len(expected)} bytes")

    # DCMSE: a send order is queued once.
    request = b"DCMSE\0" + text("PEER") + text("10.0.0.9") + text("11112") + text("1") + i32(2) + text(str(stored[0])) + text(str(stored[1]))
    response, closed = open_server.exchange(splits(request, [4, 15, 30, len(request) - 2]), delay=0.02)
    events = mutations(open_server.drain(0.5))
    sends = [e for e in events if e["event"] == "sendDICOMFiles"]
    check(closed and len(sends) == 1 and sends[0]["todo"]["Files"] == [str(p) for p in stored]
          and sends[0]["todo"]["AETitle"] == "PEER", f"DCMSE: closed={closed} events={events}")

    # MFILE answers with the modification date.
    response, closed = open_server.exchange([b"MFILE\0" + text(str(stored[0]))])
    check(closed and len(response) > 0, f"MFILE answered {len(response)} bytes")

    # What a request may reach (#637).
    (data_folder / "7.dcm").write_bytes(os.urandom(3000))
    rois = open_server.scratch / "ROIs"
    rois.mkdir(exist_ok=True)
    (rois / "roi é.dcm").write_bytes(os.urandom(700))
    elsewhere = work / "linked é"
    elsewhere.mkdir(exist_ok=True)
    linked = elsewhere / "linked.dcm"
    linked.write_bytes(os.urandom(2500))
    secret = work / "secret.txt"
    secret.write_bytes(b"not a file of the database")
    reports = open_server.scratch / "REPORTS"
    reports.mkdir(exist_ok=True)
    report_inside, report_outside = reports / "report é.odt", work / "report outside.odt"
    report_inside.write_bytes(b"report")
    report_outside.write_bytes(b"not one of the database's reports")
    (open_server.scratch / "index.json").write_text(json.dumps({
        "linked": [str(linked)],
        "values": {"x-coredata://probe/Study/r1": {"reportURL": str(report_inside)},
                   "x-coredata://probe/Study/r2": {"reportURL": str(report_outside)}}}))
    os.utime(open_server.scratch / "Database.sql")

    def fetch(paths):
        return b"DICOM\0" + i32(len(paths)) + b"".join(text(p) for p in paths) + b"".join(text(f"dst/{i}.dcm") for i in range(len(paths)))

    def fetched(files):
        reply = i32(len(files))
        for index, file in enumerate(files):
            data = file.read_bytes()
            destination = f"dst/{index}.dcm"
            reply += i32(len(data)) + data + i32(len(destination) + 1) + destination.encode() + b"\0"
        return reply

    open_server.drain()
    request = fetch(["7.dcm", "ROIs/roi é.dcm", str(linked)])
    response, closed = open_server.exchange(splits(request, [9, 20, len(request) - 4]), delay=0.02)
    lookups = [e for e in open_server.drain() if e["event"] == "fetch"]
    check(closed and response == fetched([data_folder / "7.dcm", rois / "roi é.dcm", linked]),
          f"DICOM of a database image, a ROI and a linked file: {len(response)} bytes")
    check(len(lookups) == 1, f"the linked paths were looked up {len(lookups)} times for one request")
    response, closed = open_server.exchange([request])
    lookups = [e for e in open_server.drain() if e["event"] == "fetch"]
    check(closed and response == fetched([data_folder / "7.dcm", rois / "roi é.dcm", linked]) and not lookups,
          f"DICOM again, the index unchanged: looked up {len(lookups)} more times")

    refused = {
        "an absolute path outside the database": [str(secret)],
        "an absolute path climbing out of DATABASE.noindex": [f"{open_server.scratch}/DATABASE.noindex/../Database.sql"],
        "a relative path climbing out": ["../Database.sql"],
        "a relative path of more than one component": ["10000/7.dcm"],
        "a current-folder component": ["./7.dcm"],
        "an empty path": [""],
        "a database image, then a path outside": ["7.dcm", str(secret)],
        "a linked file, then a path outside": [str(linked), str(elsewhere / "other.dcm")],
    }
    for label, paths in refused.items():
        response, closed = open_server.exchange([fetch(paths)])
        check(closed and response == b"", f"DICOM {label}: answered {len(response)} bytes")
        after, _ = open_server.exchange([b"AUTHV\0"])
        check(after == i32(1), f"after DICOM {label}: the server stopped answering")
    check(not mutations(open_server.drain()), "a refused DICOM mutated something")

    send = b"DCMSE\0" + text("PEER") + text("10.0.0.9") + text("11112") + text("1")
    response, closed = open_server.exchange([send + i32(2) + text("7.dcm") + text(str(linked))])
    sends = [e for e in mutations(open_server.drain(0.5)) if e["event"] == "sendDICOMFiles"]
    check(closed and len(sends) == 1 and sends[0]["todo"]["Files"] == [str(data_folder / "7.dcm"), str(linked)],
          f"DCMSE of a database image and a linked file: {sends}")
    for paths in (["7.dcm", str(secret)], ["../Database.sql"]):
        response, closed = open_server.exchange([send + i32(len(paths)) + b"".join(text(p) for p in paths)])
        events = mutations(open_server.drain(0.5))
        check(closed and response == b"" and not events, f"DCMSE {paths}: {events}")
    for path in (str(secret), "../Database.sql", str(elsewhere / "other.dcm")):
        response, closed = open_server.exchange([b"MFILE\0" + text(path)])
        check(closed and response == b"", f"MFILE {path}: answered {len(response)} bytes")

    def setva(identifier, value, key):
        return b"SETVA\0" + text(identifier) + (NULL if value is None else text(value)) + text(key)

    for key, value, expected in (("stateText", "2", 2), ("series.study.stateText", "3", 3), ("isKeyImage", "1", 1),
                                 ("lockedStudy", "0", 0), ("comment4", "é", "é"), ("series.study.comment", "c", "c")):
        response, closed = open_server.exchange([setva("x-coredata://probe/Study/k1", value, key)])
        events = mutations(open_server.drain())
        check(closed and events == [{"event": "setValue", "object": "x-coredata://probe/Study/k1", "key": key,
                                     "value": expected}], f"SETVA {key}: {events}")
    for key in ("name", "patientID", "series.study.patientID", "reportURL.lastPathComponent", "comment.length", "@count"):
        response, closed = open_server.exchange([setva("x-coredata://probe/Study/k2", "x", key)])
        events = mutations(open_server.drain())
        check(closed and response == b"" and not events, f"SETVA refused key {key}: {events}")
    response, closed = open_server.exchange([setva("x-coredata://probe/Study/r1", None, "reportURL")])
    events = mutations(open_server.drain())
    check(closed and not report_inside.exists() and events == [{"event": "setValue", "object": "x-coredata://probe/Study/r1",
                                                                "key": "reportURL", "value": None}],
          f"SETVA clearing a report of the database: exists={report_inside.exists()} {events}")
    response, closed = open_server.exchange([setva("x-coredata://probe/Study/r2", None, "reportURL")])
    events = mutations(open_server.drain())
    check(closed and report_outside.exists() and len(events) == 1 and events[0]["value"] is None,
          f"SETVA clearing a report outside the database: exists={report_outside.exists()} {events}")
    response, closed = open_server.exchange([setva("x-coredata://probe/Study/r3", "../../evil.odt", "reportURL")])
    events = mutations(open_server.drain())
    check(closed and events == [{"event": "setValue", "object": "x-coredata://probe/Study/r3", "key": "reportURL",
                                 "value": str(reports / "evil.odt")}], f"SETVA naming a report: {events}")
    response, closed = open_server.exchange([setva("x-coredata://probe/Study/r3", "..", "reportURL")])
    check(closed and not mutations(open_server.drain()), "SETVA naming the reports folder's parent wrote something")

    index_file = open_server.scratch / "Database.sql"
    size = index_file.stat().st_size
    response, closed = open_server.exchange([b"DBSIZ\0"])
    check(closed and response == struct.pack(">I", size), f"DBSIZ answered {response!r} for {size} bytes")
    try:
        with open(index_file, "r+b") as handle:
            handle.truncate(5 << 30)  # sparse
        response, closed = open_server.exchange([b"DBSIZ\0"])
        check(closed and response == b"\xff\xff\xff\xff", f"DBSIZ of a 5 GiB index answered {response!r}")
    finally:
        with open(index_file, "r+b") as handle:
            handle.truncate(size)

    # Invalid requests: closed at once, nothing mutated, server still answers.
    header = b"SETVA\0"
    invalid = {
        "unknown command": b"NOPE!\0",
        "unterminated command": b"SETVAX",
        "negative string length": header + i32(-1) + b"x" * 16,
        "overflowing string length": header + i32(0x7FFFFFFF) + b"x" * 16,
        "string above the limit": header + i32((64 << 20) + 1) + b"x" * 16,
        "string without terminator": header + i32(4) + b"abcd" + text("v") + text("k"),
        "string with embedded terminator": header + i32(4) + b"a\0b\0" + text("v") + text("k"),
        "string not UTF-8": header + i32(3) + b"\xff\xfe\0" + text("v") + text("k"),
        "missing object identifier": header + NULL + text("v") + text("k"),
        "missing key": header + text("x-coredata://probe/Study/p3") + text("v") + NULL,
        "negative count": b"DICOM\0" + i32(-5),
        "count above the limit": b"DICOM\0" + i32((1 << 20) + 1),
        "negative file length": b"SENDD\0" + i32(1) + i32(-100) + b"z" * 32,
        "missing path": b"DICOM\0" + i32(1) + NULL + text("dst"),
        "missing album parameters": b"ADDAL\0" + NULL,
    }
    for label, request in invalid.items():
        started = time.monotonic()
        response, closed = open_server.exchange([request], timeout=3)
        elapsed = time.monotonic() - started
        events = mutations(open_server.drain(0.1))
        check(closed and elapsed < 2 and response == b"" and not events,
              f"{label}: closed={closed} after {elapsed:.2f}s, response={response[:16]!r}, events={events}")
        after, closed_after = open_server.exchange([b"AUTHV\0"])
        check(after == i32(1), f"after {label}: the server stopped answering")
        if not open_server.alive():
            check(False, f"{label}: the server process died")
            open_server = Server()

    # A request the client cuts off releases its connection thread.
    before = open_server.threads()
    for _ in range(12):
        open_server.exchange([b"SETVA\0" + i32(40) + b"partial"], close_after_send=True)
    # Transient system threads come and go; a leak keeps one per request (the
    # revision before #614 went from 20 to 35 threads here).
    after = None
    for _ in range(12):
        time.sleep(0.5)
        after = open_server.threads()
        if before is not None and after is not None and after <= before + 3:
            break
    check(before is not None and after is not None and after <= before + 3,
          f"truncated requests left threads behind: {before} before, {after} after")
    check(not mutations(open_server.drain()), "a truncated request mutated something")
finally:
    open_server.stop()

protected = Server(password="synthetic-é-password")
try:
    def authorized(request, password="synthetic-é-password"):
        secret = password.encode()
        return b"AUTHR\0" + i32(len(secret)) + secret + request

    setva = b"SETVA\0" + text("x-coredata://probe/Study/p9") + text("v") + text("comment")
    response, closed = protected.exchange([setva])
    check(closed and response == b"" and not mutations(protected.drain()), "protected: SETVA without authorization ran")
    response, closed = protected.exchange([authorized(setva, "wrong-password")])
    check(closed and response == b"" and not mutations(protected.drain()), "protected: SETVA with a wrong password ran")
    request = authorized(setva)
    response, closed = protected.exchange(splits(request, [3, 8, 12, 20, 40, len(request) - 1]), delay=0.02)
    events = mutations(protected.drain())
    check(closed and len(events) == 1 and events[0]["object"] == "x-coredata://probe/Study/p9",
          f"protected: authorized fragmented SETVA: {events}")
    response, closed = protected.exchange([b"ISPWD\0"])
    check(response == i32(1), f"protected ISPWD answered {response!r}")
    response, closed = protected.exchange([b"DICOM\0" + i32(1) + text("/etc/hosts") + text("x")])
    check(response == b"", "protected: DICOM served a file without authorization")
finally:
    protected.stop()

shutil.rmtree(work, ignore_errors=True)
if failures:
    print(f"{len(failures)} failure(s)")
    raise SystemExit(1)
print("PASS: SETVA split at every byte, nil versus empty, ADDAL/REMAL, fragmented SENDD, DICOM, DCMSE, MFILE, "
      f"{len(invalid)} invalid requests closed without effect, truncated requests release their thread, "
      f"password protection with and without fragments, {len(refused)} paths outside the database refused, "
      "linked files looked up once, SETVA keys and reports, DBSIZ above 4 GiB")
