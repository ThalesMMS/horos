#!/usr/bin/env python3
"""Two development apps sharing a database, and what the server refuses (#637).

The server app shares its fresh private database (password protected, unless
--no-password) holding a synthetic CT study imported through INCOMING.noindex
(copied into DATABASE.noindex) and one linked in place (File > Import with
COPYDATABASE NO); one study has a report inside the database's REPORTS folder,
the other a report elsewhere. A second app, the client, opens it as a remote
database through RemoteDicomDatabase (tools/probe-shared-database-pair.m,
injected in both).

Through the client, as the browser and the viewer use it:
  index     every study and image of the server
  files     every image downloaded, byte for byte, the linked ones included
  metadata  a study comment, a state and a key image, read back in the server's index
  report    clearing the report inside REPORTS deletes it; clearing the one
            elsewhere clears the reference and keeps the file
  album     a study added to a regular album and removed again
  send      the server sends the copied study to a DICOM node (a local store SCP)

Straight to the server's port, authorized, as a hostile client would: a file
outside the database by absolute path, `..` out of DATABASE.noindex, a path of
another shape, a key the client never sets, MFILE outside - each closed without
an answer, nothing written, the refusal in the server's log, the app still
serving. At efb2b0cef the file outside is served (#637).

    local-validation/venv/bin/python tools/exercise-native-shared-database-pair.py \\
        --app build/Variants/candidate/HorosDevelopment.app --out local-validation/delta4/637-app/candidate

--no-password shares the database without a password: the client asks for no
password and sends its requests without the authorization envelope, the path a
protected database does not take (#644). The direct requests keep the envelope,
which an unprotected server reads past.

Needs a Python with pydicom, pynetdicom and numpy. Everything is synthetic and
stays under --out; the password exists only in the server's argument domain.
"""
import argparse
import hashlib
import json
import os
import plistlib
import shutil
import socket
import sqlite3
import struct
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import native_app  # noqa: E402

PASSWORD = "synthetic-637-sharing"
PORT = 8780
ALBUM = "Interesting Cases"


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def generate(folder: Path, label: str, count: int) -> dict:
    import numpy
    from pydicom.dataset import Dataset, FileMetaDataset
    from pydicom.uid import CTImageStorage, ExplicitVRLittleEndian, generate_uid
    folder.mkdir(parents=True)
    study, series = generate_uid(), generate_uid()
    sops = []
    for index in range(count):
        ds = Dataset()
        ds.file_meta = FileMetaDataset()
        ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
        ds.SOPClassUID, ds.SOPInstanceUID = CTImageStorage, generate_uid()
        ds.StudyInstanceUID, ds.SeriesInstanceUID = study, series
        ds.PatientName, ds.PatientID = f"SYNTHETIC^{label.upper()}", f"SYN-637-{label}"
        ds.StudyDate, ds.StudyTime, ds.StudyID = "20260917", "120000", "637"
        ds.StudyDescription = f"shared {label}"
        ds.Modality, ds.SeriesNumber, ds.InstanceNumber = "CT", 1, index + 1
        ds.Rows = ds.Columns = 64
        ds.SamplesPerPixel, ds.PhotometricInterpretation = 1, "MONOCHROME2"
        ds.BitsAllocated, ds.BitsStored, ds.HighBit, ds.PixelRepresentation = 16, 12, 11, 0
        ds.PixelSpacing, ds.SliceThickness = [1, 1], 1
        ds.ImageOrientationPatient, ds.ImagePositionPatient = [1, 0, 0, 0, 1, 0], [0, 0, index]
        y, x = numpy.mgrid[0:64, 0:64]
        ds.PixelData = ((x * 7 + y * 3 + index * 11) % 4000).astype(numpy.uint16).tobytes()
        ds.save_as(folder / f"{label}-{index + 1}.dcm", enforce_file_format=True)
        sops.append(str(ds.SOPInstanceUID))
    return {"study": str(study), "sops": sops}


def prepare_bundle(app: Path, out: Path):
    entitlements = plistlib.loads((ROOT / "build/Development/entitlements.plist").read_bytes())
    entitlements["com.apple.security.cs.allow-dyld-environment-variables"] = True
    path = out / "probe-entitlements.plist"
    path.write_bytes(plistlib.dumps(entitlements))
    subprocess.run(["/usr/bin/codesign", "--force", "--sign", "-", "--options", "runtime", "--entitlements", str(path),
                    str(app)], check=True, capture_output=True)


