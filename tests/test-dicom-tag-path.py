#!/usr/bin/env python3
"""An element inside a sequence item is addressed by its whole path."""
from pathlib import Path
import re
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
main = r'''import Foundation

func path(_ text: String) -> DICOMTagPath? { return DICOMTagPath.path(with: text) }

// A top-level tag, which is what every caller but the metadata editor sends.
let plain = path("(0010,0010)")!
assert(plain.group == 0x0010 && plain.element == 0x0010)
assert(plain.steps.isEmpty && !plain.isNested)

// The address the editor writes for a row inside a sequence. Reading only its
// first tag gave (0054,0016) - the sequence itself - so the edit was applied to
// the wrong element, or to none.
let nested = path("(0054,0016)[0].(0018,1074)")!
assert(nested.group == 0x0018 && nested.element == 0x1074)
assert(nested.isNested && nested.steps.count == 1)
assert(nested.steps[0].group == 0x0054 && nested.steps[0].element == 0x0016)
assert(nested.steps[0].item == 0)

// A second item of the same sequence is a different address.
let second = path("(0054,0016)[1].(0018,1074)")!
assert(second.steps[0].item == 1)
assert(second != nested)
assert(second.group == nested.group && second.element == nested.element)

// Nesting goes as deep as the file does.
let deep = path("(0008,1111)[2].(0040,0275)[0].(0040,1001)")!
assert(deep.steps.count == 2)
assert(deep.steps[0].item == 2 && deep.steps[1].item == 0)
assert(deep.group == 0x0040 && deep.element == 0x1001)
assert(deep.description == "(0008,1111)[2].(0040,0275)[0].(0040,1001)")
assert(path(deep.description) == deep)

// Upper and lower case hexadecimal both appear in the editor's rows.
assert(path("(00FF,00ab)") == path("(00ff,00AB)"))
assert(path("(7fe0,0010)")!.group == 0x7fe0)

// Anything that is not an address is refused rather than reduced to a tag that
// means something else.
for text in ["", "   ", "0010,0010", "(0010,0010", "(0010)", "(00100010)",
             "(0010,0010)[0]",                  // an item is not an element
             "(0054,0016).(0018,1074)",         // which item?
             "(0054,0016)[].(0018,1074)",
             "(0054,0016)[-1].(0018,1074)",
             "(0054,0016)[x].(0018,1074)",
             "(0054,0016)[0].(0018,1074)[1]",
             "(054,0016)[0].(0018,1074)",       // three digits
             "(0054,0016)[0]..(0018,1074)",
             "(0054,00zz)[0].(0018,1074)"] {
    assert(path(text) == nil, "expected a refusal: \(text)")
}

// Whitespace around the address is not part of it.
assert(path("  (0054,0016)[0].(0018,1074)  ") == nested)

// A large item index is an address, not an overflow.
assert(path("(0054,0016)[4294967].(0018,1074)")!.steps[0].item == 4294967)

print("PASS: top-level tags, one and two levels of nesting, case, refusals and round trip")
'''

# The writer has to receive the path, and the editor has to send it.
writer = (root / 'Horos/Sources/XMLControllerDCMTKCategory.mm').read_bytes().decode('latin1')
assert 'HorosTagPathStep' in writer, 'the edit has no room for a path'
assert 'std::vector<HorosTagPathStep> path;' in writer
start = writer.index('static bool HorosWriteInDataSet')
body = writer[start:writer.index('\n}\n', start)]
assert 'GetValueAsSQ' in body and 'GetNestedDataSet' in body, (
    'the nested write does not descend into the sequence')
assert 'step.item + 1' in body, 'gdcm numbers items from one'
assert 'dataset.Replace( sequenceElement)' in body, (
    'the sequence is not written back, so the change may not reach the file')

dispatch = writer[writer.index('for( std::vector<HorosTagEdit>::const_iterator'):]
assert 'it2->path.empty() == false' in dispatch[:1200], (
    'a nested edit still goes to gdcm::Anonymizer, which addresses the top level')

editor = (root / 'Horos/Sources/XMLController.m').read_bytes().decode('latin1')

# The address the parser has to read is the one -getPath: writes: components of
# (group,element) from the XML attributes, an item index in brackets, joined
# with a period.
path_start = editor.index('- (NSString*) getPath:')
path_body = editor[path_start:editor.index('\n}', path_start)]
assert '@"(%@,%@)"' in path_body, 'the row address is no longer built as (group,element)'
assert '@"[%d]"' in path_body, 'the item index is no longer built as [n]'
assert 'stringByAppendingString:@"."' in path_body, 'the components are no longer joined with a period'
# The attributes it reads are written as four lowercase hexadecimal digits.
attributes = (root / 'DCM Framework/DCMAttribute.m').read_bytes().decode('latin1')
assert '@"group" stringValue:[NSString stringWithFormat:@"%04x"' in attributes, (
    'the group attribute is no longer four hexadecimal digits')

apply_start = editor.index('for (int i = 0; i < [modifiedFields count]; i++)')
apply_body = editor[apply_start:editor.index('[XMLController modifyDicom:', apply_start)]
assert 'HorosDICOMTagPath pathWithString:' in apply_body, (
    'the editor still reduces the row address to its first tag')
assert re.search(r'tag = \[DCMAttributeTag tagWithTagString: field\]', apply_body), (
    'a plain tag must still be accepted')

with tempfile.TemporaryDirectory(prefix='horos-tag-path-') as tmp:
    p = Path(tmp)
    (p / 'main.swift').write_text(main)
    subprocess.run(['swiftc', str(root / 'Horos/Sources/DICOMTagPath.swift'),
                    str(p / 'main.swift'), '-o', str(p / 'test')], check=True)
    subprocess.run([str(p / 'test')], check=True)
