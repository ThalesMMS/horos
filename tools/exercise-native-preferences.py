#!/usr/bin/env python3
"""Open the preferences window and check what it preserves (#380 A).

Reports, from the running development build:

- every pane the window offers, and which of them come from plugins;
- the pane that is showing after switching to Locations and back, so a switch
  keeps content rather than emptying the window;
- the DICOM nodes in `SERVERS` before and after a DICOMweb merge applied to the
  first node through the shared editor's own merge, so AE title, port and TLS
  can be compared;
- whether the window declares any fullscreen presentation of its own.

The Protocols pane's copy of HANGINGPROTOCOLS (#618), with the window open:

- `protocols` shows the pane (its willSelect makes the copy);
- `protocols-edit` edits the pane's copy the way the table can: it turns over the
  Propagate flag of the first modality's Default protocol and adds a protocol to
  that modality (the pane refuses, with an alert, a new name for Default), records
  whether the stored value saw either, and shows Locations (the Protocols pane's
  willUnselect saves);
- `protocols-inspect` records the first modality's protocols, stored and in the
  pane's copy, and the value types of the stored Default protocol;
- `protocols-cycle` alternates Protocols and Locations 50 times.

A step that changes panes only schedules the change on the main run loop.

The window is opened through the host's own menu action and nothing modal is
called from the debugger: a panel cannot be answered while the process is
stopped.

    python3 tools/exercise-native-preferences.py --pid N open|inspect|merge|protocols|protocols-edit|protocols-inspect|protocols-cycle
"""
import argparse
import json
from pathlib import Path
import re
import subprocess
import uuid

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--pid', type=int, required=True)
parser.add_argument('step', choices=['open', 'inspect', 'merge', 'protocols', 'protocols-edit', 'protocols-inspect',
                                     'protocols-cycle'])
parser.add_argument('--label', default=None)
parser.add_argument('--output', type=Path, default=Path('local-validation/issue-380-native'))
args = parser.parse_args()
args.label = args.label or ('preferences-' + args.step)
if args.pid <= 0 or not re.fullmatch('[a-z0-9-]+', args.label):
    parser.error('positive PID and a lowercase label')
args.output.mkdir(parents=True, exist_ok=True)
out_dir = args.output.resolve()
report = out_dir / (args.label + '.json')
staged = report.with_name(report.name + '.' + uuid.uuid4().hex + '.partial')

# The Protocols pane (whether or not it is showing), its copy and the stored value.
PROTOCOLS_STATE = r'''
id pw618 = (id)[(Class)objc_getClass("PreferencesWindowController") sharedPreferencesWindowController];
id list618 = (id)[(NSObject*)pw618 valueForKey:@"panesListView"];
id pane618 = nil;
for (long i618 = 0; i618 < (long)[list618 itemsCount]; i618++) {
  id ctx618 = (id)[list618 contextForItemAtIndex:i618];
  if ([(NSString*)[(NSObject*)ctx618 valueForKey:@"resourceName"] isEqualToString:@"OSIHangingPreferencePanePref"])
    pane618 = (id)[(NSObject*)ctx618 valueForKey:@"pane"];
}
p380[@"currentPane"] = (NSString*)[(NSObject*)[(NSObject*)pw618 valueForKey:@"currentContext"] valueForKey:@"title"] ?: @"";
p380[@"paneClass"] = pane618 ? (NSString*)[(NSObject*)[(NSObject*)pane618 class] description] : @"";
NSDictionary *copy618 = pane618 ? (NSDictionary*)[(NSObject*)pane618 valueForKey:@"hangingProtocols"] : nil;
NSDictionary *stored618 = (NSDictionary*)[[NSUserDefaults standardUserDefaults] objectForKey:@"HANGINGPROTOCOLS"];
p380[@"copyIsStoredObject"] = @(copy618 != nil && copy618 == stored618);
p380[@"copyEqualsStored"] = @((BOOL)[stored618 isEqual:copy618]);
p380[@"storedModalities"] = @((long)[stored618 count]);
p380[@"copyModalities"] = @((long)[copy618 count]);
NSString *modality618 = (NSString*)[(NSArray*)[(NSArray*)[(copy618 ?: stored618) allKeys] sortedArrayUsingSelector:@selector(compare:)] firstObject];
p380[@"modality"] = modality618 ?: @"";
id first618 = modality618 ? (id)[(NSArray*)[copy618 objectForKey:modality618] firstObject] : nil;
NSDictionary *storedFirst618 = modality618 ? (NSDictionary*)[(NSArray*)[stored618 objectForKey:modality618] firstObject] : nil;
NSArray *copyList618 = modality618 ? (NSArray*)[copy618 objectForKey:modality618] : nil;
NSArray *storedList618 = modality618 ? (NSArray*)[stored618 objectForKey:modality618] : nil;
p380[@"copyNames"] = (NSArray*)[copyList618 valueForKey:@"Study Description"] ?: @[];
p380[@"storedNames"] = (NSArray*)[storedList618 valueForKey:@"Study Description"] ?: @[];
p380[@"copyPropagate"] = (id)[(NSDictionary*)first618 objectForKey:@"Propagate"] ?: @"";
p380[@"storedPropagate"] = (id)[storedFirst618 objectForKey:@"Propagate"] ?: @"";
NSMutableDictionary *types618 = [NSMutableDictionary dictionary];
for (NSString *key618 in (NSArray*)[storedFirst618 allKeys])
  (void)[types618 setObject:(NSString*)[(NSObject*)[(NSObject*)[storedFirst618 objectForKey:key618] classForCoder] description] forKey:key618];
p380[@"storedFirstTypes"] = types618;
'''

