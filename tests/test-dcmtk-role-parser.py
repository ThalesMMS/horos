#!/usr/bin/env python3
"""ASan regression for the actual pinned upstream role parser compiled into Horos."""
from pathlib import Path
import subprocess, tempfile, sys
root=Path(__file__).resolve().parents[1]
path='DCMTK/dcmnet/libsrc/dulparse.cc'
s=(subprocess.check_output(['git','show',sys.argv[1]+':'+path]).decode() if len(sys.argv)>1 else (root/path).read_text())
a=s.index('static OFCondition\nparseSCUSCPRole',s.index('/* parseSCUSCPRole'))
b=s.index('\n/* parseExtNeg',a)
header=(root/'DCMTK/dcmnet/include/dcmtk/dcmnet/dulstruc.h').read_text()
end=header.index('}   PRV_SCUSCPROLE;')+len('}   PRV_SCUSCPROLE;')
struct=header[header.rfind('typedef struct {',0,end):end]
max_start=s.index('static OFCondition\nparseMaxPDU',s.index('/* parseMaxPDU'))
max_end=s.index('\n/* parseDummy',max_start)
struct_start=header.index('typedef struct dul_maxlength {')
struct_end=header.index('}   DUL_MAXLENGTH;')+len('}   DUL_MAXLENGTH;')
code=r'''
#include <cstring>
#include <vector>
#include <cassert>
#include <cstdio>
#define DICOM_UI_LENGTH 64
#define DCMNET_WARN(message) do {} while (0)
#define DCMNET_TRACE(message) do {} while (0)
#define EXTRACT_LONG_BIG(p,v) v=((unsigned int)(p)[0]<<24)|((unsigned int)(p)[1]<<16)|((unsigned int)(p)[2]<<8)|(p)[3]
#define EXTRACT_SHORT_BIG(p,v) v=((unsigned short)(p)[0]<<8)|(p)[1]
struct OFCondition { bool success; bool good()const{return success;} bool bad()const{return !success;} };
static const OFCondition EC_Normal={true};
static OFCondition makeLengthError(const char*,unsigned int,unsigned int=0,unsigned int=0){return {false};}
STRUCT
MAXSTRUCT
METHOD
MAXMETHOD
int main(){
 for(unsigned int n=0;n<=65535;n++) {
  unsigned char input[8]={0x51,0,(unsigned char)(n>>8),(unsigned char)n,0,0,0x40,0};
  DUL_MAXLENGTH maximum={}; unsigned long consumed=0;
  assert(parseMaxPDU(&maximum,input,&consumed,sizeof input).good()==(n<=4));
  if(n==4){assert(consumed==8);assert(maximum.maxLength==16384);}
 }
 for(unsigned int n=0;n<8;n++) {
  std::vector<unsigned char> input(n,0);
  DUL_MAXLENGTH maximum={};unsigned long consumed=0;
  assert(parseMaxPDU(&maximum,input.data(),&consumed,n).bad());
 }

 for(unsigned int n: {1u,63u,64u,256u,65u,65531u}) {
  std::vector<unsigned char> input(n+8, '1');
  input[0]=0x54; input[1]=0; input[2]=(n+4)>>8; input[3]=(n+4)&255;
  input[4]=n>>8;input[5]=n&255;input[n+6]=1;input[n+7]=0;
  PRV_SCUSCPROLE *role=new PRV_SCUSCPROLE{}; unsigned long consumed=0;
  auto result=parseSCUSCPRole(role,input.data(),&consumed,input.size());
  assert(result.good()); assert(strlen(role->SOPClassUID)<=64);
  if(n<=64){assert(strlen(role->SOPClassUID)==n); assert(role->SCURole==1 && role->SCPRole==0);assert(consumed==input.size());}
  delete role;
  for(unsigned int available=0;available<input.size();available++){
   std::vector<unsigned char> truncated(input.begin(),input.begin()+available);
   PRV_SCUSCPROLE shortRole={};
   assert(parseSCUSCPRole(&shortRole,truncated.data(),&consumed,available).bad());
  }
 }
 puts("PASS: upstream parser stays within buffers for oversized roles and truncated prefixes under ASan/UBSan; host policy rejects malformed negotiation before service work");
}
'''.replace('MAXSTRUCT',header[struct_start:struct_end]).replace('STRUCT',struct).replace('MAXMETHOD',s[max_start:max_end]).replace('METHOD',s[a:b])
with tempfile.TemporaryDirectory(prefix='horos-role-parser-') as folder:
 p=Path(folder);(p/'test.cc').write_text(code)
 subprocess.run(['xcrun','clang++','-std=c++11','-fsanitize=address,undefined',str(p/'test.cc'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)

# Strict protocol acceptance belongs to the application, not an upstream patch.
policy = root / 'Horos/Sources/HorosDIMSEAssociationPolicy.swift'
driver = r'''import Foundation
func word(_ n: Int) -> [UInt8] { [UInt8((n >> 8) & 255), UInt8(n & 255)] }
func item(_ kind: UInt8, _ value: [UInt8]) -> [UInt8] { [kind, 0] + word(value.count) + value }
func association(_ user: [UInt8]) -> [UInt8] {
    let body = Array(repeating: UInt8(0), count: 68) + item(0x50, user)
    return [1, 0, UInt8((body.count >> 24) & 255), UInt8((body.count >> 16) & 255)] + word(body.count) + body
}
@main struct Check {
 static func main() {
  for size in [0, 1, 63, 64, 65, 256, 65531] {
   let role = item(0x54, word(size) + Array(repeating: UInt8(49), count: size) + [1, 0])
   let data = association(role)
   precondition(DIMSEAssociationPolicy.isValid(data) == (size >= 1 && size <= 64))
   for count in 0..<data.count { precondition(!DIMSEAssociationPolicy.isValid(Array(data.prefix(count)))) }
  }
  for size in 0...65531 {
   let data = association(item(0x51, Array(repeating: UInt8(0), count: size)))
   precondition(DIMSEAssociationPolicy.isValid(data) == (size == 4))
  }
  for scu in 0...2 { for scp in 0...2 {
   precondition(DIMSEAssociationPolicy.isValid(association(item(0x54, word(5) + Array("1.2.3".utf8) + [UInt8(scu), UInt8(scp)]))) == (scu <= 1 && scp <= 1))
  }}
  for uid in [".1", "1.", "1..2", "1A2"] {
   precondition(!DIMSEAssociationPolicy.isValid(association(item(0x54, word(uid.utf8.count) + Array(uid.utf8) + [1, 0]))))
  }
  print("PASS: host rejects oversized roles, invalid role bits, all invalid maximum-PDU lengths and every truncated prefix")
 }
}
'''
with tempfile.TemporaryDirectory(prefix='horos-association-policy-') as folder:
 p=Path(folder);(p/'Check.swift').write_text(driver)
 subprocess.run(['xcrun','swiftc','-O','-parse-as-library',str(policy),str(p/'Check.swift'),'-o',str(p/'check')],check=True)
 subprocess.run([str(p/'check')],check=True)
