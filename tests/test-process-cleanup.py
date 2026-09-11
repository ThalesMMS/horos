#!/usr/bin/env python3
"""Startup cleanup may only signal processes launched from our own bundle."""
from pathlib import Path
import subprocess, sys, tempfile

root = Path(__file__).resolve().parents[1]
path = 'Horos/Sources/AppController.m'
source = (subprocess.check_output(['git', 'show', sys.argv[1] + ':' + path])
          if len(sys.argv) > 1 else (root / path).read_bytes()).decode('latin1')

start = source.index('bool HorosPathIsInsideBundle')
end = source.index('int GetAllPIDsForProcessName')
decision = source[start:end]
# The enumeration itself, to check its retry is bounded.
enum_start = source.index('int GetAllPIDsForProcessName')
enum_end = source.index('\n}\n', source.index('kCouldNotFindRequestedProcess', enum_start)) + 3
enumeration = source[enum_start:enum_end]
# The result codes the extracted function returns.
codes_start = source.index('enum\t{kSuccess = 0,')
codes = source[codes_start:source.index('};', codes_start) + 2]

code = r'''
#import <Foundation/Foundation.h>
#include <libproc.h>
#include <sys/sysctl.h>
#include <signal.h>
#include <string.h>
#include <stdbool.h>

CODES

DECISION
ENUMERATION

#define check(...) do{if(!(__VA_ARGS__)){NSLog(@"FAIL: %s",#__VA_ARGS__);return 1;}}while(0)

int main(){@autoreleasepool{
 const char *bundle = "/Applications/Horos.app";

 // Inside the bundle.
 check(HorosPathIsInsideBundle("/Applications/Horos.app/Contents/MacOS/Horos", bundle));
 check(HorosPathIsInsideBundle("/Applications/Horos.app/Contents/Resources/Decompress", bundle));
 // A trailing slash names the same bundle.
 check(HorosPathIsInsideBundle("/Applications/Horos.app/Contents/MacOS/Horos", "/Applications/Horos.app/"));

 // A different bundle that merely starts with the same characters must not
 // match: this is the case a plain prefix test gets wrong.
 check(!HorosPathIsInsideBundle("/Applications/Horos.app.backup/Contents/MacOS/Horos", bundle));
 check(!HorosPathIsInsideBundle("/Applications/Horos.app2/Contents/MacOS/Horos", bundle));
 // Another copy of the same application elsewhere is still another copy.
 check(!HorosPathIsInsideBundle("/Users/someone/Horos.app/Contents/MacOS/Horos", bundle));
 // Unrelated processes of the same name.
 check(!HorosPathIsInsideBundle("/System/Library/CoreServices/CrashReporter", bundle));
 check(!HorosPathIsInsideBundle("/usr/bin/Horos", bundle));
 // The bundle path itself is not something inside it.
 check(!HorosPathIsInsideBundle(bundle, bundle));
 // Degenerate input answers no rather than crashing or matching.
 check(!HorosPathIsInsideBundle(NULL, bundle));
 check(!HorosPathIsInsideBundle("/Applications/Horos.app/Contents/MacOS/Horos", NULL));
 check(!HorosPathIsInsideBundle("", bundle));
 check(!HorosPathIsInsideBundle("/x", ""));

 // A live process outside our bundle is not ours; this process is inside
 // whatever directory it was built in, so it is ours relative to that.
 char self[PROC_PIDPATHINFO_MAXSIZE];
 check(proc_pidpath(getpid(), self, sizeof(self)) > 0);
 char *slash = strrchr(self, '/');
 check(slash != NULL);
 *slash = 0;
 check(HorosProcessIsOurs(getpid(), self));
 check(!HorosProcessIsOurs(getpid(), "/Applications/SomethingElse.app"));
 // launchd is not ours, and neither is a process identifier nobody holds.
 check(!HorosProcessIsOurs(1, self));
 check(!HorosProcessIsOurs(0x7FFFFFFF, self));

 // The enumeration answers, bounded, and reports its own process.
 pid_t pids[64];
 unsigned int matches = 0;
 int sysctlError = 0;
 char name[PROC_PIDPATHINFO_MAXSIZE];
 proc_name(getpid(), name, sizeof(name));
 int error = GetAllPIDsForProcessName(name, pids, 64, &matches, &sysctlError);
 check(error == 0 && matches >= 1);
 bool found = false;
 for (unsigned int i = 0; i < matches; i++) if (pids[i] == getpid()) found = true;
 check(found);

 // Invalid arguments are rejected rather than enumerated.
 check(GetAllPIDsForProcessName(NULL, pids, 64, &matches, NULL) == kInvalidArgumentsError);
 check(GetAllPIDsForProcessName(name, NULL, 64, &matches, NULL) == kInvalidArgumentsError);
 check(GetAllPIDsForProcessName(name, pids, 0, &matches, NULL) == kInvalidArgumentsError);
 check(GetAllPIDsForProcessName(name, pids, 64, NULL, NULL) == kInvalidArgumentsError);
 // A name nothing is running reports that, without touching the array.
 check(GetAllPIDsForProcessName("horos-no-such-process", pids, 64, &matches, NULL)
       == kCouldNotFindRequestedProcess);
 check(matches == 0);

 // The retry is bounded rather than open ended.
 check(strstr(ENUM_SOURCE, "RemainingAttempts") != NULL);

 NSLog(@"PASS: only executables inside the bundle are ours, a similarly named neighbouring bundle is not, live and dead process identifiers answer correctly, and the enumeration is bounded");
}}
'''.replace('CODES', codes).replace('DECISION', decision).replace('ENUMERATION', enumeration)

with tempfile.TemporaryDirectory(prefix='horos-process-cleanup-') as folder:
    p = Path(folder)
    (p / 'enum.h').write_text('static const char *ENUM_SOURCE = %s;\n' %
                              ('"' + enumeration.replace('\\', '\\\\').replace('"', '\\"')
                               .replace('\n', '\\n')[:60000] + '"'))
    (p / 'test.m').write_text('#include "enum.h"\n' + code)
    subprocess.run(['xcrun', 'clang', '-fno-objc-arc', '-fsanitize=address,undefined',
                    '-fno-sanitize-recover=all', '-framework', 'Foundation',
                    '-I', str(p), str(p / 'test.m'), '-o', str(p / 'test')], check=True)
    subprocess.run([str(p / 'test')], check=True)
