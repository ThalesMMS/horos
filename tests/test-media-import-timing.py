#!/usr/bin/env python3
"""Where an optical import spends its minutes, phase by phase.

The report is minutes per image, and a single elapsed time cannot say which part
of the import spent them. `-[DicomDatabase scanAtPath:isVolume:]` does five
separable things - lists what is on the medium, reads its DICOMDIR, opens every
file to find out whether it is DICOM, parses and indexes the ones that are, and
copies them into the database - and any of them can be the slow one, for
different reasons. It timed none of them, so a slow disc produced no evidence
beyond the user's stopwatch.

`HorosMediaScanTiming` times them apart and reports them together, longest
first, with the counts that make one disc comparable to another. Measured on a
200 MB image holding 200 CT instances of 512x512 in 5 series, once with a
DICOMDIR naming all of them and once with none at all - see the validation
document for the numbers.
"""
from pathlib import Path
import re
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
failures = []
timing = root / 'Horos/Sources/MediaScanTiming.swift'
scan = (root / 'Horos/Sources/DicomDatabase+Scan.mm').read_bytes().decode('latin1')
code = re.sub(r'//[^\n]*', '', scan)

DRIVER = '''
import Foundation

func emit(_ key: String, _ value: String) { print("\\(key)\\t\\(value)") }

// Nothing timed is not the same as everything taking no time.
emit("empty", MediaScanTiming(medium: "HOROSCD").summary)

let timing = MediaScanTiming(medium: "HOROSCD")
timing.begin("listing")
Thread.sleep(forTimeInterval: 0.30)
timing.end("listing", count: 17, noun: "file")

timing.begin("indexing")
Thread.sleep(forTimeInterval: 0.05)
timing.end("indexing", count: 1, noun: "file")

// A phase that never began - a disc with no DICOMDIR never reads one - must not
// be reported as having taken no time.
timing.end("reading the index for", count: 0, noun: "instance")

emit("summary", timing.summary)
emit("perInstance", timing.perInstance(4))
emit("perNothing", timing.perInstance(0))
emit("totalIsPositive", timing.total > 0.3 ? "yes" : "no")

// The formatter, at durations a test cannot afford to wait out.
emit("ms", MediaScanTiming.duration(0.0123))
emit("seconds", MediaScanTiming.duration(4.25))
emit("minutes", MediaScanTiming.duration(9 * 60 + 36))

// A phase whose work is not counted in anything still gets its time named.
let uncounted = MediaScanTiming(medium: "DISC")
uncounted.begin("waiting")
Thread.sleep(forTimeInterval: 0.02)
uncounted.end("waiting")
emit("uncounted", uncounted.summary)
'''

results = {}
if not timing.exists():
    failures.append('nothing times the phases of an import')
else:
    swiftc = subprocess.run(['xcrun', '--sdk', 'macosx', '-f', 'swiftc'], capture_output=True, text=True)
    if swiftc.returncode != 0:
        failures.append('no swiftc here: %s' % (swiftc.stderr or '').strip())
    else:
        with tempfile.TemporaryDirectory(prefix='horos-timing-') as directory:
            (Path(directory) / 'main.swift').write_text(DRIVER)
            binary = Path(directory) / 'timing'
            built = subprocess.run(['xcrun', '--sdk', 'macosx', 'swiftc', '-o', str(binary),
                                    str(timing), str(Path(directory) / 'main.swift')],
                                   capture_output=True, text=True)
            if built.returncode != 0:
                failures.append('the timing report does not compile:\n%s' % built.stderr[-1500:])
            else:
                run = subprocess.run([str(binary)], capture_output=True, text=True, timeout=120)
                if run.returncode != 0:
                    failures.append('the driver failed: %s' % run.stderr[-800:])
                for line in run.stdout.splitlines():
                    key, _, value = line.partition('\t')
                    results[key] = value

if results:
    if results.get('empty') != 'HOROSCD: nothing was timed':
        failures.append('a scan that timed nothing does not say so: %r' % results.get('empty'))

    summary = results.get('summary', '')
    if not summary.startswith('HOROSCD: '):
        failures.append('the summary does not name the medium: %r' % summary)
    if 'in all - ' not in summary:
        failures.append('the summary does not give a total: %r' % summary)
    if 'listing 17 files' not in summary:
        failures.append('a phase does not say what it worked on: %r' % summary)
    if 'indexing 1 file' not in summary:
        failures.append('a count of one is not written in the singular: %r' % summary)
    if summary.find('listing') > summary.find('indexing'):
        failures.append('the phases are not ordered longest first, so the summary does not '
                        'answer where the time went: %r' % summary)
    if 'reading the index' in summary:
        failures.append('a phase that never ran is reported as having taken no time: %r' % summary)

    if not results.get('perInstance', '').endswith('per instance'):
        failures.append('the cost of one instance is not reported: %r' % results.get('perInstance'))
    if results.get('perNothing') != '':
        failures.append('a rate per nothing is reported as a rate: %r' % results.get('perNothing'))
    if results.get('totalIsPositive') != 'yes':
        failures.append('the total does not add the phases up')

    if results.get('ms') != '12 ms':
        failures.append('a short phase is not reported in milliseconds: %r' % results.get('ms'))
    if results.get('seconds') != '4.2 s':
        failures.append('a phase of seconds is not reported in seconds: %r' % results.get('seconds'))
    if results.get('minutes') != '9 min 36 s':
        failures.append('the report of minutes per image cannot be written in minutes: %r'
                        % results.get('minutes'))
    if not re.match(r'^DISC: \d+ ms in all - \d+ ms waiting$', results.get('uncounted', '')):
        failures.append('a phase with nothing to count loses its time: %r' % results.get('uncounted'))

# --- and the scan uses it -----------------------------------------------------
if 'HorosMediaScanTiming' not in code:
    failures.append('the scan does not time its phases')
else:
    for phase in ('listing', 'reading the index for', 'reading', 'indexing', 'copying'):
        if '[timing begin: @"%s"]' % phase not in code:
            failures.append('the scan does not time %s' % phase)
        if '[timing end: @"%s"' % phase not in code:
            failures.append('the scan never stops timing %s' % phase)
    at = code.find('CDDVDEjectAfterAutoCopy')
    report = code.find('timing.summary')
    if at < 0 or report < 0 or report > at:
        failures.append('the report is not written before the medium is ejected')
    if code.count('timing.summary') < 2:
        failures.append('a medium that is browsed rather than copied is never reported on')

for failure in failures:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: an import says where its time went, phase by phase, longest first, before the medium '
      'is ejected')
