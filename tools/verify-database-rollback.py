#!/usr/bin/env python3
"""Rollback rehearsal on an isolated copy of the database (#385).

The release gate asks for rollback «testado em cópia isolada do banco,
preservando artefato/dados anteriores recuperáveis; nunca em banco real como
smoke destrutivo». This copies a database folder, reports what the copy holds,
and checks the two things a rollback depends on:

- the Core Data model the application would open is byte-identical to the one
  the rollback target ships, so a previous build reads the same file;
- the copy is complete and independent: counts and SHA-256 of the store files
  match the original, and the original is never written.

It opens nothing and launches nothing. The copy is left in place for a manual
launch against it.

    python3 tools/verify-database-rollback.py SOURCE_DB_FOLDER DESTINATION [--model DIR]
"""
import argparse
import hashlib
import json
import shutil
import sqlite3
import subprocess
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('source', type=Path, help='the "Horos Data" folder to copy')
parser.add_argument('destination', type=Path, help='empty destination for the isolated copy')
parser.add_argument('--model', type=Path, default=Path('Horos/Models/OsiriXDB_DataModel.xcdatamodeld'))
parser.add_argument('--baseline', default='main', help='git revision of the rollback target')
parser.add_argument('--json', type=Path, default=None)
args = parser.parse_args()
if not args.source.is_dir():
    parser.error('source is not a directory: %s' % args.source)
if args.destination.exists() and any(args.destination.iterdir()):
    parser.error('destination must be empty: %s' % args.destination)


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def store_summary(folder):
    stores = sorted(folder.glob('*.sql')) + sorted(folder.glob('*.sqlite'))
    rows = []
    for store in stores:
        entry = {'file': store.name, 'bytes': store.stat().st_size, 'sha256': sha256(store)}
        try:
            connection = sqlite3.connect('file:%s?mode=ro' % store, uri=True)
            tables = [name for (name,) in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
            entry['tables'] = len(tables)
            for table in ('ZSTUDY', 'ZSERIES', 'ZIMAGE'):
                if table in tables:
                    entry[table.lower()] = connection.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0]
            connection.close()
        except sqlite3.Error as error:
            entry['sqliteError'] = str(error)
        rows.append(entry)
    return rows


before = store_summary(args.source)
args.destination.parent.mkdir(parents=True, exist_ok=True)
shutil.copytree(args.source, args.destination, dirs_exist_ok=True, symlinks=True)
after = store_summary(args.destination)
source_after = store_summary(args.source)

model_changed = subprocess.run(['git', 'diff', '--name-only', '%s...HEAD' % args.baseline, '--', str(args.model)],
                               capture_output=True, text=True).stdout.split()
report = {
    'source': str(args.source),
    'destination': str(args.destination),
    'rollbackTarget': args.baseline,
    'modelPath': str(args.model),
    'modelChangedSinceTarget': model_changed,
    'storesBefore': before,
    'storesInCopy': after,
    'sourceUnchanged': before == source_after,
    'copyMatchesSource': [a['sha256'] for a in before] == [b['sha256'] for b in after],
    'filesCopied': sum(1 for path in args.destination.rglob('*') if path.is_file()),
    'filesInSource': sum(1 for path in args.source.rglob('*') if path.is_file()),
}
report['complete'] = report['filesCopied'] == report['filesInSource']
if args.json:
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, indent=1) + '\n')
print(json.dumps(report, indent=1))
if not (report['sourceUnchanged'] and report['copyMatchesSource'] and report['complete']):
    raise SystemExit('the isolated copy is not a faithful, non-destructive copy')
if model_changed:
    raise SystemExit('the data model changed since %s: a previous build would not open this database unchanged'
                     % args.baseline)
