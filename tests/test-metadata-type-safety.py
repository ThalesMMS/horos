#!/usr/bin/env python3
"""Metadata under the wrong value representation was asked for a number.

A DICOM parser gives back a value whose class follows the value representation
the file declares. Asked through the framework the application uses, an object
whose window centre and width are stored as `OB` answers:

    control.dcm
      WindowCenter               NSTaggedPointerString  floatValue=yes
    window-as-bytes.dcm
      WindowCenter               NSConcreteMutableData  floatValue=NO
    geometry-as-bytes.dcm
      ImagePositionPatient       NSConcreteMutableData  floatValue=NO  array[0]=NSConcreteMutableData

`-[DCMPix loadDICOMDCMFramework]` and the three group loaders beneath it read
thirty attributes as `[[dcmObject attributeValueWithName:@"…"] floatValue]` and
eight more out of arrays. Sending `floatValue` to NSData is an unrecognised
selector: the process dies, and the log the reports carry - `initWithString:nil`,
NSMutableData receiving floatValue - names no attribute.

Every one of those reads now goes through a guard that answers only when the
value can answer for a number, and names the file and the attribute when it
cannot. The attribute is then treated as absent rather than as zero-by-accident.
"""
from pathlib import Path
import re
import sys

root = Path(__file__).resolve().parents[1]
failures = []
pix = (root / 'Horos/Sources/DCMPix.m').read_bytes().decode('latin1')
code = re.sub(r'//[^\n]*', '', pix)


def body(signature, source):
    at = source.find(signature)
    if at < 0:
        return ''
    opening = source.index('{', at)
    depth, index = 0, opening
    while index < len(source):
        if source[index] == '{':
            depth += 1
        elif source[index] == '}':
            depth -= 1
            if depth == 0:
                return source[opening:index + 1]
        index += 1
    return ''


# --- the guards exist and say what went wrong ---------------------------------
for name in ('horosNumberValue', 'horosNumberInArray'):
    guard = body('static %s' % name if name == 'horosNumberValue' else
                 'static double %s' % name, code)
    if not guard:
        guard = body(name + '(', code)
    if not guard:
        failures.append('%s is gone, so a value that is not a number is asked for one' % name)
        continue
    if 'respondsToSelector' not in guard:
        failures.append('%s does not ask whether the value can answer for a number' % name)
    if 'NSStringFromClass' not in guard or 'NSLog' not in guard:
        failures.append('%s does not name what the value actually is' % name)

# --- and nothing reads a number around them -----------------------------------
direct = re.findall(r'\[\[dcmObject attributeValueWithName:@"[A-Za-z0-9]+"\] '
                    r'(?:floatValue|intValue|doubleValue|longValue|integerValue|longLongValue)\]',
                    code)
if direct:
    failures.append('%d attribute(s) are still asked for a number without a guard, starting with '
                    '%s' % (len(direct), direct[0]))

# The three group loaders are where the geometry comes from.
for signature, attributes in (
        ('- (void) dcmFrameworkLoad0x0020:', ('ImagePositionPatient', 'ImageOrientationPatient')),
        ('- (void) dcmFrameworkLoad0x0028:', ('PixelSpacing',))):
    loader = body(signature, code)
    if not loader:
        failures.append('%s is gone' % signature)
        continue
    if 'horosNumberInArray' not in loader:
        failures.append('%s still reads its arrays without a guard' % signature)
    for attribute in attributes:
        if attribute not in loader:
            failures.append('%s no longer reads %s' % (signature, attribute))
    for unguarded in re.findall(r'\[\[(?:ipp|ipv|iop|iov|pixelSpacing) objectAtIndex:[^\]]*\] '
                                r'doubleValue\]', loader):
        failures.append('%s still reads %s without a guard' % (signature, unguarded))

for failure in failures:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: a metadata value is asked for a number only when it can answer for one, and is named '
      'when it cannot')
