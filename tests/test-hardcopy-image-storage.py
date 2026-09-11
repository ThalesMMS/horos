#!/usr/bin/env python3
"""Hardcopy objects are pictures: the browser must list them, empty or not.

A hardcopy grayscale instance sitting in a mammography study is the shape of the
crash report behind #106. It did not crash here — it disappeared: the SOP class
was not among the ones the application lists as images, so
-[DicomStudy imageSeries] left the series out of the browser entirely, while the
study still counted its modality. Neither a supported representation nor a
diagnosis reached the user.
"""
from pathlib import Path
import subprocess, sys, tempfile

root = Path(__file__).resolve().parents[1]
syntaxes = (root / 'DCM Framework/DCMAbstractSyntaxUID.m').read_bytes().decode('latin1')
for name, uid in (('HardcopyGrayscaleImageStorage', '1.2.840.10008.5.1.1.29'),
                  ('HardcopyColorImageStorage', '1.2.840.10008.5.1.1.30')):
    assert f'{name} = @"{uid}"' in syntaxes, f'{name} is not declared'
    assert syntaxes.count(f'{name},') >= 1, f'{name} is not in the image syntaxes'
# The listing decision reads that list, so keep the path intact.
study = (root / 'Horos/Sources/DicomStudy.m').read_bytes().decode('latin1')
assert 'isImageStorage: uid' in study, 'the browser no longer lists series by SOP class'

products = Path(sys.argv[1]) if len(sys.argv) > 1 else None
if not products or not (products / 'DCM.framework').exists():
    print('skipped: needs the built DCM framework: PRODUCTS_DIR')
    sys.exit(2)

program = r'''
#import <DCM/DCMAbstractSyntaxUID.h>
#import <Foundation/Foundation.h>
int main(void) { @autoreleasepool {
    struct { const char *uid; BOOL image; const char *what; } cases[] = {
        {"1.2.840.10008.5.1.1.29",        YES, "hardcopy grayscale"},
        {"1.2.840.10008.5.1.1.30",        YES, "hardcopy colour"},
        {"1.2.840.10008.5.1.4.1.1.1.2",   YES, "digital mammography"},
        {"1.3.12.2.1107.5.9.1",           NO,  "a private Siemens non-image class"},
        {"1.2.840.10008.5.1.1.9",         NO,  "the grayscale print management meta class"},
    };
    for (unsigned i = 0; i < sizeof(cases)/sizeof(*cases); i++) {
        NSString *uid = [NSString stringWithUTF8String: cases[i].uid];
        BOOL got = [DCMAbstractSyntaxUID isImageStorage: uid];
        if (got != cases[i].image) {
            fprintf(stderr, "FAIL: %s (%s) reported %s\n", cases[i].what, cases[i].uid,
                    got ? "image storage" : "not image storage");
            return 1;
        }
    }
    printf("PASS: both hardcopy classes are image storage, the print meta class and the private "
           "Siemens class are not\n");
    return 0;
}}
'''
with tempfile.TemporaryDirectory(prefix='horos-hardcopy-') as tmp:
    p = Path(tmp)
    (p / 'bin').mkdir()
    # The framework's install name is @executable_path/../Frameworks.
    (p / 'Frameworks').symlink_to(products.resolve())
    (p / 'main.m').write_text(program)
    subprocess.run(['xcrun', 'clang', '-fobjc-arc', '-w', str(p / 'main.m'),
                    '-F', str(products), '-framework', 'DCM', '-framework', 'Foundation',
                    '-o', str(p / 'bin/test')], check=True)
    done = subprocess.run([str(p / 'bin/test')], capture_output=True, text=True)
    print(done.stdout.strip() or done.stderr.strip())
    if done.returncode: sys.exit(1)
