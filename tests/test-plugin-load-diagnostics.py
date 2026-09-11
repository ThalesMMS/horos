#!/usr/bin/env python3
"""Exercise the production session outcome registry without loading user plugins."""
from pathlib import Path
import subprocess
import tempfile
root = Path(__file__).resolve().parent.parent
program = r'''
#import "HorosPluginLoadDiagnostics.h"
int main() { @autoreleasepool {
 NSString *first = @"/one/Synthetic.horosplugin", *other = @"/two/Synthetic.horosplugin";
 NSCAssert([HorosPluginLoadOutcome(first, YES)[@"loadState"] isEqual:@"Not loaded"], @"Installed is not loaded");
 HorosRecordPluginLoad(first, @"Loaded", @"Registered");
 HorosRecordPluginLoad(other, @"Incompatible", @"Wrong architecture");
 NSCAssert([HorosPluginLoadOutcome(first, YES)[@"loadState"] isEqual:@"Loaded"], @"Separate bundle paths");
 NSCAssert([HorosPluginLoadOutcome(other, YES)[@"loadReason"] isEqual:@"Wrong architecture"], @"Preserve reason");
 NSCAssert([HorosPluginLoadOutcome(first, NO)[@"loadState"] isEqual:@"Installed"], @"Disabled takes precedence");
 NSCAssert([HorosPluginLoadOutcome(first, NO)[@"loadReason"] containsString:@"restart"], @"Explain resident code");
 HorosRecordPluginLoad(first, @"Load failed", @"Initialization exception");
 NSCAssert([HorosPluginLoadOutcome(first, YES)[@"loadState"] isEqual:@"Load failed"], @"Failure replaces previous outcome");
 puts("PASS: unknown, disabled, loaded, failed and independent same-name bundles");
} }
'''
with tempfile.TemporaryDirectory(prefix='horos-plugin-outcomes-') as directory:
    p = Path(directory)
    (p/'test.m').write_text(program)
    subprocess.run(['xcrun', 'clang', '-framework', 'Foundation', '-fsanitize=address', '-I', str(root/'Horos/Sources'), str(p/'test.m'), '-o', str(p/'test')], check=True)
    subprocess.run([str(p/'test')], check=True)
