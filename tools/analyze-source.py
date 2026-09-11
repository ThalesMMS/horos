#!/usr/bin/env python3
"""Run the clang static analyzer over one source file, using the real build flags.

`xcodebuild analyze` rebuilds the vendored libraries and analyses every file,
which takes long enough that a single finding is expensive to confirm. The
compile command for a file already appears in the build log, so this replays it
with `--analyze` instead: seconds per file, with the same include paths,
defines, language dialect and warning flags the application is built with.

    python3 tools/analyze-source.py Horos/Sources/DCMPix.m

Pass `--log` to choose a build log, `--target` when a file is compiled by more
than one target, and `--checker` to restrict the output to one checker name.
"""
import argparse
import re
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Flags that carry a separate argument naming a build product; the analyzer
# writes no object, dependency file or index entry.
DROP_WITH_ARGUMENT = {'-o', '-index-unit-output-path', '-index-store-path',
                      '--serialize-diagnostics', '-MF', '-MT', '-MQ'}
DROP_ALONE = {'-c', '-MD', '-MMD'}


def buildLogs(chosen):
    if chosen:
        return [Path(chosen)]
    logs = sorted((ROOT / 'build/logs').glob('*.log'), key=lambda p: p.stat().st_mtime, reverse=True)
    if not logs:
        raise SystemExit('no build log in build/logs; build once so the compile commands are recorded')
    return logs


def compileCommand(source, logs, target):
    pattern = re.compile(r'^\s*(/\S*?clang[^\n]*?-c\s+\S*%s[^\n]*)$' % re.escape(source.name), re.M)
    for log in logs:
        text = log.read_text(errors='replace')
        found = [m.group(1) for m in pattern.finditer(text)
                 if str(source) in m.group(1) or source.name in m.group(1)]
        if target:
            found = [c for c in found if '/%s.build/' % target in c]
        if found:
            return log, found[0]
    raise SystemExit('no compile command for %s in %s' % (source, ', '.join(str(l) for l in logs)))


def analyzerCommand(line):
    words = shlex.split(line)
    kept, index = [], 0
    while index < len(words):
        word = words[index]
        if word in DROP_WITH_ARGUMENT:
            index += 2
            continue
        if word in DROP_ALONE or word.startswith('-fbuild-session'):
            index += 1
            continue
        kept.append(word)
        index += 1
    return kept + ['--analyze', '-Xclang', '-analyzer-output=text', '-o', '/dev/null']


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('source', help='source file, relative to the repository root')
    parser.add_argument('--log', help='build log to read the compile command from')
    parser.add_argument('--target', help='Xcode target, when several compile the file')
    parser.add_argument('--checker', help='only report findings from this checker')
    parser.add_argument('--notes', action='store_true', help='keep the analyzer path notes')
    arguments = parser.parse_args()

    source = Path(arguments.source)
    log, line = compileCommand(source, buildLogs(arguments.log), arguments.target)
    print('# flags from %s' % log, file=sys.stderr)
    result = subprocess.run(analyzerCommand(line), capture_output=True, text=True)
    if result.returncode != 0 and not result.stderr.strip():
        print(result.stdout, file=sys.stderr)
        raise SystemExit('analyzer failed with no output')
    wanted = []
    for entry in result.stderr.splitlines():
        isWarning = ': warning: ' in entry
        if not isWarning and not (arguments.notes and ': note: ' in entry):
            continue
        if arguments.checker and isWarning and arguments.checker not in entry:
            continue
        wanted.append(entry)
    for entry in wanted:
        print(entry)
    print('%d finding%s' % (len(wanted), '' if len(wanted) == 1 else 's'), file=sys.stderr)


if __name__ == '__main__':
    main()