steps = {
    'open': r'''
id ac380 = (id)[(NSApplication*)NSApp delegate];
(void)[ac380 performSelector:@selector(showPreferencePanel:) withObject:nil afterDelay:0.1];
p380[@"scheduled"] = @YES;
''',
    'inspect': r'''
id pw380 = (id)[(Class)objc_getClass("PreferencesWindowController") sharedPreferencesWindowController];
p380[@"controller"] = @(pw380 != nil);
if (pw380) {
  NSWindow *w380 = (NSWindow*)[pw380 window];
  p380[@"windowVisible"] = @((BOOL)[w380 isVisible]);
  p380[@"windowTitle"] = (NSString*)[w380 title] ?: @"";
  p380[@"contentSubviews"] = @((long)[(NSArray*)[(NSView*)[w380 contentView] subviews] count]);
  p380[@"presentationOptions"] = @((long)[(NSApplication*)NSApp presentationOptions]);
  NSMutableArray *panes380 = [NSMutableArray array];
  id list380 = (id)[(NSObject*)pw380 valueForKey:@"panesListView"];
  for (long i380 = 0; i380 < (long)[list380 itemsCount]; i380++) {
    id ctx380 = (id)[list380 contextForItemAtIndex:i380];
    NSBundle *bundle380 = (NSBundle*)[(NSObject*)ctx380 valueForKey:@"parentBundle"];
    (void)[panes380 addObject:@{@"title": (NSString*)[(NSObject*)ctx380 valueForKey:@"title"] ?: @"",
                                @"bundle": (NSString*)[bundle380 bundleIdentifier] ?: @"",
                                @"loaded": @((id)[(NSObject*)ctx380 valueForKey:@"pane"] != nil)}];
  }
  p380[@"panes"] = panes380;
  id current380 = (id)[(NSObject*)pw380 valueForKey:@"currentContext"];
  p380[@"currentPane"] = (NSString*)[(NSObject*)current380 valueForKey:@"title"] ?: @"";
}
NSArray *servers380 = (NSArray*)[[NSUserDefaults standardUserDefaults] objectForKey:@"SERVERS"] ?: @[];
p380[@"servers"] = servers380;
''',
    'merge': r'''
NSArray *servers380 = (NSArray*)[[NSUserDefaults standardUserDefaults] objectForKey:@"SERVERS"] ?: @[];
p380[@"serversBefore"] = servers380;
if ([servers380 count]) {
  NSDictionary *node380 = (NSDictionary*)[servers380 objectAtIndex:0];
  NSDictionary *merged380 = (NSDictionary*)[(Class)objc_getClass("HorosDICOMwebNodeEditor")
      nodeMergingInto:node380 url:@"https://dicomweb.example/dicomweb" credentialIdentifier:@"horos380-credential"];
  p380[@"identity"] = (NSString*)[(Class)objc_getClass("HorosDICOMwebNodeEditor") identityOfNode:node380];
  p380[@"mergedIdentity"] = (NSString*)[(Class)objc_getClass("HorosDICOMwebNodeEditor") identityOfNode:merged380];
  p380[@"before"] = node380;
  p380[@"after"] = merged380;
  NSMutableArray *changed380 = [NSMutableArray array];
  for (NSString *key380 in (NSArray*)[merged380 allKeys]) {
    NSObject *a380v = (NSObject*)[node380 objectForKey:key380], *b380v = (NSObject*)[merged380 objectForKey:key380];
    if (a380v == nil || ![(NSString*)[a380v description] isEqualToString:(NSString*)[b380v description]]) (void)[changed380 addObject:key380];
  }
  p380[@"changedKeys"] = changed380;
  p380[@"editedKeys"] = (NSArray*)[(Class)objc_getClass("HorosDICOMwebNodeEditor") editedKeys];
}
''',
    'protocols': r'''
id pw618 = (id)[(Class)objc_getClass("PreferencesWindowController") sharedPreferencesWindowController];
(void)[(NSObject*)pw618 performSelector:@selector(setCurrentContextWithResourceName:) withObject:@"OSIHangingPreferencePanePref" afterDelay:0.1];
p380[@"scheduled"] = @YES;
''',
    'protocols-edit': PROTOCOLS_STATE + r'''
if (first618 && [(NSString*)[(NSObject*)[(NSObject*)pane618 class] description] isEqualToString:@"OSIHangingPreferencePanePref"]) {
  BOOL propagate618 = (BOOL)[(NSNumber*)[(NSDictionary*)first618 objectForKey:@"Propagate"] boolValue];
  (void)[(NSMutableDictionary*)first618 setObject:@(!propagate618) forKey:@"Propagate"];
  NSMutableDictionary *added618 = (NSMutableDictionary*)[NSMutableDictionary dictionaryWithDictionary:(NSDictionary*)first618];
  (void)[added618 setObject:@"Added in the #618 check" forKey:@"Study Description"];
  (void)[(NSMutableArray*)[copy618 objectForKey:modality618] addObject:added618];
  NSDictionary *stored618b = (NSDictionary*)[[NSUserDefaults standardUserDefaults] objectForKey:@"HANGINGPROTOCOLS"];
  p380[@"storedNamesAfterEdit"] = (NSArray*)[(NSArray*)[stored618b objectForKey:modality618] valueForKey:@"Study Description"] ?: @[];
  p380[@"storedPropagateAfterEdit"] = (id)[(NSDictionary*)[(NSArray*)[stored618b objectForKey:modality618] objectAtIndex:0] objectForKey:@"Propagate"] ?: @"";
  p380[@"copyNamesAfterEdit"] = (NSArray*)[(NSArray*)[copy618 objectForKey:modality618] valueForKey:@"Study Description"] ?: @[];
  p380[@"copyPropagateAfterEdit"] = (id)[(NSDictionary*)first618 objectForKey:@"Propagate"] ?: @"";
  (void)[(NSObject*)pw618 performSelector:@selector(setCurrentContextWithResourceName:) withObject:@"OSILocationsPreferencePanePref" afterDelay:0.1];
  p380[@"scheduled"] = @YES;
}
''',
    'protocols-inspect': PROTOCOLS_STATE,
    'protocols-cycle': r'''
id pw618 = (id)[(Class)objc_getClass("PreferencesWindowController") sharedPreferencesWindowController];
for (long i618 = 0; i618 < 100; i618++)
  (void)[(NSObject*)pw618 performSelector:@selector(setCurrentContextWithResourceName:) withObject:(i618 % 2 ? @"OSILocationsPreferencePanePref" : @"OSIHangingPreferencePanePref") afterDelay:0.1 + 0.05 * i618];
p380[@"scheduled"] = @100;
''',
}

