#!/usr/bin/env python3
"""Check the Word merge script the report path actually runs (#157).

Three failures were measured against Word 16.112 with editing enabled:

* `set d to open path add to recent files false` assigns nothing — that Word
  returns no value for the command — so every later reference to `d` fails;
* the old error handler then read those same unassigned variables and raised
  `-2753 The variable templateDocument is not defined` of its own, replacing
  Word's error with a meaningless one;
* the template document was left open in Word when the script failed.

The script is extracted from `Reports.m` and compiled by `osacompile`, so a
syntax error or a renamed handler fails here rather than at report time. The
structural checks are the three points above, expressed against the script the
application ships.

Needs Xcode's `osacompile`; skips with exit 2 without it.
"""
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
if shutil.which('osacompile') is None:
    print('needs osacompile to check the report script', file=sys.stderr)
    raise SystemExit(2)

source = (root / 'Horos/Sources/Reports.m').read_bytes().decode('latin1')
start = source.index('- (BOOL)createNewWordReportForStudy:')
literal = source.index('NSString *source =', start)


def statement(text):
    """The concatenated @"..." literals up to the semicolon that ends them."""
    index, inString = 0, False
    while index < len(text):
        character = text[index]
        if inString:
            if character == '\\':
                index += 1
            elif character == '"':
                inString = False
        elif character == '"':
            inString = True
        elif character == ';':
            return text[:index]
        index += 1
    raise SystemExit('the Word script literal is not terminated in Reports.m')


pieces = re.findall(r'@"((?:[^"\\]|\\.)*)"', statement(source[literal:]))
script = ''.join(piece.encode().decode('unicode_escape') for piece in pieces)

failures = []


def require(condition, message):
    if not condition:
        failures.append(message)


# Word returns no value here; binding it hides every later error.
require(not re.search(r'set\s+\w+\s+to\s+open\s+\w*[Pp]ath', script),
        'the script binds the result of `open`, which Word does not return')
require('open templatePath add to recent files false' in script,
        'the script no longer opens the template without binding the result')

# The handler must not read a variable the failing statement may not have set.
handler = script[script.index('on error errorMessage number errorNumber'):]
handler = handler[:handler.index('end try')]
for name in ('templateDocument', 'mergedDocument'):
    require(name not in handler,
            'the error handler still reads `%s`, which the failing statement may not have assigned' % name)
require('error errorMessage number errorNumber' in handler,
        "the error handler no longer re-raises Word's own error")

# Whatever was opened has to be closed on both paths.
require(handler.count('closeReportDocument') >= 2,
        'the error handler does not close both documents')
require('on closeReportDocument(theName)' in script,
        'the close helper is missing')
require('if theName is missing value then return' in script,
        'the close helper does not tolerate a document that was never opened')

# Word rejects `active document` and `document 1` as command targets; commands
# go to the loop variable of `every document`.
for command in ('save as d ', 'close d saving no'):
    require(command in script, 'no command is sent to a document from `every document`: %r' % command)
require('save as mergedDocument' not in script and 'close mergedDocument' not in script,
        'a command is still sent to a stored `active document` reference')

with tempfile.TemporaryDirectory(prefix='horos-word-merge-script-') as name:
    directory = Path(name)
    (directory / 'merge.applescript').write_text(script)
    compiled = subprocess.run(['osacompile', '-o', str(directory / 'merge.scpt'),
                               str(directory / 'merge.applescript')],
                              capture_output=True, text=True)
    if compiled.returncode != 0:
        failures.append('the script does not compile: %s'
                        % (compiled.stderr or compiled.stdout).strip().splitlines()[-1:])

if failures:
    for failure in failures:
        print('FAIL: %s' % failure, file=sys.stderr)
    raise SystemExit(1)
print('PASS: the Word merge script compiles, does not bind `open`, keeps Word\'s own error '
      'and closes what it opened on both paths')
