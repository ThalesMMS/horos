#!/usr/bin/env python3
"""Exercise the real sender negotiation with SEG, duplicates and full budgets."""
import os
import subprocess
import tempfile
from pathlib import Path
from dcmtk_build import ROOT, dcmtk_flags

source = Path(os.environ.get('HOROS_STORE_NEGOTIATION_SOURCE', ROOT / 'Horos/Sources/DCMTKStoreSCU.mm')).read_text(encoding='latin1')
start = source.index('static OFBool\nisaListMember(')
end = source.index('//static int', start)
actual = source[start:end]
code = r'''
#include <dcmtk/config/osconfig.h>
#include <dcmtk/dcmnet/assoc.h>
#include <dcmtk/dcmdata/dcuid.h>
#include <dcmtk/dcmdata/dcxfer.h>
#include <dcmtk/ofstd/oflist.h>
#include <cassert>
#include <cstdio>
struct StoreSendContext {
 E_TransferSyntax opt_networkTransferSyntax = EXS_LittleEndianExplicit;
 OFBool opt_proposeOnlyRequiredPresentationContexts = OFFalse;
 OFBool opt_combineProposedTransferSyntaxes = OFFalse;
};
void errmsg(const char *message) {fprintf(stderr,"%s\n",message);}
ACTUAL
void check(size_t required, E_TransferSyntax syntax, bool combine) {
 T_ASC_Parameters*params=NULL;assert(ASC_createAssociationParameters(&params,ASC_DEFAULTMAXPDU).good());
 StoreSendContext context;context.opt_networkTransferSyntax=syntax;context.opt_combineProposedTransferSyntaxes=combine;
 OFList<OFString>classes;
 classes.push_back(UID_SegmentationStorage);classes.push_back(UID_SegmentationStorage);
 for(size_t i=1;i<required;i++)classes.push_back("1.2.826.0.1.3680043.8.498.371."+std::to_string(i));
 const OFList<OFString> original=classes;
 OFCondition result=addStoragePresentationContexts(context,params,classes);
 assert(classes==original); // negotiation must not pollute the required inventory
 if(required>128) {assert(result.bad());assert(ASC_countPresentationContexts(params)==0);}
 else {
  assert(result.good());assert(ASC_countPresentationContexts(params)<=128);
  const int stride=(!combine&&required<=64&&syntax!=EXS_LittleEndianImplicit)?2:1;
  auto expected=original.begin();++expected; // skip the duplicate SEG
  for(size_t i=0;i<required;i++,++expected) {
   T_ASC_PresentationContext offered;assert(ASC_getPresentationContext(params,i*stride,&offered).good());
   assert(OFString(offered.abstractSyntax)==*expected);
   assert(offered.presentationContextID==i*stride*2+1);
   assert(offered.transferSyntaxCount>=1&&offered.transferSyntaxCount<=3);
   if(required>64&&syntax!=EXS_LittleEndianImplicit)assert(offered.transferSyntaxCount==3);
  }
 }
 ASC_destroyAssociationParameters(&params);
}
int main(){for(size_t n:{1,64,65,128,129})for(bool combined:{false,true}){
 check(n,EXS_LittleEndianExplicit,combined);check(n,EXS_LittleEndianImplicit,combined);
}puts("PASS: selected SEG first, no duplicates, optional classes fit, 65/128 classes combine, 129 fail before association");}
'''.replace('ACTUAL', actual)
with tempfile.TemporaryDirectory(prefix='horos-store-negotiation-') as temporary:
    directory = Path(temporary)
    (directory / 'main.cc').write_text(code)
    subprocess.run(['xcrun', 'clang++', '-std=c++11', str(directory / 'main.cc'),
                    *dcmtk_flags('dcmnet'), '-o', str(directory / 'check')], check=True)
    subprocess.run([str(directory / 'check')], check=True)
preflight = source[source.index('/* finally parse filenames */'):] if '/* finally parse filenames */' in source else source[source.index('// Keep every selected path'):]
preflight = preflight[:preflight.index('#ifdef ON_THE_FLY_COMPRESSION')]
assert 'opt_proposeOnlyRequiredPresentationContexts' not in preflight
assert preflight.index('fileNameList.push_back') < preflight.index('HorosFindSOPClassAndInstanceInFile')
print('PASS: all input paths reach individual reporting; all valid selected storage classes enter negotiation')

initializer = source[source.index('- (id) initWithCallingAET:'):source.index('- (void)dealloc')]
assert 'fileExistsAtPath:' not in initializer and 'removeObjectsInArray:' not in initializer
