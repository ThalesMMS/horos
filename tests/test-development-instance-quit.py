#!/usr/bin/env python3
"""One development instance at a time, however it was launched.

`script/build_and_run.sh` quits the previous development instance before it
builds, so the isolated bundle and its private database have one process. It
found that process by comparing `ps -axo comm=` against the absolute path of the
development executable - and `ps` reports the executable as it was invoked, so an
instance started with a relative path (`build/Development/...`) never matched.
Two development instances then ran at once, each with its own toolbar panel,
thumbnail list and viewers tiled over the same screen. Whoever was looking saw
panels belonging to a window that had been closed in the other process, which is
what "the left sidebar disappeared" turned out to be.

The match has to accept the same bundle under any spelling, and still refuse the
installed application.
"""
from pathlib import Path
import re
import sys

root = Path(__file__).resolve().parents[1]
script = (root / 'script/build_and_run.sh').read_text()
failures = []

absolute = '/Users/someone/horos-workbench/build/Development/HorosDevelopment.app/Contents/MacOS/Horos'
spellings = {
    absolute: True,
    'build/Development/HorosDevelopment.app/Contents/MacOS/Horos': True,
    'HorosDevelopment.app/Contents/MacOS/Horos': True,
    '/Volumes/Other/checkout/build/Development/HorosDevelopment.app/Contents/MacOS/Horos': True,
    '/Applications/Horos.app/Contents/MacOS/Horos': False,
    '/Applications/OsiriX.app/Contents/MacOS/OsiriX': False,
    '/Applications/HorosDevelopmentTool.app/Contents/MacOS/Horos': False,
}

# The two places that identify the process: the quit before the build, and the
# --verify report afterwards. Both are exercised here against the same spellings.
matchers = re.findall(r"suffix='/'\.join\(sys\.argv\[1\]\.split\('/'\)\[-4:\]\)", script)
if len(matchers) != 2:
    failures.append('%d of the 2 process lookups derive the bundle suffix' % len(matchers))

namespace = {'sys': type('s', (), {'argv': [None, absolute]})}
exec("suffix='/'.join(sys.argv[1].split('/')[-4:])\n"
     "def matches(command):\n"
     "    return command==sys.argv[1] or command==suffix or command.endswith('/'+suffix)\n",
     namespace)
for command, expected in spellings.items():
    if namespace['matches'](command) != expected:
        failures.append('%s should%s be taken for this development bundle'
                        % (command, '' if expected else ' not'))

if 'parts[1]==sys.argv[1]:' in script:
    failures.append('a process lookup still compares only the absolute path, so an instance '
                    'launched by a relative path survives the quit')

for failure in failures:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: the development instance is recognised however it was launched, and the installed '
      'application still is not')
