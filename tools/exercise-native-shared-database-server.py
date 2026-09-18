#!/usr/bin/env python3
"""Drive the built app's shared-database server over loopback (#614).

Launches the isolated development bundle with database sharing on, password
protected, on a fresh private database; imports a synthetic fixture through
INCOMING; then talks to 127.0.0.1:8780 with requests encoded exactly as
RemoteDicomDatabase encodes them:

  auth      public commands answer; protected ones refuse no or a wrong password
  index     DBSIZ and DATAB agree, the index opens as SQLite with every image
  files     DICOM returns each image file byte for byte
  metadata  SETVA writes a study comment, read back from a fresh index
  album     ADDAL puts a study in an album, REMAL takes it out again
  invalid   malformed requests close their connection; the app keeps serving
  truncated requests cut off by the client do not leave threads behind

    python3 tools/exercise-native-shared-database-server.py \
        --fixture local-validation/delta4/fixtures/jpegls --out local-validation/delta4/614-app

Everything is synthetic and stays under --out; the password exists only in the
app's argument domain for this run.
"""
import argparse
import hashlib
import json
import os
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

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("--fixture", type=Path, required=True)
parser.add_argument("--out", type=Path, required=True)
parser.add_argument("--app", type=Path, default=native_app.DEVELOPMENT_APP)
arguments = parser.parse_args()

PASSWORD = "synthetic-Δ4-sharing"
PORT = 8780
out = arguments.out.resolve()
if out.exists():
    shutil.rmtree(out)
out.mkdir(parents=True)
root = out / "database"
data = native_app.database_folder(root)
results = {"checks": []}
failures = []


def check(condition, message):
    results["checks"].append({"check": message, "ok": bool(condition)})
    if not condition:
        failures.append(message)
        print("FAIL:", message)


def i32(value):
    return struct.pack(">i", value)


def text(value):
    raw = value.encode() + b"\0"
    return i32(len(raw)) + raw


def authorized(request, password=PASSWORD):
    secret = password.encode()
    return b"AUTHR\0" + i32(len(secret)) + secret + request


def exchange(request, timeout=10, close_after_send=False):
    with socket.create_connection(("127.0.0.1", PORT), timeout=5) as s:
        s.sendall(request)
        if close_after_send:
            return b"", True
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


def fetch_index(label):
    size = struct.unpack(">I", exchange(authorized(b"DBSIZ\0"))[0])[0]
    index, closed = exchange(authorized(b"DATAB\0"), timeout=30)
    path = out / f"index-{label}.sql"
    path.write_bytes(index)
    return size, index, path


def thread_count(pid):
    lines = subprocess.run(["/bin/ps", "-M", "-p", str(pid)], capture_output=True, text=True).stdout.splitlines()
    return max(0, len(lines) - 1)


native_app.stop_all(arguments.app)
process = native_app.launch(root, out / "horos.log",
                            ["-bonjourSharing", "YES", "-bonjourPasswordProtected", "YES", "-bonjourPassword", PASSWORD],
                            app=arguments.app)
