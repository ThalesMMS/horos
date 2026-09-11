#!/usr/bin/env python3
"""DCM.framework names, aliases and plugin headers survive the DCMTK migration (#372).

Migrating parsing to DCMTK does not authorize deleting DCM.framework, PluginFilter
or the class names plugins already compile against. ystarrev's plugin-system
removal is out of scope. PatientsName and PatientName must resolve to the same
tag. A valid DICOM file whose decoder is missing is kept, not deleted.
"""
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
source = root / 'Horos/Sources/HorosDCMFacade.swift'
keyword = root / 'Horos/Sources/DICOMKeyword.swift'
alias_m = root / 'DCM Framework/DCMTagNameAlias.m'
alias_h = root / 'DCM Framework/DCMTagNameAlias.h'
tag_source = root / 'DCM Framework/DCMAttributeTag.m'
plugin = root / 'Horos/Sources/PluginFilter.h'
pbx = (root / 'Horos.xcodeproj/project.pbxproj').read_text(encoding='utf-8')
names = root / 'DCM Framework/nameDictionary.plist'
failures = []

if not source.is_file():
    print('FAIL: Horos/Sources/HorosDCMFacade.swift is missing')
    sys.exit(1)
if 'HorosDCMFacade.swift' not in pbx:
    failures.append('HorosDCMFacade.swift is not in the Xcode project')
if 'HorosDCMFacade.swift in Sources' not in pbx:
    failures.append('HorosDCMFacade.swift is not in a Sources build phase')
if 'DCMTagNameAlias.m in Sources' not in pbx:
    failures.append('DCMTagNameAlias.m is not in the DCM Framework target')
if 'Horos DCM Framework' not in pbx:
    failures.append('the Horos DCM Framework target is gone')
if (root / 'Scripts/test_plugin_cleanup.py').exists() or (root / 'tests/test_plugin_cleanup.py').exists():
    failures.append('ystarrev test_plugin_cleanup.py was copied; plugin removal is out of scope')

plugin_text = plugin.read_text(encoding='latin1') if plugin.is_file() else ''
for token in ('DCMPix.h', 'ViewerController.h', 'DCMView.h', 'ROI.h',
              'filterImage:', 'processFiles:', 'initPlugin', 'willUnload'):
    if token not in plugin_text:
        failures.append('PluginFilter.h no longer exposes %s' % token)

tag_m = tag_source.read_bytes().decode('latin1') if tag_source.is_file() else ''
if 'DCMTagNameOtherSpelling' not in tag_m:
    failures.append('DCMAttributeTag no longer tries the other 2011 spelling')
if 'initWithName:' not in tag_m:
    failures.append('DCMAttributeTag tagWithName: is gone')

driver = r'''
import Foundation

@main struct Check {
    static func main() {
        precondition(HorosDCMFacade.requiredFrameworkName == "DCM.framework")
        precondition(HorosDCMFacade.ystarrevPluginCleanupTestThatMustNotBeCopied == "test_plugin_cleanup.py")
        for name in ["PluginFilter", "DCMPix", "DCMView", "ROI", "ViewerController"] {
            precondition(HorosDCMFacade.requiredPluginTypes.contains(name))
            precondition(!HorosDCMFacade.mayRemovePluginFacingType(name))
        }

        precondition(HorosDCMFacade.dispositionForValidFileMissingDecoder() == "keep")
        precondition(HorosDCMFacade.characterSetDisposition() == "retainOriginal")
        precondition(!HorosDCMFacade.parserMigrationMayChangeCoreDataSchema())
        precondition(HorosDCMFacade.guessedPrivateCreator(forUnknownTag: "7053,1000") == nil)

        let dictionary = [
            "PatientsName": "0010,0010",
            "PatientsBirthDate": "0010,0030",
            "PatientsSex": "0010,0040",
            "ReferringPhysiciansName": "0008,0090",
            "PatientID": "0010,0020",
            "SOPInstanceUID": "0008,0018",
        ]
        precondition(HorosDCMFacade.tagString(forName: "PatientsName", in: dictionary) == "0010,0010")
        precondition(HorosDCMFacade.tagString(forName: "PatientName", in: dictionary) == "0010,0010")
        precondition(HorosDCMFacade.tagString(forName: "PatientsBirthDate", in: dictionary) == "0010,0030")
        precondition(HorosDCMFacade.tagString(forName: "PatientBirthDate", in: dictionary) == "0010,0030")
        precondition(HorosDCMFacade.tagString(forName: "PatientsSex", in: dictionary) == "0010,0040")
        precondition(HorosDCMFacade.tagString(forName: "PatientSex", in: dictionary) == "0010,0040")
        precondition(HorosDCMFacade.tagString(forName: "ReferringPhysiciansName", in: dictionary) == "0008,0090")
        precondition(HorosDCMFacade.tagString(forName: "ReferringPhysicianName", in: dictionary) == "0008,0090")
        precondition(HorosDCMFacade.tagString(forName: "PatientID", in: dictionary) == "0010,0020")
        precondition(HorosDCMFacade.tagString(forName: "SOPInstanceUID", in: dictionary) == "0008,0018")
        precondition(HorosDCMFacade.tagString(forName: "NotATag", in: dictionary) == nil)

        precondition(HorosDCMFacade.otherSpelling(for: "PatientName") == "PatientsName")
        precondition(HorosDCMFacade.otherSpelling(for: "PatientsName") == "PatientName")
        precondition(DICOMKeyword.otherSpelling(for: "PatientName") == HorosDCMFacade.otherSpelling(for: "PatientName"))

        print("PASS: plugin types stay, aliases match, missing decoder keeps the file")
    }
}
'''

