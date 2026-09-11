#!/usr/bin/env python3
"""Create, count, refresh and delete a smart album in the running build (#380 B).

Steps, each on the live browser through its own API:

1. create a smart album with the shared ROI/segmentation clause and one with a
   modality clause, through `DicomDatabase`, and refresh the browser;
2. report, for every album, the predicate stored, the studies the browser's own
   predicate compiler matches and the count the background thread published;
3. import nothing: the refresh path is the one the host runs after an import
   (`OsirixAddToDBNotification`), so the notification is posted and the counts
   are read again;
4. delete the album while the count thread is running and report whether the
   thread survived, whether the album is gone, and whether the remaining
   counts are still right. The deletion is *scheduled*, never called from the
   debugger: it can raise a confirmation panel, and a panel cannot be answered
   while the process is stopped.

    python3 tools/exercise-native-smart-albums.py --pid N
"""
import argparse
import json
from pathlib import Path
import re
import subprocess
import uuid

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--pid', type=int, required=True)
parser.add_argument('step', choices=['create', 'read', 'delete'])
parser.add_argument('--label', default=None)
parser.add_argument('--output', type=Path, default=Path('local-validation/issue-380-native'))
args = parser.parse_args()
args.label = args.label or ('smart-albums-' + args.step)
if args.pid <= 0 or not re.fullmatch('[a-z0-9-]+', args.label):
    parser.error('positive PID and a lowercase label')
args.output.mkdir(parents=True, exist_ok=True)
out_dir = args.output.resolve()
report = out_dir / (args.label + '.json')
staged = report.with_name(report.name + '.' + uuid.uuid4().hex + '.partial')

expression = r'''
NSMutableDictionary *a380 = [NSMutableDictionary dictionary];
id br380 = (id)[(id)objc_getClass("BrowserController") currentBrowser];
id db380 = (id)[br380 database];
NSString *clause380 = (NSString*)[(Class)objc_getClass("HorosStudyContentPredicates") roiOrSegmentationFormat];
a380[@"clause"] = clause380;
STEP
'''
steps = {'create': r'''
NSArray *names380 = @[@"Horos380 content", @"Horos380 modality"];
NSArray *formats380 = @[clause380, @"modality ==[cd] \"MR\""];
for (long i380 = 0; i380 < 2; i380++) {
  id existing380 = nil;
  for (id al380 in (NSArray*)[br380 albumsInDatabase]) if ([(NSString*)[(NSObject*)al380 valueForKey:@"name"] isEqualToString:[names380 objectAtIndex:i380]]) existing380 = al380;
  id album380 = existing380 ?: (id)[db380 newObjectForEntity:(id)[db380 albumEntity]];
  (void)[(NSObject*)album380 setValue:[names380 objectAtIndex:i380] forKey:@"name"];
  (void)[(NSObject*)album380 setValue:@YES forKey:@"smartAlbum"];
  (void)[(NSObject*)album380 setValue:[formats380 objectAtIndex:i380] forKey:@"predicateString"];
  a380[[names380 objectAtIndex:i380]] = existing380 ? @"updated" : @"created";
}
(void)[db380 save:nil];
(void)[br380 performSelector:@selector(refreshAlbums) withObject:nil afterDelay:0.1];
(void)[br380 performSelector:@selector(outlineViewRefresh) withObject:nil afterDelay:0.2];
''', 'read': r'''
NSMutableArray *report380 = [NSMutableArray array];
for (id al380 in (NSArray*)[br380 albumsInDatabase]) {
  NSString *name380 = (NSString*)[(NSObject*)al380 valueForKey:@"name"];
  if (![name380 hasPrefix:@"Horos380"]) continue;
  NSString *format380 = (NSString*)[(NSObject*)al380 valueForKey:@"predicateString"];
  NSPredicate *pred380 = (NSPredicate*)[br380 smartAlbumPredicateString:format380];
  NSArray *studies380 = (NSArray*)[db380 objectsForEntity:(id)[db380 studyEntity] predicate:pred380];
  NSMutableArray *matched380 = [NSMutableArray array];
  for (id st380 in studies380) (void)[matched380 addObject:(NSString*)[(NSObject*)st380 valueForKey:@"name"] ?: @""];
  (void)[report380 addObject:@{@"album": name380, @"predicate": format380 ?: @"", @"matched": matched380,
    @"count": @((long)[matched380 count]), @"numberOfStudies": (NSString*)[(NSObject*)al380 valueForKey:@"numberOfStudies"] ?: @""}];
}
a380[@"albums"] = report380;
NSMutableArray *all380 = [NSMutableArray array];
for (id al380 in (NSArray*)[br380 albumsInDatabase]) (void)[all380 addObject:(NSString*)[(NSObject*)al380 valueForKey:@"name"] ?: @""];
a380[@"allAlbums"] = all380;
a380[@"albumTableRows"] = @((long)[(NSTableView*)[(NSObject*)br380 valueForKey:@"albumTable"] numberOfRows]);
''', 'delete': r'''
for (id al380 in [(NSArray*)[br380 albumsInDatabase] copy]) {
  NSString *name380 = (NSString*)[(NSObject*)al380 valueForKey:@"name"];
  if ([name380 isEqualToString:@"Horos380 modality"]) { (void)[br380 performSelector:@selector(removeAlbumObject:) withObject:al380 afterDelay:0.1]; a380[@"deletionScheduled"] = name380; }
}
(void)[br380 performSelector:@selector(refreshAlbums) withObject:nil afterDelay:0.1];
'''}
expression = expression.replace('STEP', steps[args.step])
expression += '(void)[[NSJSONSerialization dataWithJSONObject:a380 options:3 error:nil] writeToFile:@' + json.dumps(str(staged)) + ' atomically:YES];\n'
commands = out_dir / (args.label + '.lldb')
commands.write_text('expression -l objc++ -- @import AppKit\n'
                    'expression -l objc++ -- { ' + ' '.join(expression.splitlines()) + ' }\nprocess detach\n')
result = subprocess.run(['xcrun', 'lldb', '--batch', '-p', str(args.pid), '-s', str(commands)], capture_output=True, text=True)
(out_dir / (args.label + '.log')).write_text(result.stdout + result.stderr)
if result.returncode or not staged.exists():
    raise SystemExit('lldb step failed; inspect ' + str(out_dir / (args.label + '.log')))
staged.replace(report)
print(json.dumps(json.loads(report.read_text()), indent=1)[:2000])
