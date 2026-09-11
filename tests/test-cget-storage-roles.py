#!/usr/bin/env python3
"""Role selection is built per presentation context, and C-GET asks for SCP.

A C-GET carries its C-STORE sub-operations back over the same association, so the
requestor proposes the storage SOP classes with the SCP role; an SCP that sees no
role selection stores nothing and reports it. Horos asks for that role in
-addPresentationContext:abstractSyntax:.

constructSCUSCPRoles, in the DCMTK the project compiles from Binaries, built the
role selection sub-items with two flags declared once outside the loop and only
ever set. A context asking for SCU therefore left scuRole at 1 for every context
after it, so later SCP contexts went out as SCU/SCP - a different negotiation
from the one asked for, and one the standard gives a different meaning.

This compiles both the real requestor code and the real role construction, drives
the construction with contexts in orders that expose the carry-over, and checks
the encoded sub-items.
"""
from pathlib import Path
from dcmtk_build import dcmtk_flags
import re
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
dcmtk = root / 'DCMTK'
failures = []

# --- what Horos asks for -----------------------------------------------------
source = (root / 'Horos/Sources/DCMTKQueryNode.mm').read_bytes().decode('latin1')
SIGNATURE = ('- (OFCondition) addPresentationContext:(T_ASC_Parameters *)params '
             'abstractSyntax:(const char *)abstractSyntax\n{')
start = source.index(SIGNATURE)
requestor = source[start:source.index('\n- (void)setShowErrorMessage:', start)]
# The storage contexts of a C-GET, and only those, are proposed as Storage SCP.
storage = re.search(r'if\s*\(\s*strcmp\(abstractSyntax, UID_GET.*?\n\t\}', requestor, re.S)
if not storage:
    failures.append('the C-GET branch that adds the storage contexts is gone')
elif 'ASC_SC_ROLE_SCP' not in storage.group(0):
    failures.append('the C-GET storage contexts no longer ask for the Storage SCP role')
for model in ('UID_GETPatientRootQueryRetrieveInformationModel',
              'UID_GETStudyRootQueryRetrieveInformationModel',
              'UID_GETPatientStudyOnlyQueryRetrieveInformationModel'):
    if storage and model not in storage.group(0):
        failures.append('%s does not reach the storage contexts' % model)
if requestor.count('ASC_SC_ROLE_SCP') != 1:
    failures.append('the role is proposed %d times, expected once'
                    % requestor.count('ASC_SC_ROLE_SCP'))

# --- how DCMTK encodes it ----------------------------------------------------
construct = (dcmtk / 'dcmnet/libsrc/dulconst.cc').read_text()
begin = construct.index('constructSCUSCPRoles(unsigned char type,',
                        construct.index('/* constructSCUSCPRoles'))
roles_source = construct[begin:construct.index('\n/* constructExtNeg', begin)]
begin = construct.index('constructSCUSCPSubItem(char *name,',
                        construct.index('/* constructSCUSCPSubItem'))
subitem_source = construct[begin:construct.index('\n/* streamSubItem', begin)]

