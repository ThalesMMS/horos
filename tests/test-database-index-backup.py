#!/usr/bin/env python3
"""Verify the Swift recovery snapshot against real SQLite/WAL and failure cases."""
import hashlib
import shutil
from pathlib import Path
import sqlite3
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='horos-index-backup-') as temporary:
    work = Path(temporary)
    main = work / 'Main.swift'
    main.write_text('''import Foundation
@main struct Main {
 static func main() {
  do { print(try DatabaseIndexBackup.snapshot(atPath: CommandLine.arguments[1], metadataPath: CommandLine.arguments.count > 2 ? CommandLine.arguments[2] : nil)) }
  catch { fputs("BACKUP FAILED: \\(error.localizedDescription)\\n", stderr); exit(1) }
 }
}
''')
    binary = work / 'backup'
    subprocess.run(['swiftc', str(root / 'Horos/Sources/DatabaseIndexBackup.swift'), str(main), '-o', str(binary)], check=True)

    def run(source, metadata=None, success=True):
        result = subprocess.run([str(binary), str(source)] + ([str(metadata)] if metadata else []), capture_output=True, text=True)
        assert (result.returncode == 0) == success, result.stderr
        return Path(result.stdout.strip()) if success else None

    source = work / 'Database.sql'
    connection = sqlite3.connect(source)
    connection.execute('pragma journal_mode=wal')
    connection.execute('pragma wal_autocheckpoint=0')
    connection.execute('create table images (uid text primary key, patient text)')
    connection.executemany('insert into images values (?, ?)', [(f'synthetic-{i}', f'patient-{i % 40}') for i in range(640)])
    connection.commit()
    metadata = work / 'DB_VERSION'
    metadata.write_text('synthetic-model-version')
    old = work / 'Database.sql - old'
    old.write_bytes(b'previous valuable recovery copy')
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in (source, Path(str(source)+'-wal'), metadata, old)}
    first = run(source, metadata)
    recovered = sqlite3.connect((first / source.name).as_uri() + '?mode=ro', uri=True)
    assert recovered.execute('select count(*) from images').fetchone()[0] == 640
    assert recovered.execute('pragma integrity_check').fetchone()[0] == 'ok'
    recovered.close()
    assert (first / metadata.name).read_bytes() == metadata.read_bytes()
    standalone = work / 'standalone.sql'
    shutil.copyfile(first / source.name, standalone)
    standalone_connection = sqlite3.connect(standalone)
    assert standalone_connection.execute('select count(*) from images').fetchone()[0] == 640
    assert standalone_connection.execute('pragma journal_mode').fetchone()[0] == 'delete'
    standalone_connection.close()
    first_hash = hashlib.sha256((first / source.name).read_bytes()).hexdigest()
    second = run(source, metadata)
    assert first != second and first.exists() and second.exists()
    assert hashlib.sha256((first / source.name).read_bytes()).hexdigest() == first_hash
    for p, digest in before.items():
        assert hashlib.sha256(p.read_bytes()).hexdigest() == digest, p
    run(source, work / 'missing-metadata', success=False)
    assert len(list((work / 'Index Backups').iterdir())) == 2
    run(work / 'missing.sql', success=False)
    assert not (work / 'missing.sql').exists()
    corrupt = work / 'corrupt.sql'
    corrupt.write_bytes(b'not a SQLite database')
    run(corrupt, success=False)
    assert corrupt.read_bytes() == b'not a SQLite database'
    blocked = work / 'blocked'
    blocked.mkdir()
    (blocked / 'Index Backups').write_bytes(b'keep this file')
    other = sqlite3.connect(blocked / 'Database.sql')
    other.execute('create table t (id integer)')
    other.commit(); other.close()
    run(blocked / 'Database.sql', success=False)
    assert (blocked / 'Index Backups').read_bytes() == b'keep this file'
    assert len(list((work / 'Index Backups').iterdir())) == 2
    locked = sqlite3.connect(work / 'locked.sql')
    locked.execute('create table t (id integer)'); locked.commit()
    locked.execute('begin exclusive')
    result = subprocess.run([str(binary), str(work / 'locked.sql')], capture_output=True, text=True, timeout=10)
    assert result.returncode != 0 and 'locked' in result.stderr.lower(), result.stderr
    locked.rollback(); locked.close()
    assert len(list((work / 'Index Backups').iterdir())) == 2
    connection.close()
    print('PASS: live WAL snapshot, integrity, metadata, repeated backups, original hashes, missing/corrupt input, locked source and blocked destination')
