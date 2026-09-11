#!/usr/bin/env python3
"""Drive retrieve-and-view in the development app against a loopback C-GET peer (#604).

Steps, each an LLDB attach to the development process (a `--debug` build):

    python3 tools/exercise-native-retrieve-viewing.py servers --pid P --port 11193 --aetitle CGETFIX
    python3 tools/exercise-native-retrieve-viewing.py query   --pid P --patient CGET-27
    python3 tools/exercise-native-retrieve-viewing.py view    --pid P
    python3 tools/exercise-native-retrieve-viewing.py probe   --pid P --label t1
    python3 tools/exercise-native-retrieve-viewing.py scroll  --pid P --index 3
    python3 tools/exercise-native-retrieve-viewing.py cancel  --pid P
    python3 tools/exercise-native-retrieve-viewing.py close   --pid P
    python3 tools/exercise-native-retrieve-viewing.py pref    --pid P --progressive YES

`servers` installs one C-GET node in the running defaults; `query` opens the
query window, queries the patient and selects the first result; `view` sends
the window's own retrieve-and-view action; `probe` reads the open 2D viewers
(images, shown index and SOP instance, overlay text, partial flag), the
viewing state (phase, reloads, seconds to first image) and the retrieve
threads. Every snapshot is a JSON file; nothing leaves local-validation.

The probe reads nothing through Core Data: an import may hold the context
lock while LLDB has every thread stopped, and a faulting access never returns.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess
import uuid

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument('step', choices=['servers', 'query', 'view', 'probe', 'scroll', 'cancel', 'close', 'pref'])
parser.add_argument('--pid', type=int, required=True)
parser.add_argument('--port', type=int, default=11193)
parser.add_argument('--aetitle', default='CGETFIX')
parser.add_argument('--address', default='127.0.0.1',
                    help='peer address; the default keeps the loopback fixture of #604')
parser.add_argument('--patient', default='CGET-27')
parser.add_argument('--index', type=int, default=0)
parser.add_argument('--progressive', choices=['YES', 'NO'], default='YES')
parser.add_argument('--label', default=None)
parser.add_argument('--output', type=Path, default=Path('local-validation/issue-604-native'))
args = parser.parse_args()
label = args.label or args.step
if args.pid <= 0 or not re.fullmatch('[a-z0-9-]+', label) or not re.fullmatch(r'[A-Z0-9*^-]+', args.patient):
    parser.error('Use a positive PID, a lowercase label and a plain patient ID')
if not re.fullmatch(r'[0-9.]+', args.address):
    parser.error('Use a numeric peer address')
args.output.mkdir(parents=True, exist_ok=True)
output = (args.output / ('view-' + label + '.json')).resolve()
staged = output.with_name(output.name + '.' + uuid.uuid4().hex + '.partial')

COMMON = r'''
NSMutableDictionary *m604 = [NSMutableDictionary dictionary];
'''
bodies = {
    'servers': COMMON + r'''
NSDictionary *server604 = @{@"AETitle": @"AETITLE", @"Address": @"ADDRESS", @"Port": @PORT, @"Description": @"Test peer",
  @"Activated": @YES, @"QR": @YES, @"Send": @NO, @"retrieveMode": @1, @"TransferSyntax": @0};
[[NSUserDefaults standardUserDefaults] setObject: @[server604] forKey: @"SERVERS"];
[[NSNotificationCenter defaultCenter] postNotificationName: @"DCMNetServicesDidChange" object: nil];
m604[@"servers"] = @((long)[(NSArray*)[[NSUserDefaults standardUserDefaults] objectForKey: @"SERVERS"] count]);
''',
    'pref': COMMON + r'''
[[NSUserDefaults standardUserDefaults] setBool: PROGRESSIVE forKey: @"HorosProgressiveRetrieveViewing"];
m604[@"HorosProgressiveRetrieveViewing"] = @((BOOL)[[NSUserDefaults standardUserDefaults] boolForKey: @"HorosProgressiveRetrieveViewing"]);
''',
    'query': COMMON + r'''
id qc604 = (id)[(Class)objc_getClass("QueryController") currentQueryController];
if (qc604 == nil) { qc604 = (id)[(id)[(Class)objc_getClass("QueryController") alloc] initAutoQuery: NO]; }
(void)[qc604 showWindow: nil];
(void)[qc604 refreshSources];
NSArray *result604 = (NSArray*)[qc604 queryPatientID: @"PATIENT"];
m604[@"results"] = @((long)[result604 count]);
id ov604 = (id)[qc604 outlineView];
long rows604 = (long)[(NSOutlineView*)ov604 numberOfRows];
m604[@"rows"] = @(rows604);
if (rows604 > 0) { (void)[(NSOutlineView*)ov604 selectRowIndexes: [NSIndexSet indexSetWithIndex: 0] byExtendingSelection: NO]; }
id item604 = rows604 > 0 ? (id)[(NSOutlineView*)ov604 itemAtRow: 0] : nil;
m604[@"item"] = item604 ? NSStringFromClass((Class)[(NSObject*)item604 class]) : @"";
m604[@"studyUID"] = item604 ? ((NSString*)[item604 uid] ?: @"") : @"";
m604[@"numberImages"] = item604 ? @((long)[(NSNumber*)[item604 numberImages] intValue]) : @0;
m604[@"windowVisible"] = @((BOOL)[(NSWindow*)[qc604 window] isVisible]);
''',
    'view': COMMON + r'''
id qc604 = (id)[(Class)objc_getClass("QueryController") currentQueryController];
m604[@"queryController"] = @(qc604 != nil);
m604[@"startedAt"] = @((double)[NSDate timeIntervalSinceReferenceDate]);
(void)[qc604 retrieveAndView: nil];
m604[@"pending"] = @((long)[(NSArray*)[qc604 pendingRetrieveAndViewItems] count]);
''',
    'probe': COMMON + r'''
m604[@"now"] = @((double)[NSDate timeIntervalSinceReferenceDate]);
NSMutableArray *viewers604 = [NSMutableArray array];
for (id v604 in (NSArray*)[(Class)objc_getClass("ViewerController") get2DViewers]) {
  NSArray *files604 = (NSArray*)[v604 fileList];
  long cur604 = (long)[(id)[v604 imageView] curImage];
  id shown604 = (cur604 >= 0 && cur604 < (long)[files604 count]) ? [files604 objectAtIndex: cur604] : nil;
  DCMPix *pix604 = (DCMPix*)[(id)[v604 imageView] curDCM];
  (void)[viewers604 addObject: @{
    @"images": @((long)[files604 count]),
    @"pixCount": @((long)[(NSArray*)[v604 pixList] count]),
    @"curImage": @(cur604),
    @"shownFile": [(NSString*)[pix604 srcFile] lastPathComponent] ?: @"",
    @"shownOriginZ": @((double)[pix604 originZ]),
    @"pixLoaded": @((BOOL)[pix604 isLoaded]),
    @"missingPixelsReason": (NSString*)[pix604 missingPixelsReason] ?: @"",
    @"everythingLoaded": @((BOOL)[v604 isEverythingLoaded])}];
}
m604[@"viewers"] = viewers604;
NSMutableArray *threads604 = [NSMutableArray array];
for (NSThread *t604 in (NSArray*)[(id)[(Class)objc_getClass("ThreadsManager") defaultManager] threads])
  (void)[threads604 addObject: @{@"name": [t604 name] ?: @"", @"status": (NSString*)[(NSObject*)t604 valueForKey: @"status"] ?: @"", @"cancelled": @((BOOL)[t604 isCancelled]), @"executing": @((BOOL)[t604 isExecuting])}];
m604[@"threads"] = threads604;
id qc604 = (id)[(Class)objc_getClass("QueryController") currentQueryController];
m604[@"pending"] = @((long)[(NSArray*)[qc604 pendingRetrieveAndViewItems] count]);
id ov604 = (id)[qc604 outlineView];
NSString *study604 = ((long)[(NSOutlineView*)ov604 numberOfRows] > 0) ? ((NSString*)[(id)[(NSOutlineView*)ov604 itemAtRow: 0] uid] ?: @"") : @"";
id state604 = (id)[(id)[(Class)objc_getClass("HorosRetrieveViewing") shared] stateForStudyUID: study604 seriesUID: @""];
if (state604) m604[@"state"] = @{@"phase": @((long)[state604 phase]), @"localCount": @((long)[state604 localCount]), @"expectedCount": @((long)[state604 expectedCount]),
  @"failedCount": @((long)[state604 failedCount]), @"inventoryConfirmed": @((BOOL)[state604 inventoryConfirmed]), @"viewerOpened": @((BOOL)[state604 viewerOpened]),
  @"overlay": (NSString*)[state604 overlayText] ?: @"",
  @"secondsToFirstImage": @((double)[(id)[(Class)objc_getClass("HorosRetrieveViewing") shared] secondsToFirstImageForStudyUID: study604 seriesUID: @""]),
  @"reloads": @((long)[(id)[(Class)objc_getClass("HorosRetrieveViewing") shared] reloadsForStudyUID: study604 seriesUID: @""])};
m604[@"studyUID"] = study604;
m604[@"modal"] = (NSString*)[(NSWindow*)[(NSApplication*)NSApp modalWindow] title] ?: @"(none)";
''',
    'scroll': COMMON + r'''
id v604 = [(NSArray*)[(Class)objc_getClass("ViewerController") get2DViewers] firstObject];
if (v604) { (void)[v604 setImageIndex: (long)INDEX]; m604[@"curImage"] = @((long)[(id)[v604 imageView] curImage]); }
m604[@"viewer"] = @(v604 != nil);
''',
    'cancel': COMMON + r'''
long cancelled604 = 0;
for (NSThread *t604 in (NSArray*)[(id)[(Class)objc_getClass("ThreadsManager") defaultManager] threads])
  if ([[t604 name] containsString: @"Retrieving"]) { [t604 cancel]; cancelled604++; }
m604[@"cancelled"] = @(cancelled604);
''',
    'close': COMMON + r'''
id v604 = [(NSArray*)[(Class)objc_getClass("ViewerController") get2DViewers] firstObject];
m604[@"closed"] = @(v604 != nil);
if (v604) (void)[(NSWindow*)[v604 window] close];
''',
}
body = bodies[args.step].replace('AETITLE', args.aetitle).replace('PORT', str(args.port)).replace('PATIENT', args.patient) \
    .replace('INDEX', str(args.index)).replace('PROGRESSIVE', args.progressive) \
    .replace('ADDRESS', args.address)
expr = body + '(void)[[NSJSONSerialization dataWithJSONObject:m604 options:3 error:nil] writeToFile:@"STAGED" atomically:YES];\n'
expr = expr.replace('STAGED', str(staged))
commands = args.output / ('view-' + label + '.lldb')
commands.write_text('expression -l objc++ -- @import AppKit\n'
                    'expression -l objc++ -- { ' + ' '.join(expr.splitlines()) + ' }\nprocess detach\n')
run = subprocess.run(['xcrun', 'lldb', '--batch', '-p', str(args.pid), '-s', str(commands)], capture_output=True, text=True)
(args.output / ('view-' + label + '.log')).write_text(run.stdout + run.stderr)
if not staged.exists():
    print('\n'.join(sorted(set(re.findall(r'error: [^\\\n]{0,200}', run.stdout + run.stderr)))))
    raise SystemExit(1)
staged.replace(output)
print(json.dumps(json.loads(output.read_text()), indent=1, sort_keys=True))