code = r'''
#include <dcmtk/config/osconfig.h>
#include <dcmtk/ofstd/ofstd.h>
#define DCMNET_WARN(message) do {} while (0)
#include <dcmtk/dcmnet/lst.h>
#include <dcmtk/dcmnet/dul.h>
#include <dcmtk/dcmnet/dulstruc.h>
#include <cassert>
#include <cstdio>
#include <cstring>
#include <cstdlib>
static OFCondition constructSCUSCPSubItem(char *name, unsigned char type, unsigned char scuRole,
                       unsigned char scpRole, PRV_SCUSCPROLE * scuscpItem,
                       unsigned long *length);
static OFCondition
SUBITEM
static OFCondition
ROLES

// One presentation context per SOP class, in the order the caller added them.
struct Context { const char *uid; DUL_SC_ROLE role; };
static OFCondition build(const Context *contexts, int count, LST_HEAD **list, unsigned long *length){
 DUL_ASSOCIATESERVICEPARAMETERS params;
 memset(&params, 0, sizeof params);
 params.requestedPresentationContext = LST_Create();
 assert(params.requestedPresentationContext);
 for(int i=0;i<count;i++){
  DUL_PRESENTATIONCONTEXT *pc=(DUL_PRESENTATIONCONTEXT*)malloc(sizeof(DUL_PRESENTATIONCONTEXT));
  memset(pc,0,sizeof *pc);
  pc->presentationContextID=(unsigned char)(1+2*i);
  pc->proposedSCRole=contexts[i].role;
  pc->acceptedSCRole=contexts[i].role;
  strcpy(pc->abstractSyntax,contexts[i].uid);
  pc->proposedTransferSyntax=LST_Create();
  LST_Enqueue(&params.requestedPresentationContext,(LST_NODE*)pc);
 }
 *list=LST_Create();
 assert(*list);
 return constructSCUSCPRoles(DUL_TYPEASSOCIATERQ,&params,list,length);
}

static int failed=0;
static void check(const Context *contexts,int count,const char *what){
 LST_HEAD *list=NULL; unsigned long length=0;
 if(build(contexts,count,&list,&length).bad()){fprintf(stderr,"FAIL: %s: construction failed\n",what);failed=1;return;}
 int seen=0;
 PRV_SCUSCPROLE *item=(PRV_SCUSCPROLE*)LST_Head(&list);
 if(item) (void)LST_Position(&list,(LST_NODE*)item);
 while(item!=NULL){
  // The sub-items come out in the order the contexts went in, skipping the ones
  // that asked for no role at all.
  while(seen<count && contexts[seen].role==DUL_SC_ROLE_DEFAULT) seen++;
  if(seen>=count){fprintf(stderr,"FAIL: %s: more role items than contexts asked for one\n",what);failed=1;break;}
  const DUL_SC_ROLE wanted=contexts[seen].role;
  const unsigned char scu=(wanted==DUL_SC_ROLE_SCU||wanted==DUL_SC_ROLE_SCUSCP)?1:0;
  const unsigned char scp=(wanted==DUL_SC_ROLE_SCP||wanted==DUL_SC_ROLE_SCUSCP)?1:0;
  if(item->SCURole!=scu||item->SCPRole!=scp){
   fprintf(stderr,"FAIL: %s: %s went out as SCU=%d SCP=%d, expected SCU=%d SCP=%d\n",
           what,item->SOPClassUID,item->SCURole,item->SCPRole,scu,scp);failed=1;}
  if(strcmp(item->SOPClassUID,contexts[seen].uid)!=0){
   fprintf(stderr,"FAIL: %s: role item %d is for %s, expected %s\n",
           what,seen,item->SOPClassUID,contexts[seen].uid);failed=1;}
  if(item->type!=DUL_TYPESCUSCPROLE){fprintf(stderr,"FAIL: %s: sub-item type %d\n",what,item->type);failed=1;}
  if(item->length!=strlen(contexts[seen].uid)+4){
   fprintf(stderr,"FAIL: %s: sub-item length %d for a %zu character UID\n",
           what,item->length,strlen(contexts[seen].uid));failed=1;}
  seen++;
  item=(PRV_SCUSCPROLE*)LST_Next(&list);
 }
 while(seen<count && contexts[seen].role==DUL_SC_ROLE_DEFAULT) seen++;
 if(seen!=count){fprintf(stderr,"FAIL: %s: %d of %d contexts produced a role item\n",what,seen,count);failed=1;}
}

#define QR "1.2.840.10008.5.1.4.1.2.2.3"
#define CT "1.2.840.10008.5.1.4.1.1.2"
#define MR "1.2.840.10008.5.1.4.1.1.4"
#define US "1.2.840.10008.5.1.4.1.1.6.1"
#define USMF "1.2.840.10008.5.1.4.1.1.3.1"
int main(){
 // What a Horos C-GET builds: the query/retrieve context with no role, then
 // storage contexts as SCP.
 const Context cget[]={{QR,DUL_SC_ROLE_DEFAULT},{CT,DUL_SC_ROLE_SCP},{MR,DUL_SC_ROLE_SCP},
                       {US,DUL_SC_ROLE_SCP},{USMF,DUL_SC_ROLE_SCP}};
 check(cget,5,"a C-GET association");
 // An SCU context before SCP ones: scuRole used to stay 1 for all of them.
 const Context mixed[]={{CT,DUL_SC_ROLE_SCU},{MR,DUL_SC_ROLE_SCP},{US,DUL_SC_ROLE_SCP}};
 check(mixed,3,"SCU followed by SCP");
 // And the other way round, which used to leave scpRole at 1.
 const Context reverse[]={{CT,DUL_SC_ROLE_SCP},{MR,DUL_SC_ROLE_SCU},{US,DUL_SC_ROLE_SCU}};
 check(reverse,3,"SCP followed by SCU");
 // SCU/SCP sets both; nothing after it may inherit either.
 const Context both[]={{CT,DUL_SC_ROLE_SCUSCP},{MR,DUL_SC_ROLE_SCP},{US,DUL_SC_ROLE_SCU}};
 check(both,3,"SCU/SCP followed by single roles");
 // Contexts asking for no role produce no sub-item and disturb nothing.
 const Context sparse[]={{QR,DUL_SC_ROLE_DEFAULT},{CT,DUL_SC_ROLE_SCU},{MR,DUL_SC_ROLE_DEFAULT},
                         {US,DUL_SC_ROLE_SCP},{USMF,DUL_SC_ROLE_DEFAULT}};
 check(sparse,5,"roles separated by contexts without one");
 // No contexts at all is not an error.
 LST_HEAD *list=NULL; unsigned long length=1;
 const Context none[]={{QR,DUL_SC_ROLE_DEFAULT}};
 if(build(none,1,&list,&length).bad()||length!=0){fprintf(stderr,"FAIL: an association with no roles\n");failed=1;}
 if(failed) return 1;
 puts("PASS: role selection built per context across six orderings, including every "
      "combination that used to inherit a flag from the context before it");
 return 0;
}
'''.replace('SUBITEM', subitem_source).replace('ROLES', roles_source)

