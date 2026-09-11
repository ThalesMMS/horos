#!/usr/bin/env python3
"""#592: production Core Data attributes + N2XMLRPC round-trip via Python's client.

Compile the complete serializer and its real string/data/date dependencies, with
no framework or fixture prerequisites. Neither escaping nor parsing is mocked.
"""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile
import xmlrpc.client

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--attribute-source', type=Path,
                    default=ROOT / 'Horos/Sources/XMLRPCOwnedThreadRead.swift')
args = parser.parse_args()
VALUES = ['', 'plain', 'a <b> & c', '\'quoted\' "double"', 'é João Тест 🩻',
          'literal &amp; &lt; &#39; &quot;', '  leading\tand\ntrailing  ']
SHIM = '''#import "Shim.h"
#import "N2XMLRPC.h"
NSString *ProbeResponse(id value, NSUInteger options) {
    return [N2XMLRPC responseWithValue:value options:options];
}
NSString *ProbeRequest(NSString *method, NSArray *arguments) {
    return [N2XMLRPC requestWithMethodName:method arguments:arguments];
}
id ProbeParse(NSString *xml) {
    NSXMLDocument *document = [[[NSXMLDocument alloc] initWithXMLString:xml options:0 error:NULL] autorelease];
    NSXMLNode *value = [[document nodesForXPath:@"*/params/param/value" error:NULL] firstObject];
    return value ? [N2XMLRPC ParseElement:value] : nil;
}
'''
HEADER = '''#import <Foundation/Foundation.h>
#ifdef __cplusplus
extern "C" {
#endif
NSString *ProbeResponse(id value, NSUInteger options);
NSString *ProbeRequest(NSString *method, NSArray *arguments);
id ProbeParse(NSString *xml);
#ifdef __cplusplus
}
#endif
'''
DRIVER = r'''
import Foundation
import CoreData
let folder = URL(fileURLWithPath: CommandLine.arguments[1])
let values = try JSONSerialization.jsonObject(with: Data(contentsOf: folder.appendingPathComponent("values.json"))) as! [String]
let model = NSManagedObjectModel()
let entity = NSEntityDescription()
entity.name = "Probe"
entity.managedObjectClassName = "NSManagedObject"
var attributes: [NSAttributeDescription] = values.indices.map {
    let attribute = NSAttributeDescription()
    attribute.name = "case\($0)"
    attribute.attributeType = .stringAttributeType
    return attribute
}
let thumbnail = NSAttributeDescription()
thumbnail.name = "thumbnail"
thumbnail.attributeType = .binaryDataAttributeType
attributes.append(thumbnail)
entity.properties = attributes
model.entities = [entity]
let coordinator = NSPersistentStoreCoordinator(managedObjectModel: model)
try coordinator.addPersistentStore(ofType: NSInMemoryStoreType, configurationName: nil, at: nil)
let context = NSManagedObjectContext(concurrencyType: .mainQueueConcurrencyType)
context.persistentStoreCoordinator = coordinator
let object = NSManagedObject(entity: entity, insertInto: context)
for (index, value) in values.enumerated() { object.setValue(value, forKey: "case\(index)") }
object.setValue(Data([1, 2, 3]), forKey: "thumbnail")
let attributesOnWire = XMLRPCOwnedThreadRead.dictionary(for: object)
precondition(attributesOnWire["thumbnail"] == nil)
let record: [String: Any] = ["record": attributesOnWire,
                           "nested<&": ["literal&key;": values],
                           "number": 7, "flag": true]
for option in 0...1 {
    let xml = ProbeResponse(record, UInt(option))!
    try xml.write(to: folder.appendingPathComponent("response\(option).xml"), atomically: true, encoding: .utf8)
    guard let decoded = ProbeParse(xml) as? [String: Any] else {
        fatalError("N2XMLRPC generated malformed XML for nested string keys")
    }
    try JSONSerialization.data(withJSONObject: decoded).write(to: folder.appendingPathComponent("native\(option).json"))
}
let request = ProbeRequest("literal<&method", [record])!
try request.write(to: folder.appendingPathComponent("request.xml"), atomically: true, encoding: .utf8)
let external = try String(contentsOf: folder.appendingPathComponent("external.xml"), encoding: .utf8)
let decoded = ProbeParse(external) as! [String: Any]
try JSONSerialization.data(withJSONObject: decoded).write(to: folder.appendingPathComponent("external.json"))
'''

with tempfile.TemporaryDirectory(prefix='horos-xmlrpc-roundtrip-') as temporary:
    work = Path(temporary)
    (work / 'Shim.h').write_text(HEADER)
    (work / 'Shim.mm').write_text(SHIM)
    (work / 'main.swift').write_text(DRIVER)
    (work / 'values.json').write_text(json.dumps(VALUES))
    expected = {'record': {f'case{i}': value for i, value in enumerate(VALUES)},
                'nested<&': {'literal&key;': VALUES}, 'number': 7, 'flag': True}
    (work / 'external.xml').write_text(xmlrpc.client.dumps((expected,), methodname='Probe', allow_none=True))
    sources = [ROOT / 'Nitrogen/Sources' / name for name in
               ('N2XMLRPC.mm', 'NSString+N2.mm', 'NSData+N2.mm',
                'NSMutableString+N2.mm', 'ISO8601DateFormatter.m')]
    sources.append(work / 'Shim.mm')
    objects = []
    for source in sources:
        output = work / (source.stem + '.o')
        subprocess.run(['xcrun', 'clang++' if source.suffix == '.mm' else 'clang',
                        '-c', '-w', '-fno-objc-arc', '-I' + str(ROOT / 'Nitrogen/Sources'),
                        str(source), '-o', str(output)], check=True)
        objects.append(str(output))
    subprocess.run(['xcrun', 'swiftc', '-import-objc-header', str(work / 'Shim.h'),
                    str(args.attribute_source), str(work / 'main.swift'),
                    *objects, '-framework', 'Cocoa', '-lc++', '-o', str(work / 'probe')], check=True)
    subprocess.run([str(work / 'probe'), str(work)], check=True)
    for option in (0, 1):
        decoded, method = xmlrpc.client.loads((work / f'response{option}.xml').read_text())
        assert decoded == (expected,) and method is None, (option, decoded, expected)
        assert json.loads((work / f'native{option}.json').read_text()) == expected
    decoded, method = xmlrpc.client.loads((work / 'request.xml').read_text())
    assert decoded == (expected,) and method == 'literal<&method'
    assert json.loads((work / 'external.json').read_text()) == expected
print('PASS: real Core Data/N2XMLRPC/Python round-trip, typed/untyped strings, nested keys, '
      'literal entities, Unicode and controls; binary attributes excluded')