try:
    native_app.wait_for(lambda: (data / "INCOMING.noindex").is_dir(), 90, description="the database to open")
    names = sorted(p.name for p in arguments.fixture.glob("*.dcm"))
    for name in names:
        staging = data / "INCOMING.noindex" / f".{name}.part"
        shutil.copyfile(arguments.fixture / name, staging)
        os.rename(staging, data / "INCOMING.noindex" / name)
    native_app.wait_for(lambda: (native_app.image_count(root) or 0) >= len(names), 120, interval=0.5,
                        description="the fixture to be indexed")
    native_app.wait_for(lambda: socket.socket().connect_ex(("127.0.0.1", PORT)) == 0, 60,
                        description="the shared-database listener")
    results["images_imported"] = native_app.image_count(root)

    # auth
    check(exchange(b"AUTHV\0")[0] == i32(1), "AUTHV answers version 1")
    check(exchange(b"ISPWD\0")[0] == i32(1), "ISPWD reports password protection")
    check(exchange(b"DATAB\0")[0] == b"", "DATAB without authorization returns nothing")
    check(exchange(authorized(b"DATAB\0", "wrong password"))[0] == b"", "DATAB with a wrong password returns nothing")

    # index
    size, index, index_path = fetch_index("before")
    results["index_bytes"] = len(index)
    check(size == len(index) and index.startswith(b"SQLite format 3\0"), f"DBSIZ {size} matches DATAB {len(index)}")
    with sqlite3.connect(f"file:{index_path}?mode=ro", uri=True) as db:
        images = db.execute("SELECT Z_PK, ZPATHNUMBER, ZPATHSTRING FROM ZIMAGE").fetchall()
        studies = db.execute("SELECT Z_PK FROM ZSTUDY").fetchall()
        store = db.execute("SELECT Z_UUID FROM Z_METADATA").fetchone()[0]
        entities = dict(db.execute("SELECT Z_NAME, Z_ENT FROM Z_PRIMARYKEY").fetchall())
        albums = db.execute("SELECT Z_PK, ZNAME FROM ZALBUM WHERE ZSMARTALBUM IS NULL OR ZSMARTALBUM = 0").fetchall() \
            if "Album" in entities else []
    check(len(images) == len(names), f"the index lists {len(images)} of {len(names)} images")

    # files: DICOM fetch by the relative names the client sends
    stored = {}
    for pk, number, string in images:
        relative = string if string else f"{number}.dcm"
        found = list((data / "DATABASE.noindex").rglob(Path(relative).name))
        if found:
            stored[relative] = found[0].read_bytes()
    request = b"DICOM\0" + i32(len(stored)) + b"".join(text(r) for r in stored) + b"".join(text(f"dst/{r}") for r in stored)
    response, closed = exchange(authorized(request), timeout=30)
    offset, count = 4, struct.unpack(">I", response[:4])[0] if len(response) >= 4 else -1
    fetched = {}
    for relative in stored:
        length = struct.unpack(">I", response[offset:offset + 4])[0]; offset += 4
        content = response[offset:offset + length]; offset += length
        dst_length = struct.unpack(">I", response[offset:offset + 4])[0]; offset += 4
        destination = response[offset:offset + dst_length - 1].decode(); offset += dst_length
        fetched[destination] = content
    check(count == len(stored) and all(fetched.get(f"dst/{r}") == stored[r] for r in stored),
          f"DICOM returned {len(fetched)} files byte for byte")

    # metadata
    study_uri = f"x-coredata://{store}/Study/p{studies[0][0]}"
    comment = "synthetic Δ4 comment é"
    exchange(authorized(b"SETVA\0" + text(study_uri) + text(comment) + text("comment")))
    time.sleep(1)
    _, _, after_path = fetch_index("after-setva")
    with sqlite3.connect(f"file:{after_path}?mode=ro", uri=True) as db:
        written = db.execute("SELECT ZCOMMENT FROM ZSTUDY WHERE Z_PK = ?", (studies[0][0],)).fetchone()[0]
    check(written == comment, f"SETVA wrote the study comment ({written!r})")

    # album
    results["albums"] = [name for _, name in albums]
    if albums:
        album_uri = f"x-coredata://{store}/Album/p{albums[0][0]}"
        params = '{ albumStudies = ( "%s" ); albumUID = "%s"; }' % (study_uri, album_uri)
        link = f"Z_{entities['Album']}STUDIES"
        for command, expected in (("ADDAL", 1), ("REMAL", 0)):
            exchange(authorized(command.encode() + b"\0" + text(params)))
            time.sleep(1)
            _, _, path = fetch_index(command.lower())
            with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as db:
                tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
                table = next((t for t in tables if t.startswith(f"Z_{entities['Album']}") and "STUDIES" in t), None)
                rows = db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] if table else -1
            check(rows == expected, f"{command} leaves {rows} study in the album (expected {expected})")
    else:
        check(False, "the fresh database has no regular album to exercise ADDAL/REMAL")

    # invalid
    malformed = {
        "negative string length": b"SETVA\0" + i32(-1) + b"x" * 8,
        "string above the limit": b"SETVA\0" + i32((64 << 20) + 1),
        "string not UTF-8": b"SETVA\0" + i32(3) + b"\xff\xfe\0" + text("v") + text("k"),
        "negative count": b"DICOM\0" + i32(-3),
        "missing path": b"DICOM\0" + i32(1) + i32(0) + text("dst"),
    }
    for label, request in malformed.items():
        started = time.monotonic()
        response, closed = exchange(authorized(request), timeout=5)
        check(closed and response == b"" and time.monotonic() - started < 3, f"{label}: closed at once without data")
    check(struct.unpack(">I", exchange(authorized(b"DBSIZ\0"))[0])[0] > 0, "the app still serves after malformed requests")

    # truncated
    before = thread_count(process.pid)
    for _ in range(12):
        exchange(authorized(b"SETVA\0" + i32(64) + b"cut off"), close_after_send=True)
    after = before
    for _ in range(12):
        time.sleep(0.5)
        after = thread_count(process.pid)
        if after <= before + 3:
            break
    results["threads"] = {"before": before, "after": after}
    check(after <= before + 3, f"truncated requests left threads behind ({before} → {after})")
    check(process.poll() is None, "the app is still running")
finally:
    native_app.stop(process)

log = (out / "horos.log").read_text(errors="replace")
results["log_rejections"] = sorted({line.split("closed: ", 1)[1].strip() for line in log.splitlines()
                                    if "Shared database: request from" in line and "closed: " in line})
(out / "results.json").write_text(json.dumps(results, indent=1, ensure_ascii=False) + "\n")
print(json.dumps(results, indent=1, ensure_ascii=False))
raise SystemExit(1 if failures else 0)
