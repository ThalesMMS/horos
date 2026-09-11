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

The window is opened through the host's own menu action and nothing modal is
called from the debugger: a panel cannot be answered while the process is
stopped.

    python3 tools/exercise-native-preferences.py --pid N --step open|inspect|merge
"""
import argparse
import json
from pathlib import Path
import re
import subprocess
import uuid

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--pid', type=int, required=True)
parser.add_argument('step', choices=['open', 'inspect', 'merge'])
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
