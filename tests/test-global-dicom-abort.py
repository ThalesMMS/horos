#!/usr/bin/env python3
"""Private cross-process abort signal and local cancellation regression."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parents[1]
code=r'''
#include "HorosDICOMGlobalAbort.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/wait.h>
int main(int argc,char**argv) {
 setenv("TMPDIR", argv[1], 1);
 int native=HorosDICOMAbortOpenDirectory();assert(native>=0 && HorosDICOMAbortPrivateDirectory(native));close(native);
 int d=open(argv[1],O_RDONLY|O_DIRECTORY);assert(d>=0);
 struct stat untouched;assert(fstatat(d,"horos-dicom-control",&untouched,0)!=0);
 assert(!HorosDICOMAbortRequestedInDirectory(d));
 assert(HorosDICOMAbortBeginInDirectory(d));
 assert(HorosDICOMAbortRequestedInDirectory(d));
 pid_t child=fork();assert(child>=0);
 if(!child)_exit(HorosDICOMAbortRequestedInDirectory(d)?0:1);
 int status;waitpid(child,&status,0);assert(WIFEXITED(status)&&WEXITSTATUS(status)==0);
 struct timespec times[2]={{time(NULL)-20,0},{time(NULL)-20,0}};
 assert(utimensat(d,"abort",times,0)==0);assert(!HorosDICOMAbortRequestedInDirectory(d));
 assert(HorosDICOMAbortBeginInDirectory(d));assert(HorosDICOMAbortRequestedInDirectory(d));
 HorosDICOMAbortEndInDirectory(d);assert(!HorosDICOMAbortRequestedInDirectory(d));
 assert(symlinkat("target",d,"abort")==0);assert(!HorosDICOMAbortBeginInDirectory(d));assert(!HorosDICOMAbortRequestedInDirectory(d));
 unlinkat(d,"abort",0);
 assert(mkfifoat(d,"abort",0600)==0);assert(!HorosDICOMAbortBeginInDirectory(d));assert(!HorosDICOMAbortRequestedInDirectory(d));unlinkat(d,"abort",0);
 assert(HorosDICOMAbortBeginInDirectory(d));assert(fchmodat(d,"abort",0666,0)==0);
 assert(!HorosDICOMAbortRequestedInDirectory(d));assert(!HorosDICOMAbortBeginInDirectory(d));unlinkat(d,"abort",0);
 assert(fchmod(d,0777)==0);assert(!HorosDICOMAbortBeginInDirectory(d));assert(fchmod(d,0700)==0);
 close(d);puts("ok: private signal, cross-process visibility, expiry, refresh, cleanup, symlink/FIFO/mode rejection");
}
'''
with tempfile.TemporaryDirectory(prefix='horos-abort-') as t:
 p=Path(t);(p/'main.c').write_text(code);d=p/'private';d.mkdir(mode=0o700)
 r=subprocess.run(['xcrun','clang','-I'+str(root/'Horos/Sources'),str(p/'main.c'),'-o',str(p/'probe')],capture_output=True,text=True)
 assert r.returncode==0,r.stderr
 r=subprocess.run([str(p/'probe'),str(d)],capture_output=True,text=True,timeout=10)
 assert r.returncode==0,r.stdout+r.stderr
 print(r.stdout,end='')
source=(root/'Horos/Sources/QueryController.mm').read_text(encoding='latin1')
body=source[source.index('- (void) performRetrieve:'):source.index('- (void) checkAndView:')]
assert 'kill_all_storescu' not in body and 'GlobalAbortBegin' not in body
assert 'if ([NSThread currentThread].isCancelled) break;' in body
print('ok: retrieve cancellation never broadcasts a global abort and skips queued nodes')
