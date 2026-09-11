#!/usr/bin/env python3
"""Build local synthetic plugins. Never install them automatically."""
from pathlib import Path
import argparse
import plistlib
import subprocess

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('destination', type=Path)
args = parser.parse_args()
args.destination.mkdir(parents=True, exist_ok=True)
if any(args.destination.iterdir()):
    parser.error('destination must be empty')
for name, architectures, principal, throws in [
    ('QADisabled', ['arm64', 'x86_64'], 'QADisabled', False),
    ('QAUniversal', ['arm64', 'x86_64'], 'QAUniversal', False),
    ('QAIntel', ['x86_64'], 'QAIntel', False),
    ('QAMissingClass', ['arm64', 'x86_64'], 'QAAbsent', False),
    ('QAInvalidSignature', ['arm64', 'x86_64'], 'QAInvalidSignature', False),
    ('QAInitializationFailure', ['arm64', 'x86_64'], 'QAInitializationFailure', True),
]:
    bundle = args.destination / (name + '.horosplugin')
    executable = bundle / 'Contents/MacOS' / name
    executable.parent.mkdir(parents=True)
    source = args.destination / (name + '.m')
    source.write_text('''#import <AppKit/AppKit.h>
@interface CLASS : NSObject
+ (id)filter;
- (long)filterImage:(NSString*)menu;
@end
@implementation CLASS
// +load runs while the loader is still inside -[NSBundle loadAndReturnError:],
// which is the only moment the note naming the plugin being loaded is true.
// Silent unless HOROS_PLUGIN_MARKER_DIR says where to look.
+ (void)load {
    const char *directory = getenv("HOROS_PLUGIN_MARKER_DIR");
    if (!directory) return;
    NSString *where = @(directory);
    for (NSString *entry in [NSFileManager.defaultManager contentsOfDirectoryAtPath:where error:NULL])
        if ([entry hasPrefix:@"Plugin_Loading"])
            NSLog(@"PLUGINFIXTURE while CLASS loads, %@ names %@", entry,
                  [NSString stringWithContentsOfFile:[where stringByAppendingPathComponent:entry]
                                            encoding:NSUTF8StringEncoding error:NULL]);
}
+ (id)filter { BODY }
- (long)prepareFilter:(id)viewer { return 0; }
- (long)filterImage:(NSString*)menu {
    NSAlert *alert = [[[NSAlert alloc] init] autorelease];
    alert.messageText = @"Synthetic plugin executed";
    alert.informativeText = @"QA universal filter completed without changing images.";
    [alert addButtonWithTitle:@"OK"];
    [alert runModal];
    return 0;
}
@end
'''.replace('CLASS', name).replace('BODY', '@throw [NSException exceptionWithName:@"SyntheticFailure" reason:@"Synthetic initialization failure" userInfo:nil];' if throws else 'return [[[self alloc] init] autorelease];'))
    command = ['xcrun', 'clang', '-bundle', '-framework', 'AppKit']
    for architecture in architectures:
        command += ['-arch', architecture]
    subprocess.run(command + [str(source), '-o', str(executable)], check=True)
    info = {'CFBundleExecutable': name, 'CFBundleIdentifier': 'org.horosproject.qa.' + name,
            'CFBundleName': name, 'CFBundleVersion': '1.0', 'CFBundlePackageType': 'BNDL',
            'NSPrincipalClass': principal, 'pluginType': 'imageFilter', 'MenuTitles': [name]}
    (bundle/'Contents/Info.plist').write_bytes(plistlib.dumps(info))
    resources = bundle/'Contents/Resources'
    resources.mkdir()
    (resources/'seal.txt').write_text('Original synthetic resource')
    subprocess.run(['codesign', '--force', '--sign', '-', str(bundle)], check=True, capture_output=True)
    if name == 'QAInvalidSignature':
        (resources/'seal.txt').write_text('Modified after signing')
print('Created six synthetic plugin bundles; none installed.')
