#!/usr/bin/env python3
"""PatientName resolves against the dictionary the application actually loads.

getDicomField: looks a keyword up in dcmDataDict. The table that object holds is
not the vendored DCMTK/dcmdata/data/dicom.dic and not the copy in the application
bundle: Horos and Decompress compile Binaries/dcmtk-source/dcmdata/dcdictbi.cc
(generated 2005-11-15). That table calls (0010,0010) PatientsName, so a lookup
of PatientName does not find the public tag.

Static inspection of the modern sources cannot catch this: they say PatientName.
This builds the same dictionary sources the application compiles, then runs the
same resolve path getDicomField: uses. It fails if PatientName is not (0010,0010).
"""
from pathlib import Path
from dcmtk_build import dcmtk_flags
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
dcmtk = root / 'DCMTK'
vendored = root / 'DCMTK/dcmdata/data/dicom.dic'
driver = root / 'tools/exercise-dicom-keyword-dictionary.mm'
implementation = root / 'Horos/Sources/DICOMDataDictionary.mm'
header = root / 'Horos/Sources/DICOMDataDictionary.h'
getter = root / 'Horos/Sources/DicomFileDCMTKCategory.mm'
failures = []

if not dcmtk.exists():
    print('skipped: needs the compiled-in DCMTK: %s' % dcmtk)
    sys.exit(2)
if not vendored.exists():
    print('skipped: needs the vendored dicom.dic: %s' % vendored)
    sys.exit(2)
for path in (driver, implementation, header):
    if not path.exists():
        failures.append('%s is gone' % path.name)

# The application path has to call the resolver. A source that only greps for
# PatientName would still compile if getDicomField: went back to findEntry alone.
source = getter.read_bytes().decode('latin1') if getter.exists() else ''
if 'HorosResolveDicomKeyword' not in source:
    failures.append('getDicomField:forFile: no longer asks HorosResolveDicomKeyword, so a '
                    'modern name can miss the tag again')

if driver.exists() and implementation.exists() and header.exists():
    with tempfile.TemporaryDirectory(prefix='horos-dicom-keyword-') as directory:
        binary = Path(directory) / 'keywords'
        build = subprocess.run(
            ['xcrun', 'clang++', '-std=c++11', '-fobjc-arc', str(driver), str(implementation), *dcmtk_flags(), '-framework', 'Foundation', '-o', str(binary)],
            capture_output=True, text=True)
        if build.returncode != 0:
            failures.append('the dictionary helper does not compile:\n%s' % build.stderr[-2000:])
        else:
            run = subprocess.run([str(binary), str(vendored)],
                                 capture_output=True, text=True, timeout=120)
            out = run.stdout
            print(out.strip())
            if run.stderr.strip():
                print(run.stderr.strip())
            if run.returncode == 2:
                print('skipped: %s' % run.stderr.strip())
                sys.exit(2)
            answers = {}
            for line in out.splitlines():
                if '=' in line:
                    key, value = line.split('=', 1)
                    answers[key.strip()] = value.strip()

            # What the process compiles, before any overlay. This is the
            # measurement the issue asked for: not an assumption from the
            # vendored tree.
            if answers.get('builtin DCMTK') != '3.7.0+':
                failures.append('the driver did not link the pinned current dictionary')
            if answers.get('builtin DCMDICTPATH') != '(unset)':
                failures.append('DCMDICTPATH is set in this process; the measurement would not '
                                'be the compiled-in table')
            if not answers.get('builtin PatientName', '').startswith('0010,0010'):
                failures.append('the builtin dictionary lacks the standard PatientName keyword')
            builtin_tag = answers.get('builtin (0010,0010)', '')
            if not builtin_tag.startswith('PatientName'):
                failures.append('the builtin dictionary did not expose the current keyword')
            try:
                builtin_entries = int(builtin_tag.rsplit('entries=', 1)[-1])
            except ValueError:
                builtin_entries = 0
            if builtin_entries < 5000:
                failures.append('the active dictionary fell back to the historical table')

            # After the same overlay and spelling fallback the application uses.
            if answers.get('loaded (0010,0010)', '').split()[0] != 'PatientName':
                failures.append('after loading the vendored dicom.dic, (0010,0010) is %s, not PatientName'
                                % answers.get('loaded (0010,0010)'))
            for keyword, tag in (
                    ('PatientName', '0010,0010'),
                    ('PatientsName', '0010,0010'),
                    ('PatientBirthDate', '0010,0030'),
                    ('PatientsBirthDate', '0010,0030'),
                    ('PatientSex', '0010,0040'),
                    ('PatientsSex', '0010,0040'),
                    ('ReferringPhysicianName', '0008,0090'),
                    ('ReferringPhysiciansName', '0008,0090'),
                    ('PatientID', '0010,0020')):
                got = answers.get('resolve %s' % keyword)
                if got != tag:
                    failures.append('%s resolved to %s, not %s' % (keyword, got, tag))
            if run.returncode != 0:
                failures.append('the helper exited %d' % run.returncode)

# The Swift spelling rule is what Horos itself calls. The helper above uses the
# Objective-C copy so Decompress, which has no Swift, stays able to resolve.
swiftc = subprocess.run(['xcrun', '--sdk', 'macosx', '-f', 'swiftc'], capture_output=True, text=True)
if swiftc.returncode != 0:
    failures.append('swiftc is not available')
else:
    main = r'''import Foundation
precondition(DICOMKeyword.otherSpelling(for: "PatientName") == "PatientsName")
precondition(DICOMKeyword.otherSpelling(for: "PatientsName") == "PatientName")
precondition(DICOMKeyword.spellingsToTry(for: "PatientName") == ["PatientName", "PatientsName"])
precondition(DICOMKeyword.spellingsToTry(for: "PatientsName") == ["PatientsName", "PatientName"])
precondition(DICOMKeyword.spellingsToTry(for: "StudyDescription") == ["StudyDescription"])
print("PASS: both spellings of a renamed keyword")
'''
    with tempfile.TemporaryDirectory(prefix='horos-dicom-spelling-') as directory:
        path = Path(directory)
        (path / 'main.swift').write_text(main)
        built = subprocess.run(
            ['xcrun', '--sdk', 'macosx', 'swiftc', '-o', str(path / 'test'),
             str(root / 'Horos/Sources/DICOMKeyword.swift'), str(path / 'main.swift')],
            capture_output=True, text=True)
        if built.returncode != 0:
            failures.append('DICOMKeyword.swift did not compile:\n%s' % built.stderr[-1500:])
        else:
            checks = subprocess.run([str(path / 'test')], capture_output=True, text=True)
            print(checks.stdout.strip())
            if checks.returncode != 0:
                failures.append('the spelling rule failed: %s' % (checks.stderr or checks.stdout)[-500:])

for failure in failures:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: PatientName and PatientsName both resolve to (0010,0010) against the '
      'dictionary the application compiles')
