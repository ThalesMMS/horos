#!/usr/bin/env python3
"""The pin, build graph, application policies and catalog describe the same library."""
from pathlib import Path
import json
import re
import subprocess
import tempfile
from dcmtk_build import ROOT, INSTALL, dcmtk_flags

catalog = json.loads((ROOT / 'docs/dcmtk-dimse-catalog.json').read_text())
pin = (ROOT / 'Horos/Scripts/DCMTK/UPSTREAM_REVISION').read_text().strip()
assert re.fullmatch('[0-9a-f]{40}', pin)
assert subprocess.check_output(['git','-C',str(ROOT/'DCMTK'),'rev-parse','HEAD'],text=True).strip() == pin
assert not subprocess.check_output(['git','-C',str(ROOT/'DCMTK'),'status','--porcelain'],text=True).strip()
index = subprocess.check_output(['git','-C',str(ROOT),'ls-files','--stage','--','DCMTK'],text=True).split()
assert index[:2] == ['160000', pin]
for field in ('compiled_library','compiled_into_app','upstream_pin','bundled_tools'):
    assert catalog[field]['version']=='3.7.0+' and catalog[field]['revision']==pin, field
assert catalog['compiled_library']['upstream_unpatched']
assert catalog['compiled_library']['implementation_class_uid']=='1.2.276.0.7230010.3.0.3.7.0'
project=(ROOT/'Horos.xcodeproj/project.pbxproj').read_text()
assert 'Binaries/dcmtk-source' not in project
for name in ('HorosDIMSEPolicy.swift','HorosDIMSEAssociationPolicy.swift','HorosDIMSEGet.mm',
             'HorosDIMSEMove.mm','HorosQueryRetrieveServer.mm','dcmqrdbq.mm'):
    assert name+' in Sources' in project,name
assert '"-ldcmnet"' in project and '"-ldcmdata"' in project
assert '"-lhorosdcmjpls"' in project and '"-ldcmtkcharls"' not in project
listener=(ROOT/'Horos/Sources/DCMTKQueryRetrieveSCP.mm').read_text(encoding='latin1')
assert 'new HorosQueryRetrieveServer(' in listener
assert 'public DcmThreadSCP' in (ROOT/'Horos/Sources/HorosQueryRetrieveServer.mm').read_text()
script=(ROOT/'Horos/Scripts/DCMTK/CMake.sh').read_text()
for option in ('BUILD_SHARED_LIBS=OFF','CMAKE_CXX_STANDARD=11','DCMTK_DEFAULT_DICT=builtin',
               'DCMTK_WITH_OPENSSL=ON','DCMTK_MAX_SEQUENCE_NESTING=16','CMAKE_BUILD_TYPE='):
    assert option in script,option
for forbidden in ('git reset','git checkout','git apply'):
    assert forbidden not in script
assert 'git -C "$source_dir" status --porcelain' in script
assert 'ditto "$source_dir" "$compat_source_dir"' in script
patch=(ROOT/'Horos/Scripts/DCMTK/DCMTK-3.6.7-print-status.patch').read_text()
assert 'dcmpstat/apps/dcmprscu.cc' in patch and not re.search(r'dcmnet|dimget|dimstore|dcmqrdb',patch)
for name in ('DICOMwebClient.swift','DICOMwebCredentials.swift','DICOMwebMultipart.swift','DICOMwebNodeEditor.swift'):
    assert (ROOT/'Horos/Sources'/name).is_file()
assert set((27,170,175,180,191,195,196,201,202,351,355)) <= set(catalog['host_regressions'])
for name in catalog['suites_to_reuse_not_copy']:
    assert (ROOT/name).is_file(),name
assert catalog['native_gap'] is False or catalog['native_gap_reason']
assert catalog['intel_in_scope'] is False
assert 'identifier: "dcmtk"' in (ROOT/'Horos/Sources/LicenseAttribution.swift').read_text()
dcmtk_flags('dcmnet','dcmqrdb','dcmtls')
configuration=(INSTALL/'include/dcmtk/config/osconfig.h').read_text()
assert '#define PACKAGE_VERSION "3.7.0"' in configuration
assert '#define PACKAGE_VERSION_SUFFIX "+"' in configuration
print('PASS: clean upstream pin, installed library version, build graph and application-owned DIMSE policy agree')

with tempfile.TemporaryDirectory(prefix='horos-library-identity-') as temporary:
    directory = Path(temporary)
    (directory / 'main.cc').write_text('#include <dcmtk/dcmdata/dcuid.h>\n#include <cstdio>\nint main(){puts(OFFIS_IMPLEMENTATION_CLASS_UID);}')
    subprocess.run(['xcrun', 'clang++', '-std=c++11', str(directory/'main.cc'),
                    *dcmtk_flags('dcmnet'), '-o', str(directory/'check')], check=True)
    actual = subprocess.check_output([str(directory/'check')], text=True).strip()
    assert actual == catalog['compiled_library']['implementation_class_uid'], actual
    assert actual in (ROOT/'Horos/Sources/HorosDIMSEPolicy.swift').read_text()
print('PASS: catalog and Swift identity equal the installed upstream implementation UID')
