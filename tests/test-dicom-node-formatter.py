#!/usr/bin/env python3
"""Compile the real Locations formatter and validate addresses/ports/AE titles."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parents[1]
source=r'''
import Foundation
for port in [0, 1, 104, 65534, 65535, 65536, Int.max] {
 let other=DICOMNodeFormatter.alternativePort(to:port)
 assert((1...65535).contains(other) && other != port)
}
assert(DICOMNodeFormatter.alternativePort(to:65535)==65534)
for (field, valid, invalid) in [
 ("Port", ["1","104","65535"," 11112 "], ["0","65536","131072","-1","1.5","1e2","","abc"]),
 ("Address", ["127.0.0.1","localhost","pacs.example.org","::1","fe80::1%en0","pacs.example.org."], ["","http://host/path","host:104","999.1.1.1","a b","a..b","-bad","host/dir","::1%"]),
 ("AETitle", ["HOROS"," A B ","1234567890123456"], ["","12345678901234567","A\\B","é","A\nB"])
] {
 let formatter=DICOMNodeFormatter(field:field)
 for value in valid { assert(formatter.validationError(value)==nil, "valid \(field): \(value)") }
 for value in invalid { assert(formatter.validationError(value) != nil, "invalid \(field): \(value)") }
 var value:AnyObject?; var error:NSString?
 assert(!formatter.getObjectValue(&value,for:invalid[0],errorDescription:&error) && error != nil && value == nil)
 assert(formatter.getObjectValue(&value,for:valid[0],errorDescription:&error))
 assert(formatter.string(for:value)==valid[0])
}
print("ok: strict port range, host syntax, IPv6 scope and AE Title validation")
'''
with tempfile.TemporaryDirectory() as tmp:
 p=Path(tmp);(p/'main.swift').write_text(source)
 subprocess.run(['xcrun','swiftc',str(root/'Horos/Sources/DICOMNodeFormatter.swift'),str(p/'main.swift'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