with tempfile.TemporaryDirectory(prefix='horos-cget-roles-') as directory:
    path = Path(directory)
    (path / 'test.cc').write_text(code)
    command = ['xcrun', 'clang++', '-std=c++14', '-fsanitize=address,undefined',
               '-fno-sanitize-recover=all',
               str(path / 'test.cc'), *dcmtk_flags('dcmnet'),
               '-o', str(path / 'test')]
    build = subprocess.run(command, capture_output=True, text=True)
    if build.returncode != 0:
        print(build.stderr[-3000:])
        failures.append('the role construction no longer compiles on its own')
    else:
        run = subprocess.run([str(path / 'test')], capture_output=True, text=True)
        print((run.stdout or run.stderr).strip())
        if run.returncode != 0:
            failures.append('role selection is not built per context')

        # A regression mutation removes the explicit reset added upstream.
        # It must fail the same cases, without depending on an old clone's history.
        before = roles_source.replace('                  scuRole = 0;', '').replace('                  scpRole = 0;', '')
        (path / 'before.cc').write_text(code.replace(roles_source, before))
        command[command.index(str(path / 'test.cc'))] = str(path / 'before.cc')
        command[-1] = str(path / 'before')
        mutation = subprocess.run(command, capture_output=True, text=True)
        if mutation.returncode != 0:
            failures.append('the flag carry-over mutation did not compile: ' + mutation.stderr[-700:])
        else:
            was = subprocess.run([str(path / 'before')], capture_output=True, text=True)
            if was.returncode == 0:
                failures.append('the role carry-over mutation escaped the regression test')

for failure in failures:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: the C-GET storage contexts ask for the Storage SCP role, and the role selection '
      'sub-items are built from each context alone')
