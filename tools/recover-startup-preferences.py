#!/usr/bin/env python3
"""Reset only the preferences that can stop Horos from starting, keeping everything else.

"Delete the preferences" is the usual advice for a launch that hangs, and it also
throws away the DICOM node list, the hanging protocols, the annotation layouts
and the window state, none of which have anything to do with starting up. This
resets a named, short list instead, after writing the whole domain to a backup
file, and it never touches the database, the images or the plugins.

    python3 tools/recover-startup-preferences.py --list
    python3 tools/recover-startup-preferences.py --domain org.horosproject.horos --dry-run
    python3 tools/recover-startup-preferences.py --domain org.horosproject.horos --group database

Run it with Horos closed: macOS caches preferences per process and a running
application will write its own copy back over yours.
"""
import argparse, datetime, plistlib, shutil, subprocess, sys
from pathlib import Path

# Each group is one reason a launch stops, with the keys that carry it.
GROUPS = {
    'database': (
        'the database is on a volume that is not mounted, so the launch waits on '
        'a panel; this puts the database back in the home folder without moving '
        'or deleting any data',
        ['DATABASELOCATION', 'DATABASELOCATIONURL',
         'DEFAULT_DATABASELOCATION', 'DEFAULT_DATABASELOCATIONURL'],
    ),
    'windows': (
        'saved window frames from another display can place a window out of reach',
        ['NSWindow Frame QR', 'NSWindow Frame DBWindow', 'DBWindowFrame',
         'SPLITVERT', 'SPLITHORZ', 'NSWindow Frame 3DPosition'],
    ),
    'network': (
        'the query window opens at launch and a node that cannot answer keeps it '
        'there; the listener and auto-routing start before the interface is up',
        ['isQueryControllerVisible', 'STORESCP', 'USESTORESCP',
         'AUTOROUTINGACTIVATED', 'bonjourSharing', 'httpXMLRPCServer'],
    ),
    'plugins': (
        'a plugin that fails to load takes the launch with it; this only turns off '
        'the update check and the crash prompt, and removes no plugin',
        ['checkForUpdatesPlugins', 'DoNotDeleteCrashingPlugins'],
    ),
}


def domain_path(domain):
    return Path.home() / 'Library' / 'Preferences' / (domain + '.plist')


def read_domain(domain):
    result = subprocess.run(['defaults', 'export', domain, '-'],
                            capture_output=True)
    if result.returncode != 0:
        raise SystemExit(f'no preferences for {domain}: {result.stderr.decode().strip()}')
    return plistlib.loads(result.stdout)


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--domain', default='org.horosproject.horos',
                        help='preferences domain (default: the released application)')
    parser.add_argument('--group', action='append', choices=sorted(GROUPS),
                        help='reset one group; repeatable. Default: every group')
    parser.add_argument('--backup-dir', type=Path, default=Path.cwd(),
                        help='where to write the backup (default: the current directory)')
    parser.add_argument('--dry-run', action='store_true',
                        help='say what would be reset and change nothing')
    parser.add_argument('--list', action='store_true', help='describe the groups and exit')
    options = parser.parse_args()

    if options.list:
        for name, (why, keys) in GROUPS.items():
            print(f'{name}: {why}')
            for key in keys:
                print(f'    {key}')
        return 0

    groups = options.group or sorted(GROUPS)
    values = read_domain(options.domain)
    present = [(group, key) for group in groups for key in GROUPS[group][1] if key in values]
    if not present:
        print(f'{options.domain}: none of the selected keys are set; nothing to reset')
        return 0

    print(f'{options.domain}: {len(present)} key(s) would be reset')
    for group, key in present:
        print(f'  [{group}] {key} = {values[key]!r}')
    if options.dry_run:
        print('dry run: nothing was changed')
        return 0

    running = subprocess.run(['pgrep', '-f', 'Horos.app/Contents/MacOS/Horos'],
                             capture_output=True)
    if running.returncode == 0:
        raise SystemExit('Horos is running; quit it first or its own copy will be written back')

    stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    backup = options.backup_dir / f'{options.domain}.{stamp}.plist'
    options.backup_dir.mkdir(parents=True, exist_ok=True)
    backup.write_bytes(plistlib.dumps(values))
    print(f'whole domain saved to {backup}')

    for _, key in present:
        subprocess.run(['defaults', 'delete', options.domain, key], check=False,
                       capture_output=True)
    print('reset done. Restore everything with:')
    print(f'  defaults import {options.domain} {backup}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
