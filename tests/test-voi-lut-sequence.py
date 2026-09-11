#!/usr/bin/env python3
"""The table an object carries instead of a window is read, and applied.

PS 3.3 C.11.2: when an object has a VOI LUT Sequence, that table is how its
values are meant to be shown and Window Center and Width are the alternative.
Horos read neither. Three things were in the way, and all three are checked
here: the name dictionary spelled the tag's name with its value representations
stuck on the end, so no lookup by name could find it; the preference that turns
the feature on switched itself off on the first image loaded, and wrote the
answer back into the defaults so the menu item could not turn it on again; and
nothing on the path that actually runs ever called the code that applies a table.
"""
from pathlib import Path
import plistlib
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]

# The tag's name, which is how every lookup in the framework reaches it.
names = plistlib.loads((root / 'DCM Framework/nameDictionary.plist').read_bytes())
assert names.get('LUTData') == '0028,3006', \
    'LUT Data cannot be looked up by name, so a VOI LUT is never read'
assert 'LUTDataUS/SS/OW' not in names, 'the name still carries its value representations'
tags = plistlib.loads((root / 'DCM Framework/tagDictionary.plist').read_bytes())
assert tags['0028,3006']['Description'] == 'LUTData'

pix = (root / 'Horos/Sources/DCMPix.m').read_bytes().decode('latin1')
assert 'VOILUT is not supported with DCMFramework' not in pix, \
    'the preference still turns itself off on the first image loaded'
assert 'setBool: NO forKey: @"UseVOILUT"' in pix, \
    'a corrupt table should still turn the feature off'
assert pix.count('setBool: NO forKey: @"UseVOILUT"') == 1, \
    'more than one place writes the preference away from what the user chose'
assert '[self applyVOILUTFrom: dcmObject to: (unsigned short*) oImage]' in pix, \
    'nothing applies the table on the path that runs'
assert 'if( slope != 1.0 || offset != 0.0)' in pix, \
    "the table is applied without checking that its input is the object's stored value"

# The preference ships as on; nothing should quietly disagree with that.
defaults = (root / 'Horos/Sources/DefaultsOsiriX.m').read_bytes().decode('latin1')
assert '[defaultValues setObject:@"1" forKey: @"UseVOILUT"];' in defaults

source = r'''
import Foundation

func table(_ values: [UInt16]) -> Data {
    var out = Data()
    for value in values { withUnsafeBytes(of: value.littleEndian) { out.append(contentsOf: $0) } }
    return out
}

// Sixteen bits per entry, written as OW, which is the common shape.
let ramp = (0..<4096).map { UInt16($0) }
let lut = VOILookupTable(descriptor: [4096, 0, 16] as [NSNumber],
                         data: table(ramp), signed: false)!
precondition(lut.entries == 4096 && lut.depth == 16 && lut.firstMapped == 0)
precondition(lut.smallest == 0 && lut.largest == 4095)
precondition(lut.table.count == 4096 * 4, "\(lut.table.count)")
lut.table.withUnsafeBytes { (raw: UnsafeRawBufferPointer) in
    let entries = raw.bindMemory(to: UInt32.self)
    precondition(entries[0] == 0 && entries[1] == 1 && entries[4095] == 4095)
}
// The window that shows the whole of what the table produces.
precondition(lut.windowCenter == 2047.5, "\(lut.windowCenter)")
precondition(lut.windowWidth == 4096, "\(lut.windowWidth)")

// A table that answers the same value for everything: a flat field, on purpose.
let flat = VOILookupTable(descriptor: [4096, 0, 16] as [NSNumber],
                          data: table([UInt16](repeating: 2048, count: 4096)), signed: false)!
precondition(flat.smallest == 2048 && flat.largest == 2048)
precondition(flat.windowWidth == 1, "\(flat.windowWidth)")

// Eight bits per entry written one to a byte, which is what OB gives.
let bytes = VOILookupTable(descriptor: [256, 0, 8] as [NSNumber],
                           data: Data((0..<256).map { UInt8($0) }), signed: false)!
precondition(bytes.entries == 256 && bytes.depth == 8 && bytes.largest == 255)

// Zero entries means 65536: the count is stored in sixteen bits and the largest
// table there is does not fit in them.
let full = VOILookupTable(descriptor: [0, 0, 16] as [NSNumber],
                          data: table([UInt16](repeating: 7, count: 65536)), signed: false)!
precondition(full.entries == 65536)

// The first mapped value is signed when the object's pixels are.
let below = VOILookupTable(descriptor: [16, 64512, 16] as [NSNumber],   // -1024
                           data: table([UInt16](repeating: 1, count: 16)), signed: true)!
precondition(below.firstMapped == -1024, "\(below.firstMapped)")
let above = VOILookupTable(descriptor: [16, 64512, 16] as [NSNumber],
                           data: table([UInt16](repeating: 1, count: 16)), signed: false)!
precondition(above.firstMapped == 64512)

// Values that came back as numbers rather than bytes.
let numbers = VOILookupTable(descriptor: [4, 0, 16] as [NSNumber],
                             data: [1, 2, 3, 4] as [NSNumber], signed: false)!
precondition(numbers.largest == 4)

// And everything that is not a table this can use.
precondition(VOILookupTable(descriptor: nil, data: table(ramp), signed: false) == nil)
precondition(VOILookupTable(descriptor: [4096, 0] as [NSNumber], data: table(ramp), signed: false) == nil)
precondition(VOILookupTable(descriptor: [4096, 0, 16] as [NSNumber], data: nil, signed: false) == nil)
precondition(VOILookupTable(descriptor: [4096, 0, 16] as [NSNumber],
                            data: table([1, 2, 3]), signed: false) == nil,
             "a table shorter than its descriptor says was accepted")
precondition(VOILookupTable(descriptor: [4096, 0, 4] as [NSNumber],
                            data: table(ramp), signed: false) == nil, "four bits per entry")
precondition(VOILookupTable(descriptor: [4096, 0, 32] as [NSNumber],
                            data: table(ramp), signed: false) == nil, "thirty-two bits per entry")
precondition(VOILookupTable(descriptor: [1, 0, 16] as [NSNumber],
                            data: table([1]), signed: false) == nil, "a table of one entry")

print("PASS: the table is read from bytes or numbers, at eight or sixteen bits, "
      + "with a signed first value, and its own window comes out of it")
'''
with tempfile.TemporaryDirectory(prefix='horos-voi-lut-') as tmp:
    p = Path(tmp)
    (p / 'main.swift').write_text(source)
    subprocess.run(['xcrun', 'swiftc', str(root / 'Horos/Sources/VOILookupTable.swift'),
                    str(p / 'main.swift'), '-o', str(p / 'test')], check=True)
    subprocess.run([str(p / 'test')], check=True)
