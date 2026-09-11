#!/usr/bin/env python3
"""Choosing languages writes preferences and never moves anything in the bundle."""
import re, subprocess, sys, tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]

# 1. Nothing may relocate a localization directory. Moving .lproj folders in or
#    out of Resources breaks the code signature of a signed application.
offenders = []
for folder in ['Horos/Sources', 'Preference Panes', 'Nitrogen/Sources']:
    base = root / folder
    if not base.exists():
        continue
    for source in sorted(list(base.rglob('*.m')) + list(base.rglob('*.mm'))):
        text = source.read_bytes().decode('latin1')
        for m in re.finditer(r'^.*\b(moveItemAtPath|moveItemAtURL|copyItemAtPath|removeItemAtPath)\b.*$', text, re.M):
            line = m.group(0)
            if line.lstrip().startswith('//'):
                continue
            if 'lproj' in line or 'Resources Disabled' in line or 'localizations' in line:
                offenders.append('%s:%d %s' % (source.relative_to(root),
                                               text[:m.start()].count('\n') + 1, line.strip()))
if offenders:
    print('FAIL: language selection still relocates bundle resources:')
    for o in offenders:
        print(' ', o)
    sys.exit(1)

header = root / 'Preference Panes/OSIGeneralPreferencePane/HorosLanguagePreferences.h'
code = r'''
#import <Foundation/Foundation.h>
#import "HorosLanguagePreferences.h"

#define check(...) do{if(!(__VA_ARGS__)){NSLog(@"FAIL: %s",#__VA_ARGS__);return 1;}}while(0)

static NSMutableArray *rowsFor(NSArray *codes, NSArray *activeCodes) {
    NSMutableArray *rows = [NSMutableArray array];
    for (NSString *code in codes)
        [rows addObject:[NSMutableDictionary dictionaryWithDictionary:
            @{@"foldername":code, @"active":@([activeCodes containsObject:code])}]];
    return rows;
}

int main(int argc, char **argv){@autoreleasepool{
 NSString *suite = @"org.horosproject.horos.language-selection-test";
 NSUserDefaults *defaults = [[NSUserDefaults alloc] initWithSuiteName:suite];
 [defaults removePersistentDomainForName:suite];

 NSArray *all = @[@"en", @"es", @"it-IT", @"ja-JP"];

 // A pane left untouched must not pin the language: with everything active the
 // keys are removed so macOS keeps deciding.
 [defaults setObject:@[@"en"] forKey:@"HorosEnabledLanguages"];
 [defaults setObject:@[@"en"] forKey:@"AppleLanguages"];
 HorosApplyLanguageRows(rowsFor(all, all), defaults);
 // Read the suite's own storage: AppleLanguages also exists in the global
 // domain, so -objectForKey: would keep seeing the system's value.
 NSDictionary *stored = [defaults persistentDomainForName:suite];
 check([stored objectForKey:@"HorosEnabledLanguages"] == nil);
 check([stored objectForKey:@"AppleLanguages"] == nil);

 // A subset is written, canonicalised, and ordered against the system's own
 // preference so the most preferred available language comes first.
 HorosApplyLanguageRows(rowsFor(all, @[@"es", @"it-IT"]), defaults);
 stored = [defaults persistentDomainForName:suite];
 NSArray *enabled = [stored objectForKey:@"HorosEnabledLanguages"];
 NSArray *ordered = [stored objectForKey:@"AppleLanguages"];
 check(enabled.count == 2 && ordered.count == 2);
 check([enabled containsObject:@"es"] && [enabled containsObject:@"it-IT"]);
 for (NSString *code in enabled) check([ordered containsObject:code]);
 check(![enabled containsObject:@"en"] && ![enabled containsObject:@"ja-JP"]);

 // Turning everything off cannot leave the application with no language.
 HorosApplyLanguageRows(rowsFor(all, @[]), defaults);
 check([[[defaults persistentDomainForName:suite] objectForKey:@"HorosEnabledLanguages"] count] == 1);

 // An empty list is a no-op rather than a wipe.
 [defaults setObject:@[@"es"] forKey:@"HorosEnabledLanguages"];
 HorosApplyLanguageRows(@[], defaults);
 check([[[defaults persistentDomainForName:suite] objectForKey:@"HorosEnabledLanguages"] isEqual:@[@"es"]]);

 // Reading the rows back from a real bundle: Base is not a language, and with
 // no stored preference every localization is active.
 NSBundle *bundle = [NSBundle bundleWithPath:[NSString stringWithUTF8String:argv[1]]];
 check(bundle != nil);
 [defaults removeObjectForKey:@"HorosEnabledLanguages"];
 NSArray *rows = HorosLanguageRows(bundle, defaults);
 check(rows.count == 4);
 for (NSDictionary *row in rows) {
   check(![[row objectForKey:@"foldername"] isEqualToString:@"Base"]);
   check([[row objectForKey:@"active"] boolValue]);
   check([[row objectForKey:@"language"] length] > 0);
 }
 // With a stored preference only those are active, matched canonically.
 [defaults setObject:@[@"es"] forKey:@"HorosEnabledLanguages"];
 rows = HorosLanguageRows(bundle, defaults);
 NSUInteger active = 0;
 for (NSDictionary *row in rows) if ([[row objectForKey:@"active"] boolValue]) active++;
 check(active == 1);

 [defaults removePersistentDomainForName:suite];
 NSLog(@"PASS: no source relocates a localization directory; selection writes only preferences, keeps at least one language, leaves an untouched pane to macOS and reads Base out of the list");
}}
'''

with tempfile.TemporaryDirectory(prefix='horos-language-') as folder:
    p = Path(folder)
    # A minimal bundle with the localizations to read back.
    resources = p / 'Probe.app/Contents/Resources'
    for name in ['en.lproj', 'es.lproj', 'it-IT.lproj', 'ja-JP.lproj', 'Base.lproj']:
        (resources / name).mkdir(parents=True)
    (p / 'Probe.app/Contents/Info.plist').write_text(
        '<?xml version="1.0" encoding="UTF-8"?><!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd"><plist version="1.0"><dict>'
        '<key>CFBundleIdentifier</key><string>org.horosproject.probe</string>'
        '<key>CFBundleDevelopmentRegion</key><string>en</string></dict></plist>')
    (p / 'test.m').write_text(code)
    subprocess.run(['xcrun', 'clang', '-fno-objc-arc', '-fsanitize=address,undefined',
                    '-fno-sanitize-recover=all', '-framework', 'Foundation',
                    '-I', str(header.parent), str(p / 'test.m'), '-o', str(p / 'test')], check=True)
    subprocess.run([str(p / 'test'), str(p / 'Probe.app')], check=True)