class App:
    def __init__(self, app, root, log, dylib, role, arguments):
        self.commands = Path(tempfile.mkdtemp(prefix=f"pair-{role}-", dir=str(root.parent)))
        self.number = 0
        self.log = log
        self.process = native_app.launch(root, log, arguments, app=app,
                                         environment={"DYLD_INSERT_LIBRARIES": str(dylib), "HOROS_PAIR_ROLE": role,
                                                      "HOROS_PAIR_COMMANDS": str(self.commands)})

    def alive(self):
        return self.process.poll() is None

    def command(self, payload, timeout=180):
        self.number += 1
        answer = self.commands / f"{self.number}.out.json"
        staging = self.commands / f".{self.number}.json"
        staging.write_text(json.dumps(payload))
        os.rename(staging, self.commands / f"{self.number}.json")
        native_app.wait_for(lambda: answer.exists() or not self.alive(), timeout, interval=0.1,
                            description=f"the answer to {payload['action']}")
        return json.loads(answer.read_text()) if answer.exists() else {"error": "the app died"}

    def stop(self):
        native_app.stop(self.process)
        shutil.rmtree(self.commands, ignore_errors=True)


def i32(value):
    return struct.pack(">i", value)


def text(value):
    raw = value.encode() + b"\0"
    return i32(len(raw)) + raw


def authorized(request):
    secret = PASSWORD.encode()
    return b"AUTHR\0" + i32(len(secret)) + secret + request


def exchange(request, timeout=10):
    with socket.create_connection(("127.0.0.1", PORT), timeout=5) as s:
        s.sendall(request)
        s.settimeout(timeout)
        response = bytearray()
        try:
            while chunk := s.recv(1 << 20):
                response.extend(chunk)
            return bytes(response), True
        except socket.timeout:
            return bytes(response), False
        except ConnectionResetError:
            return bytes(response), True


