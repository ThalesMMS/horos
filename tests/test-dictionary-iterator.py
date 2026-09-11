#!/usr/bin/env python3
"""Walking the DICOM data dictionary by name reaches the end.

`DcmHashDictIterator::stepUp` in the vendored DCMTK leaves `hindex` one past the
last bucket when the last bucket is exhausted, while `end()` is built with
`hindex == highestBucket`. The two are never equal, so a traversal that does not
find what it is looking for never terminates — and dereferencing the iterator in
that state walks off the end of the bucket.

That is what `DcmTag::findTagFromName` does for a name that is not in the
dictionary, and it is reachable: a C-FIND filter naming an attribute that does
not exist crashed the application with

    EXC_BAD_ACCESS (SIGSEGV) at 0x10
      DcmDictEntry::contains(char const*)
      DcmDataDictionary::findEntry(char const*)
      DcmTag::findTagFromName(char const*, DcmTag&)
      -[DCMTKQueryNode queryWithValues:dataset:]
      -[XMLRPCInterface Retrieve:error:]

reached over the XML-RPC interface. Upstream DCMTK returns from `stepUp` when it
is already at the highest bucket; that is what this checks, by building a small
dictionary and walking it.
"""
from pathlib import Path
from dcmtk_build import dcmtk_flags
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
failures = []
driver = root / 'tools/exercise-dictionary-iterator.cc'
source = root / 'DCMTK'

if not driver.exists():
    failures.append('the driver that walks the dictionary is gone')
elif not source.exists():
    failures.append('the vendored DCMTK is not here')
else:
    with tempfile.TemporaryDirectory(prefix='horos-dict-') as directory:
        binary = Path(directory) / 'dicts'
        build = subprocess.run(
            ['xcrun', 'clang++', '-std=c++11', str(driver), *dcmtk_flags(), '-o', str(binary)],
            capture_output=True, text=True)
        if build.returncode != 0:
            failures.append('the dictionary does not compile on its own:\n%s' % build.stderr[-1500:])
        else:
            try:
                run = subprocess.run([str(binary)], capture_output=True, text=True, timeout=60)
            except subprocess.TimeoutExpired:
                failures.append('walking the dictionary did not finish in 60 seconds')
                run = None
            if run is not None:
                out = run.stdout
                if run.returncode == 2 or 'DID NOT TERMINATE' in out:
                    failures.append('the traversal never reaches end(): a lookup for a name that '
                                    'is not in the dictionary spins for ever')
                elif run.returncode == 3 or 'NULL ENTRY' in out:
                    failures.append('the traversal hands out a null entry')
                elif run.returncode != 0:
                    failures.append('the driver failed (%d): %s' % (run.returncode, run.stderr[-500:]))
                else:
                    if 'entries=3 seen=3' not in out:
                        failures.append('the traversal did not visit every entry exactly once: %s'
                                        % out.strip().replace('\n', '; '))
                    if 'unknown-name matches=0' not in out:
                        failures.append('a name that is not in the dictionary matched something')
                    if 'nameless.contains=0' not in out:
                        failures.append('an entry with no name does not answer "no" to a name')

for failure in failures:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: the dictionary can be walked to its end, a name that is not in it matches nothing, and '
      'an entry without a name answers no')

application = (root / 'Horos/Sources/DICOMDataDictionary.mm').read_text()
assert 'HorosFindStandardDicomEntry(dictionary, name)' in application
assert 'dictionary.findEntry(name)' not in application
