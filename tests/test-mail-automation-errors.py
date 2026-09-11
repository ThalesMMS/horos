#!/usr/bin/env python3
"""Run the actual AppleScript handler error path and native error formatter locally."""
from pathlib import Path
import plistlib
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = root / 'Horos/Sources/NSAppleScript+HandlerCalls.m'
script = (root / 'Horos/Resources/Mail.applescript').read_text()
assert 'tell application "Finder"' not in script
assert 'return 0' in script
entitlements = plistlib.loads((root / 'Horos/Horos.entitlements').read_bytes())
assert entitlements['com.apple.security.automation.apple-events'] is True
info = plistlib.loads((root / 'Horos/Info.plist').read_bytes())
assert info['NSAppleEventsUsageDescription'].strip()
# Keep the real outer catch; replace the Mail interaction with a controlled denial.
assert ' send ' not in script.lower()
assert 'with timeout of 90 seconds' in script
start = script.index('with timeout of 90 seconds')
end = script.index('\ton error error_message number error_number')
denied = script[:start] + 'error "Synthetic denial" number -1743\n' + script[end:]
successful = script[:start] + 'set syntheticSuccess to true\n' + script[end:]
code = r'''
#import <Cocoa/Cocoa.h>
#import "NSAppleScript+HandlerCalls.h"
int main(int argc, char **argv) { @autoreleasepool {
    NSDictionary *error = nil;
    NSAppleScript *script = [[NSAppleScript alloc] initWithContentsOfURL:
        [NSURL fileURLWithPath:[NSString stringWithUTF8String:argv[1]]] error:&error];
    if (!script || error) return 1;
    NSAppleEventDescriptor *args = [NSAppleEventDescriptor listDescriptor];
    for (int i=1; i<=7; i++) [args insertDescriptor:[NSAppleEventDescriptor descriptorWithString:@""] atIndex:i];
    NSAppleEventDescriptor *result = [script callHandler:@"mail_images" withArguments:args errorInfo:&error];
    if ([error[NSAppleScriptErrorNumber] integerValue] != -1743) return 2;
    NSString *message = [NSAppleScript mailExportErrorMessage:error result:result];
    if (![message containsString:@"Automation"] || ![message containsString:@"denied"]) return 3;
    if ([NSAppleScript mailExportErrorMessage:nil result:[NSAppleEventDescriptor descriptorWithInt32:0]]) return 4;
    if (![NSAppleScript mailExportErrorMessage:nil result:nil]) return 5;
    message = [NSAppleScript mailExportErrorMessage:@{NSAppleScriptErrorNumber:@(-1708)} result:nil];
    if (![message containsString:@"-1708"] || ![message containsString:@"incomplete"]) return 6;
    message = [NSAppleScript mailExportErrorMessage:@{NSAppleScriptErrorNumber:@(-1712)} result:nil];
    if (![message containsString:@"-1712"] || ![message containsString:@"Automation"] || ![message containsString:@"incomplete"]) return 10;
    message = [NSAppleScript mailExportErrorMessage:@{NSAppleScriptErrorNumber:@(-1744)} result:nil];
    if (![message containsString:@"Automation"] || ![message containsString:@"denied"]) return 11;
    message = [NSAppleScript mailExportErrorMessage:nil result:[NSAppleEventDescriptor descriptorWithInt32:-1743]];
    if (![message containsString:@"Automation"]) return 7;
    [script release];
    error = nil;
    script = [[NSAppleScript alloc] initWithContentsOfURL:
        [NSURL fileURLWithPath:[NSString stringWithUTF8String:argv[2]]] error:&error];
    if (!script || error) return 8;
    result = [script callHandler:@"mail_images" withArguments:args errorInfo:&error];
    if (!result || error || result.int32Value != 0) return 9;
    [script release];
    puts("PASS: real handler propagates denial; native message explains recovery; nil/error/success distinguished");
} }
'''
with tempfile.TemporaryDirectory(prefix='horos-mail-errors-') as d:
    p = Path(d)
    (p / 'denied.applescript').write_text(denied)
    (p / 'successful.applescript').write_text(successful)
    (p / 'main.m').write_text(code)
    subprocess.run(['osacompile', '-o', str(p / 'Mail.scpt'), str(root / 'Horos/Resources/Mail.applescript')], check=True)
    subprocess.run(['osacompile', '-o', str(p / 'denied.scpt'), str(p / 'denied.applescript')], check=True)
    subprocess.run(['osacompile', '-o', str(p / 'successful.scpt'), str(p / 'successful.applescript')], check=True)
    subprocess.run(['xcrun', 'clang', '-fsanitize=address', '-framework', 'Cocoa', '-I', str(source.parent), str(source), str(p / 'main.m'), '-o', str(p / 'test')], check=True)
    subprocess.run([str(p / 'test'), str(p / 'denied.scpt'), str(p / 'successful.scpt')], check=True)