def query(sql_path: Path, statement, arguments=()):
    with sqlite3.connect(f"file:{sql_path}?mode=ro", uri=True, timeout=5) as db:
        return db.execute(statement, arguments).fetchall()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--app", type=Path, default=native_app.DEVELOPMENT_APP)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--no-password", action="store_true", help="share the database without a password")
    arguments = parser.parse_args()
    protected = not arguments.no_password
    out = arguments.out.resolve()
    if "local-validation" not in out.parts:
        parser.error("--out must be under local-validation")
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    app = arguments.app.resolve()
    prepare_bundle(app, out)
    dylib = out / "probe-shared-database-pair.dylib"
    subprocess.run(["xcrun", "clang", "-dynamiclib", "-fobjc-arc", "-framework", "Cocoa", "-framework", "CoreData",
                    str(ROOT / "tools/probe-shared-database-pair.m"), "-o", str(dylib)], check=True)

    copied = generate(out / "fixture-copied", "copied", 4)
    linked = generate(out / "linked-in-place", "linked", 2)
    secret = out / "outside" / "secret.txt"
    secret.parent.mkdir()
    secret.write_bytes(b"a file the shared database must not serve")
    report_elsewhere = out / "outside" / "report elsewhere.odt"
    report_elsewhere.write_bytes(b"a report kept outside the database")

    results, failures = {"checks": [], "password_protected": protected}, []

    def check(condition, message):
        results["checks"].append({"check": message, "ok": bool(condition)})
        if not condition:
            failures.append(message)
            print("FAIL:", message)

    store_port = free_port()
    store = subprocess.Popen([sys.executable, str(ROOT / "tools/serve-store-fixture.py"), str(out / "store"), "--port",
                              str(store_port), "--aetitle", "PAIRSTORE", "--store-to", str(out / "store/received")],
                             stdout=open(out / "store.log", "w"), stderr=subprocess.STDOUT)
    server_root, client_root = out / "server", out / "client"
    data = native_app.database_folder(server_root)
    server = client = None
    native_app.stop_all(app)
    try:
        server = App(app, server_root, out / "server.log", dylib, "server",
                     ["-bonjourSharing", "YES"]
                     + (["-bonjourPasswordProtected", "YES", "-bonjourPassword", PASSWORD] if protected
                        else ["-bonjourPasswordProtected", "NO"])
                     + ["-COPYDATABASE", "NO", "-STORESCP", "NO", "-hideListenerError", "YES", "-publishDICOMBonjour", "NO",
                      "-searchDICOMBonjour", "NO", "-syncDICOMNodes", "NO"])
        native_app.wait_for(lambda: (data / "INCOMING.noindex").is_dir(), 90, description="the server's database")
        check(server.command({"action": "ping"}).get("ok"), "the server's probe answers")
        for path in sorted((out / "fixture-copied").glob("*.dcm")):
            staging = data / "INCOMING.noindex" / f".{path.name}.part"
            shutil.copyfile(path, staging)
            os.rename(staging, data / "INCOMING.noindex" / path.name)
        native_app.wait_for(lambda: (native_app.image_count(server_root) or 0) >= 4, 120, interval=0.5,
                            description="the copied study")
        server.command({"action": "link", "paths": [str(out / "linked-in-place")]})
        native_app.wait_for(lambda: (native_app.image_count(server_root) or 0) >= 6, 120, interval=0.5,
                            description="the linked study")
        native_app.wait_for(lambda: socket.socket().connect_ex(("127.0.0.1", PORT)) == 0, 60, description="sharing")
        sql = data / "Database.sql"
        linked_rows = query(sql, "SELECT ZPATHSTRING FROM ZIMAGE WHERE ZPATHSTRING LIKE '/%'")
        check(len(linked_rows) == 2 and all(r[0].startswith(str(out / "linked-in-place")) for r in linked_rows),
              f"the server links two images in place ({linked_rows})")
        reports = data / "REPORTS"
        reports.mkdir(exist_ok=True)
        report_inside = reports / "report inside.odt"
        report_inside.write_bytes(b"a report of the database")
        check(server.command({"action": "report", "study": copied["study"], "path": str(report_inside)}).get("ok"),
              "report inside REPORTS recorded")
        check(server.command({"action": "report", "study": linked["study"], "path": str(report_elsewhere)}).get("ok"),
              "report elsewhere recorded")

        client = App(app, client_root, out / "client.log", dylib, "client",
                     ["-STORESCP", "NO", "-hideListenerError", "YES", "-publishDICOMBonjour", "NO", "-searchDICOMBonjour", "NO",
                      "-syncDICOMNodes", "NO", "-bonjourSharing", "NO"])
        native_app.wait_for(lambda: (native_app.database_folder(client_root) / "INCOMING.noindex").is_dir(), 90,
                            description="the client's database")
        opened = client.command({"action": "open", "port": PORT, **({"password": PASSWORD} if protected else {})},
                                timeout=240)
        results["opened"] = opened
        # The server archives a study's reports and annotations as DICOM SR images of its own.
        served = query(sql, "SELECT COUNT(*) FROM ZIMAGE")[0][0]
        check(opened.get("studies") == 2 and opened.get("images") == served,
              f"index: the client sees {opened}, the server holds {served} images")

        images = client.command({"action": "images"}).get("images", [])
        results["client_images"] = images
        expected = {}
        for sop, path in zip(copied["sops"], sorted((out / "fixture-copied").glob("*.dcm"))):
            expected[sop] = hashlib.sha256(path.read_bytes()).hexdigest()
        for sop, path in zip(linked["sops"], sorted((out / "linked-in-place").glob("*.dcm"))):
            expected[sop] = hashlib.sha256(path.read_bytes()).hexdigest()
        downloads = client.command({"action": "download", "sops": list(expected)}, timeout=240).get("files", [])
        results["downloads"] = downloads
        got = {d["sop"]: d["sha256"] for d in downloads}
        check(len(downloads) == 6 and all(got.get(sop) == digest for sop, digest in expected.items()),
              f"files: {sum(got.get(s) == d for s, d in expected.items())} of 6 downloaded byte for byte (linked included)")
        # The same files asked of the server directly, by the paths the index gives the client:
        # what the server serves, apart from the client's own download code (#644).
        paths = {row["sop"]: row["path"] for row in images}
        fetched = 0
        for sop, digest in expected.items():
            request = b"DICOM\0" + i32(1) + text(paths.get(sop, "")) + text("dst.dcm")
            response, closed = exchange(authorized(request))
            if len(response) >= 8 and struct.unpack(">i", response[:4])[0] == 1:
                size = struct.unpack(">i", response[4:8])[0]
                fetched += hashlib.sha256(response[8:8 + size]).hexdigest() == digest
        check(fetched == len(expected), f"files served: {fetched} of {len(expected)} fetched from the server byte for byte "
                                        f"(copied by name, linked by absolute path)")

        client.command({"action": "set", "study": copied["study"], "key": "comment", "value": "shared comment é"})
        client.command({"action": "set", "study": copied["study"], "key": "stateText", "value": 2})
        client.command({"action": "set", "sop": copied["sops"][0], "key": "isKeyImage", "value": 1})
        time.sleep(2)
        row = query(sql, "SELECT ZCOMMENT, ZSTATETEXT FROM ZSTUDY WHERE ZSTUDYINSTANCEUID = ?", (copied["study"],))
        keys = query(sql, "SELECT COUNT(*) FROM ZIMAGE WHERE ZSTOREDISKEYIMAGE = 1")[0][0]
        check(row == [("shared comment é", 2)] and keys == 1, f"metadata: study {row}, key images {keys}")

        client.command({"action": "set", "study": copied["study"], "key": "reportURL", "value": None})
        client.command({"action": "set", "study": linked["study"], "key": "reportURL", "value": None})
        time.sleep(2)
        urls = dict(query(sql, "SELECT ZSTUDYINSTANCEUID, ZREPORTURL FROM ZSTUDY"))
        check(not report_inside.exists() and urls.get(copied["study"]) is None,
              f"report inside REPORTS deleted and cleared (exists={report_inside.exists()}, url={urls.get(copied['study'])})")
        check(report_elsewhere.exists() and urls.get(linked["study"]) is None,
              f"report elsewhere kept and cleared (exists={report_elsewhere.exists()}, url={urls.get(linked['study'])})")

        albums = client.command({"action": "albums"}).get("albums", [])
        check(ALBUM in albums, f"the remote index has the regular album {ALBUM!r} ({albums})")
        entities = dict(query(sql, "SELECT Z_NAME, Z_ENT FROM Z_PRIMARYKEY"))
        link_table = next(name for (name,) in query(sql, "SELECT name FROM sqlite_master WHERE type='table'")
                          if name.startswith(f"Z_{entities['Album']}STUDIES"))
        for add, expected_rows in ((True, 1), (False, 0)):
            client.command({"action": "album", "study": copied["study"], "album": ALBUM, "add": add})
            time.sleep(2)
            rows = query(sql, f"SELECT COUNT(*) FROM {link_table}")[0][0]
            check(rows == expected_rows, f"album: {'added' if add else 'removed'}, {rows} study in it")

        client.command({"action": "send", "sops": copied["sops"], "aet": "PAIRSTORE", "address": "127.0.0.1",
                        "port": store_port})
        try:
            native_app.wait_for(lambda: len(list((out / "store/received").rglob("*"))) >= 4, 60, description="the send")
        except TimeoutError:
            pass
        received = [p for p in (out / "store/received").rglob("*") if p.is_file()]
        check(len(received) == 4, f"send: the store received {len(received)} of 4 images")

        refused = {
            "DICOM of a file outside the database": b"DICOM\0" + i32(1) + text(str(secret)) + text("dst"),
            "DICOM climbing out of DATABASE.noindex": b"DICOM\0" + i32(1) + text("../Database.sql") + text("dst"),
            "DICOM of a path of another shape": b"DICOM\0" + i32(1) + text("10000/1.dcm") + text("dst"),
            "SETVA of a key the client never sets": b"SETVA\0" + text(f"x-coredata://nothing/Study/p1") + text("x")
                                                    + text("patientID"),
            "MFILE outside the database": b"MFILE\0" + text(str(secret)),
            "DCMSE of a file outside the database": b"DCMSE\0" + text("PAIRSTORE") + text("127.0.0.1")
                                                    + text(str(store_port)) + text("1") + i32(1) + text(str(secret)),
        }
        before = native_app.image_count(server_root)
        for label, request in refused.items():
            response, closed = exchange(authorized(request))
            check(closed and response == b"", f"refused: {label} (answered {len(response)} bytes)")
        time.sleep(3)
        received_after = [p for p in (out / "store/received").rglob("*") if p.is_file()]
        check(len(received_after) == 4, f"nothing more was sent ({len(received_after)} received)")
        check(native_app.image_count(server_root) == before, "nothing was added to the server's index")
        size = struct.unpack(">I", exchange(authorized(b"DBSIZ\0"))[0])[0]
        check(0 < size == sql.stat().st_size, f"the server still answers DBSIZ ({size} bytes)")
        check(server.alive() and client.alive(), "both apps are still running")
    finally:
        for instance in (client, server):
            if instance:
                instance.stop()
        store.terminate()
        try:
            store.wait(timeout=10)
        except subprocess.TimeoutExpired:
            store.kill()

    log = (out / "server.log").read_text(errors="replace")
    results["server_refusals"] = [line.split("closed: ", 1)[1].strip() for line in log.splitlines()
                                  if "Shared database: request from" in line and "closed: " in line]
    check(len(results["server_refusals"]) == len(refused),
          f"the server logged {len(results['server_refusals'])} refusals for {len(refused)} refused requests")
    results["failures"] = failures
    for path in set(out.rglob("*.dcm")) | {p for p in (out / "store/received").rglob("*") if p.is_file()}:
        path.unlink(missing_ok=True)
    (out / "results.json").write_text(json.dumps(results, indent=1, ensure_ascii=False) + "\n")
    passed = sum(1 for c in results["checks"] if c["ok"])
    print(f"{passed} of {len(results['checks'])} checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