expression = 'NSMutableDictionary *p380 = [NSMutableDictionary dictionary];\n' + steps[args.step]
expression += '(void)[[NSJSONSerialization dataWithJSONObject:p380 options:3 error:nil] writeToFile:@' + json.dumps(str(staged)) + ' atomically:YES];\n'
commands = out_dir / (args.label + '.lldb')
commands.write_text('expression -l objc++ -- @import AppKit\n'
                    'expression -l objc++ -- { ' + ' '.join(expression.splitlines()) + ' }\nprocess detach\n')
result = subprocess.run(['xcrun', 'lldb', '--batch', '-p', str(args.pid), '-s', str(commands)], capture_output=True, text=True)
(out_dir / (args.label + '.log')).write_text(result.stdout + result.stderr)
if result.returncode or not staged.exists():
    raise SystemExit('lldb step failed; inspect ' + str(out_dir / (args.label + '.log')))
staged.replace(report)
data = json.loads(report.read_text())
summary = {k: v for k, v in data.items() if k not in ('servers', 'serversBefore', 'before', 'after', 'panes')}
if 'panes' in data:
    summary['paneCount'] = len(data['panes'])
    summary['paneTitles'] = [p['title'] for p in data['panes']]
print(json.dumps(summary, indent=1)[:1800])
