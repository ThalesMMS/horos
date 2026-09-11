#!/usr/bin/env python3
"""Execute the actual preference write blocks with process overrides and saved values."""
from pathlib import Path
import argparse
import re
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--baseline', help='read source from this Git revision')
args = parser.parse_args()


def source(path):
    if args.baseline:
        return subprocess.check_output(['git', 'show', f'{args.baseline}:{path}'],
                                       cwd=root).decode('latin1')
    return (root / path).read_bytes().decode('latin1')


app = source('Horos/Sources/AppController.m')
browser = source('Horos/Sources/BrowserController.m')
category = source('Horos/Sources/NSUserDefaults+OsiriX.mm')
helper = re.search(r'-\(BOOL\)hasArgumentOverrideForKey:.*?\n\}', category, re.S)
browser_scope = browser.split('- (void)waitForRunningProcesses', 1)[1]
browser_scope = browser_scope.split('// ----------', 2)[1]
abort = app.split('- (IBAction) killAllStoreSCU:', 1)[1].split('\n}', 1)[0]
abort_begin = abort[abort.index('\n\tBOOL '):].split('HorosDICOMGlobalAbortBegin();')[0]
abort_end = abort.split('HorosDICOMGlobalAbortEnd();')[1]
recovery_end = app.index('objectForKey: @"copyHideListenerError"]')
recovery_start = app.rfind('if(', 0, recovery_end)
recovery = app[recovery_start:app.index(';', recovery_end) + 1]

blocks = [browser_scope, abort_begin + abort_end, recovery]
functions = '\n'.join(
    f'static void writeBlock{index}(NSUserDefaults *defaults) {{\n'
    + block.replace('[NSUserDefaults standardUserDefaults]', 'defaults') + '\n}'
    for index, block in enumerate(blocks))

driver = r'''
#import <Foundation/Foundation.h>
@interface NSUserDefaults (Probe)
-(BOOL)hasArgumentOverrideForKey:(NSString*)key;
@end
@implementation NSUserDefaults (Probe)
HELPER
@end
FUNCTIONS
int main(void) { @autoreleasepool {
    NSString *domain = [@"org.horosproject.horos.test-server-mode-" stringByAppendingString:NSUUID.UUID.UUIDString];
    NSUserDefaults *defaults = [[NSUserDefaults alloc] initWithSuiteName:domain];
    [defaults registerDefaults:@{@"hideListenerError": @NO}];
    void (*writers[])(NSUserDefaults *) = {writeBlock0, writeBlock1, writeBlock2};
    int checks = 0;
    @try {
        for (int saved = -1; saved <= 1; saved++) {
            for (int argument = 0; argument <= 1; argument++) {
                for (int stale = 0; stale <= 1; stale++) {
                    NSMutableDictionary *original = [@{@"sentinel": @"preserved"} mutableCopy];
                    if (saved >= 0) original[@"hideListenerError"] = @(saved != 0);
                    if (stale) original[@"copyHideListenerError"] = @(argument == 0);
                    [defaults setVolatileDomain:@{@"hideListenerError": argument ? @"YES" : @"NO"}
                                       forName:NSArgumentDomain];
                    for (int block = 0; block < 3; block++) {
                        [defaults setPersistentDomain:original forName:domain];
                        // Repeated writes model startup, later abort and shutdown, with no timer.
                        writers[block](defaults);
                        writers[block](defaults);
                        if (![[defaults persistentDomainForName:domain] isEqual:original]) {
                            fprintf(stderr, "FAIL: block %d changed saved mode %d with argument %d and backup %d\n",
                                    block, saved, argument, stale);
                            return 1;
                        }
                        if ([defaults boolForKey:@"hideListenerError"] != (argument != 0)) return 1;
                        checks++;
                    }
                }
            }
        }
        // Without an override, preserve existing suppression and crash recovery.
        [defaults setVolatileDomain:@{} forName:NSArgumentDomain];
        for (int saved = 0; saved <= 1; saved++) {
            for (int block = 0; block < 3; block++) {
                [defaults setPersistentDomain:@{@"hideListenerError": @(saved != 0),
                    @"copyHideListenerError": @(saved == 0)} forName:domain];
                writers[block](defaults);
                BOOL expected = block == 2 ? saved == 0 : saved != 0;
                if ([defaults boolForKey:@"hideListenerError"] != expected) return 1;
                checks++;
            }
        }
        printf("PASS: %d native preference cases; all three host write paths preserve process overrides\n", checks);
    } @finally {
        [defaults removePersistentDomainForName:domain];
        [defaults synchronize];
    }
} }
'''.replace('HELPER', helper.group() if helper else '').replace('FUNCTIONS', functions)

with tempfile.TemporaryDirectory(prefix='horos-server-mode-') as directory:
    path = Path(directory)
    (path / 'probe.m').write_text(driver)
    subprocess.run(['xcrun', 'clang', '-fobjc-arc', '-framework', 'Foundation',
                    str(path / 'probe.m'), '-o', str(path / 'probe')], check=True)
    subprocess.run([str(path / 'probe')], check=True)

launcher = source('script/build_and_run.sh')
assert 'ARGS=(-hideListenerError NO ' in launcher, 'development must override saved server mode'
assert 'restore_development_server_mode' not in launcher, 'startup cannot depend on a timed restoration'
