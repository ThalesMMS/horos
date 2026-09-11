#!/usr/bin/env python3
"""Exercise the production C-STORE publication hook against real filesystem errors."""
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
path = 'Horos/Sources/dcmqrdbq.mm'
source = (subprocess.check_output(['git', 'show', sys.argv[1] + ':' + path]).decode('latin1')
          if len(sys.argv) > 1 else (root / path).read_text(encoding='latin1'))
start = source.index('OFCondition DcmQueryRetrieveOsiriXDatabaseHandle::storeRequest(')
end = source.index('/* ========================= UTILS', start)
code = r'''
#import <Foundation/Foundation.h>
#include <cassert>
#include <cerrno>
#include <cstdio>
#include <cstring>
#include <string>
#include <sys/param.h>
#include <sys/stat.h>
#include <unistd.h>
using OFBool = bool;
const int STATUS_Success=0, STATUS_STORE_Refused_OutOfResources=0xA700, OFM_imagectn=1, OF_error=1;
struct OFCondition {int code;std::string text;bool good()const{return code==0;}};
const OFCondition EC_Normal{0,"Normal"};
OFCondition makeOFCondition(int,int,int,const char* text){return {1,text};}
struct DcmQueryRetrieveDatabaseStatus {int value=0;void setStatus(int v){value=v;}};
static std::string incoming;
@interface DicomDatabase : NSObject
+ (id)activeLocalDatabase;
- (const char*)incomingDirPathC;
@end
@implementation DicomDatabase
+ (id)activeLocalDatabase {static id db=[self new];return db;}
- (const char*)incomingDirPathC {return incoming.c_str();}
@end
struct DcmQueryRetrieveOsiriXDatabaseHandle {
 OFCondition storeRequest(const char*,const char*,const char*,DcmQueryRetrieveDatabaseStatus*,OFBool);
};
METHOD
static void writeFile(const char* path){FILE* f=fopen(path,"w");assert(f);fputs("synthetic payload",f);fclose(f);}
int main(int argc,char**argv){ @autoreleasepool {
 assert(argc==2);assert(chdir(argv[1])==0);assert(mkdir("incoming",0700)==0);
 incoming="incoming";DcmQueryRetrieveOsiriXDatabaseHandle db;DcmQueryRetrieveDatabaseStatus status;
 writeFile("received");
 assert(db.storeRequest("1","2","received",&status,true).good());
 assert(status.value==0);assert(access("received",F_OK)!=0);assert(access("incoming/received",F_OK)==0);
 for(int scenario=0;scenario<4;scenario++){
  writeFile("pending");
  incoming=scenario==0?"missing":scenario==1?"incoming":"blocked";
  if(scenario==1)assert(chmod("incoming",0500)==0);
  if(scenario==2)writeFile("blocked");
  if(scenario==3){unlink("blocked");assert(mkdir("blocked",0700)==0);assert(mkdir("blocked/pending",0700)==0);}
  auto result=db.storeRequest("1","2","pending",&status,true);
  assert(!result.good());assert(status.value==STATUS_STORE_Refused_OutOfResources);
  assert(result.text.find(incoming)!=std::string::npos);assert(result.text.find("errno")!=std::string::npos);
  assert(access("pending",F_OK)==0); // caller still owns cleanup after a failed publication
  assert(chmod("incoming",0700)==0);unlink("pending");
 }
 incoming="incoming";writeFile("retry");
 assert(db.storeRequest("1","2","retry",&status,true).good());assert(status.value==0);
 puts("PASS: publication precedes success; missing, read-only and conflicting destinations return refusal and preserve source; retry succeeds");
} }
'''.replace('METHOD', source[start:end])
with tempfile.TemporaryDirectory(prefix='horos-store-publication-') as folder:
    p = Path(folder)
    (p / 'test.mm').write_text(code)
    subprocess.run(['clang++', '-std=c++11', '-framework', 'Foundation', str(p / 'test.mm'), '-o', str(p / 'test')], check=True)
    subprocess.run([str(p / 'test'), str(p)], check=True)
