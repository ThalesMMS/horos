#!/usr/bin/env python3
"""A C-STORE must not acknowledge a dataset with another SOP identity."""
import subprocess,tempfile
from pathlib import Path
root=Path(__file__).resolve().parents[1]
s=(root/'DCMTK/dcmqrdb/libsrc/dcmqrcbs.cc').read_text(encoding='latin1')
a=s.index('void DcmQueryRetrieveStoreContext::checkRequestAgainstDataset(');b=s.index('void DcmQueryRetrieveStoreContext::callbackHandler(',a)
method=s[a:b]
code=r'''
#include <cstring>
#include <cassert>
#include <cstdio>
#define DCMQRDB_ERROR(message) do {} while (0)
using OFBool=bool;using DIC_UI=char[65];
const int STATUS_Success=0,STATUS_STORE_Error_CannotUnderstand=0xc000,STATUS_STORE_Error_DataSetDoesNotMatchSOPClass=0xa900;
struct DcmDataset {const char *sopClass,*sopInstance;};
struct T_DIMSE_C_StoreRQ {const char *AffectedSOPClassUID,*AffectedSOPInstanceUID;};
struct T_DIMSE_C_StoreRSP {int DimseStatus=0;};
struct DcmFileFormat {DcmDataset data{"1.2.3","1.2.4"};void loadFile(const char*){} DcmDataset*getDataset(){return &data;}};
struct DcmQueryRetrieveOptions {static void errmsg(const char*,const char*){}};
bool DU_findSOPClassAndInstanceInDataSet(DcmDataset*d,char*c,size_t cs,char*i,size_t is,bool){
 if(!d->sopClass||!d->sopInstance)return false;
 snprintf(c,cs,"%s",d->sopClass);snprintf(i,is,"%s",d->sopInstance);return true;
}
struct DcmQueryRetrieveStoreContext {void checkRequestAgainstDataset(T_DIMSE_C_StoreRQ*,const char*,DcmDataset*,T_DIMSE_C_StoreRSP*,OFBool);};
METHOD
int main(){
 DcmQueryRetrieveStoreContext c;T_DIMSE_C_StoreRQ req{"1.2.3","1.2.4"};
 DcmDataset cases[]={{"1.2.3","1.2.4"},{"1.2.9","1.2.4"},{"1.2.3","1.2.9"},{nullptr,"1.2.4"},{"1.2.3",nullptr}};
 int expected[]={0,0xa900,0xa900,0xc000,0xc000};
 for(int n=0;n<5;n++){T_DIMSE_C_StoreRSP rsp;c.checkRequestAgainstDataset(&req,"fixture",&cases[n],&rsp,false);assert(rsp.DimseStatus==expected[n]);}
 puts("ok: matching identity accepted, divergent identities and missing identity rejected");
}
'''.replace('METHOD',method)
with tempfile.TemporaryDirectory(prefix='horos-store-identity-') as d:
 p=Path(d);(p/'main.cc').write_text(code)
 subprocess.run(['xcrun','clang++','-std=c++11',str(p/'main.cc'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
# The helper existed before but was disconnected: inspect the active callback too.
import re
callback=re.sub(r'/\*.*?\*/','',s[b:],flags=re.S)
assert callback.index('checkRequestAgainstDataset(req,') < callback.index('writeToFile(dcmff,')