objc_probe = r'''
#import <Foundation/Foundation.h>
#import "DCMTagNameAlias.h"
int main(int argc, const char **argv) {
    @autoreleasepool {
        NSCAssert([DCMTagNameOtherSpelling(@"PatientName") isEqual:@"PatientsName"], @"modern to legacy");
        NSCAssert([DCMTagNameOtherSpelling(@"PatientsName") isEqual:@"PatientName"], @"legacy to modern");
        NSCAssert([DCMTagNameOtherSpelling(@"ReferringPhysicianName") isEqual:@"ReferringPhysiciansName"], @"physician");
        NSCAssert([DCMTagNameOtherSpelling(@"ReferringPhysiciansName") isEqual:@"ReferringPhysicianName"], @"physicians");
        NSCAssert(DCMTagNameOtherSpelling(@"PatientID") == nil, @"PatientID has one spelling");
        NSCAssert(DCMTagNameOtherSpelling(@"SOPInstanceUID") == nil, @"UID has one spelling");
        NSDictionary *names = [NSDictionary dictionaryWithContentsOfFile:@(argv[1])];
        NSCAssert(names.count > 1000, @"name dictionary did not load");
        NSCAssert(names[@"PatientsName"] != nil, @"legacy PatientsName missing");
        NSCAssert(names[@"PatientName"] == nil, @"plist unexpectedly gained PatientName");
        NSString *legacy = names[@"PatientsName"];
        NSString *modernKey = DCMTagNameOtherSpelling(@"PatientName");
        NSCAssert([names[modernKey] isEqual:legacy], @"PatientName must resolve through the alias");
        puts("PASS: DCMAttributeTag alias matches the 2011 keyword rename");
    }
    return 0;
}
'''

if source.is_file() and keyword.is_file():
    with tempfile.TemporaryDirectory(prefix='horos-dcm-facade-') as folder:
        path = Path(folder)
        (path / 'check.swift').write_text(driver)
        built = subprocess.run(
            ['xcrun', 'swiftc', '-parse-as-library', str(source), str(keyword),
             str(path / 'check.swift'), '-o', str(path / 'check')],
            capture_output=True, text=True)
        if built.returncode != 0:
            failures.append('HorosDCMFacade does not compile:\n%s' % built.stderr[-2000:])
        else:
            run = subprocess.run([str(path / 'check')], capture_output=True, text=True, timeout=20)
            print(run.stdout.strip())
            if run.returncode != 0:
                failures.append('HorosDCMFacade failed:\n%s%s' % (run.stdout, run.stderr))

if alias_m.is_file() and alias_h.is_file() and names.is_file():
    with tempfile.TemporaryDirectory(prefix='horos-dcm-alias-') as folder:
        path = Path(folder)
        (path / 'probe.m').write_text(objc_probe)
        built = subprocess.run(
            ['xcrun', 'clang', '-fobjc-arc', '-framework', 'Foundation',
             '-I', str(root / 'DCM Framework'),
             str(alias_m), str(path / 'probe.m'), '-o', str(path / 'probe')],
            capture_output=True, text=True)
        if built.returncode != 0:
            failures.append('DCMTagNameOtherSpelling does not compile:\n%s' % built.stderr[-2000:])
        else:
            run = subprocess.run([str(path / 'probe'), str(names)],
                                 capture_output=True, text=True, timeout=20)
            print(run.stdout.strip())
            if run.returncode != 0:
                failures.append('alias probe failed:\n%s%s' % (run.stdout, run.stderr))

if failures:
    print('FAIL:')
    for item in failures:
        print(item)
    sys.exit(1)
print('ok: DCM facade keeps plugin names, 2011 aliases and undecodable files')
