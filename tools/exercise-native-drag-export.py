#!/usr/bin/env python3
"""Fulfil database file promises in the development app without a Finder drop (#605).

Steps, each an LLDB attach to the development process (a `--debug` build):

    python3 tools/exercise-native-drag-export.py promise    --pid P --patient REPLACE-603 --level study --mode dicom --dest /…/local-validation/issue-605-native/out/dicom
    python3 tools/exercise-native-drag-export.py promise    --pid P --patient REPLACE-603 --level series --series-index 0 --mode jpeg --dest …
    python3 tools/exercise-native-drag-export.py pasteboard --pid P --patient REPLACE-603
    python3 tools/exercise-native-drag-export.py frame      --pid P --patient REPLACE-603 --dest …/frame.jpg
    python3 tools/exercise-native-drag-export.py cancel     --pid P
    python3 tools/exercise-native-drag-export.py threads    --pid P

`promise` builds the same writer the outline or the thumbnail matrix hands
AppKit (`filePromiseForDatabaseObjects:asJPEG:`), records how long that took,
then calls its `writePromiseToURL:` as a drop target would, with `--dest` as
the promised URL; the completion writes `<dest>.result.json`. `pasteboard`
puts two rows on a private pasteboard as two items and reads the aggregated
identifiers. `frame` promises the captured preview frame of the first image
thumbnail as one JPEG. `promise-cancel` starts a promise and cancels its
activity thread inside the same attach, so the worker never runs at all;
`cancel` cancels whatever export threads are running, from a second attach. Nothing leaves local-validation.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess
import uuid

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument('step', choices=['promise', 'promise-cancel', 'promise-cancel-after', 'promise-delete', 'promise-encrypted', 'pasteboard', 'frame', 'cancel', 'threads'])
parser.add_argument('--pid', type=int, required=True)
parser.add_argument('--patient', default='REPLACE-603')
parser.add_argument('--level', choices=['study', 'series', 'image', 'study+series'], default='study')
parser.add_argument('--series-index', type=int, default=0)
parser.add_argument('--mode', choices=['dicom', 'jpeg'], default='dicom')
parser.add_argument('--dest', default='')
parser.add_argument('--cancel-after', type=float, default=0.5, help='promise-cancel-after: seconds after the process resumes before the export thread is cancelled')
parser.add_argument('--label', default=None)
parser.add_argument('--output', type=Path, default=Path('local-validation/issue-605-native'))
args = parser.parse_args()
label = args.label or args.step
if args.pid <= 0 or not re.fullmatch('[a-z0-9-]+', label) or not re.fullmatch('[A-Z0-9-]+', args.patient):
    parser.error('Use a positive PID, a lowercase label and a plain patient ID')
if args.step.startswith('promise') or args.step == 'frame':
    pass
if args.step in ('promise', 'promise-cancel', 'promise-cancel-after', 'promise-delete', 'promise-encrypted', 'frame') and ('local-validation' not in args.dest or not args.dest.startswith('/')):
    parser.error('--dest must be an absolute path under local-validation')
args.output.mkdir(parents=True, exist_ok=True)
output = (args.output / ('drag-' + label + '.json')).resolve()
staged = output.with_name(output.name + '.' + uuid.uuid4().hex + '.partial')

COMMON = [
    'NSMutableDictionary *$m = [NSMutableDictionary dictionary]',
    'id $db = (id)[(Class)objc_getClass("DicomDatabase") activeLocalDatabase]',
    'id $b = (id)[(Class)objc_getClass("BrowserController") currentBrowser]',
    'NSArray *$studies = (NSArray*)[$db objectsForEntity:(id)[$db entityForName:@"Study"] predicate:[NSPredicate predicateWithFormat:@"patientID == %@", @"PATIENT"]]',
    'id $study = [$studies firstObject]',
    'NSArray *$series = $study ? [(NSArray*)[(NSObject*)$study valueForKey:@"imageSeries"] sortedArrayUsingDescriptors:@[[NSSortDescriptor sortDescriptorWithKey:@"id" ascending:YES]]] : @[]',
    '$m[@"studies"] = @((long)[$studies count])',
    '$m[@"seriesCount"] = @((long)[$series count])',
]
WRITE = '(void)[(id)$promise filePromiseProvider:(NSFilePromiseProvider*)$promise writePromiseToURL:[NSURL fileURLWithPath:@"DEST"] completionHandler:^(NSError *e) { NSDictionary *r = @{@"error": e ? (NSString*)[e localizedDescription] : @"", @"code": @((long)(e ? [e code] : 0)), @"finishedAt": @((double)[NSDate timeIntervalSinceReferenceDate])}; (void)[[NSJSONSerialization dataWithJSONObject:r options:3 error:nil] writeToFile:@"DEST.result.json" atomically:YES]; }]'
bodies = {
    'promise': COMMON + [
        'NSMutableArray *$items = [NSMutableArray array]',
        'if ([@"LEVEL" isEqualToString:@"study"] && $study) [$items addObject:$study]',
        'if ([@"LEVEL" isEqualToString:@"series"] && (long)[$series count] > SERIESINDEX) [$items addObject:[$series objectAtIndex:SERIESINDEX]]',
        'if ([@"LEVEL" isEqualToString:@"image"] && (long)[$series count] > SERIESINDEX) [$items addObject:[(NSArray*)[(id)[$series objectAtIndex:SERIESINDEX] sortedImages] firstObject]]',
        'if ([@"LEVEL" isEqualToString:@"study+series"] && $study && [$series count]) { [$items addObject:$study]; [$items addObject:[$series firstObject]]; }',
        'double $t0 = (double)[NSDate timeIntervalSinceReferenceDate]',
        'id $promise = (id)[$b filePromiseForDatabaseObjects:$items asJPEG:ASJPEG]',
        '$m[@"promiseBuildMs"] = @(((double)[NSDate timeIntervalSinceReferenceDate] - $t0) * 1000.0)',
        '$m[@"items"] = @((long)[$items count])',
        '$m[@"promise"] = @($promise != nil)',
        '$m[@"exportName"] = (NSString*)[$promise exportName] ?: @""',
        '$m[@"fileType"] = (NSString*)[(NSFilePromiseProvider*)$promise fileType] ?: @""',
        'NSMutableArray *$types = [NSMutableArray array]',
        'for (NSString *t in (NSArray*)[(id)$promise writableTypesForPasteboard:[NSPasteboard pasteboardWithUniqueName]]) (void)[$types addObject:t]',
        '$m[@"writableTypes"] = $types',
        '$m[@"startedAt"] = @((double)[NSDate timeIntervalSinceReferenceDate])',
        'if ($promise) ' + WRITE,
    ],
    'promise-cancel': [],   # the promise body plus the cancel loop, built below
    'cancel': [
        'NSMutableDictionary *$m = [NSMutableDictionary dictionary]',
        'long $cancelled = 0',
        'for (NSThread *t in (NSArray*)[(id)[(Class)objc_getClass("ThreadsManager") defaultManager] threads]) if ([[t name] isEqualToString:@"Exporting..."]) { [t cancel]; $cancelled++; }',
        '$m[@"cancelledThreads"] = @($cancelled)',
    ],
    'pasteboard': COMMON + [
        'NSPasteboard *$pb = [NSPasteboard pasteboardWithUniqueName]',
        '(void)[$pb clearContents]',
        'NSMutableArray *$writers = [NSMutableArray array]',
        'for (id s in $series) { id w = (id)[$b filePromiseForDatabaseObjects:@[s] asJPEG:NO]; if (w) (void)[$writers addObject:w]; }',
        '$m[@"rowsWritten"] = @((BOOL)[$pb writeObjects:(NSArray*)$writers])',
        '$m[@"rows"] = @((long)[$writers count])',
        '$m[@"pasteboardItems"] = @((long)[(NSArray*)[$pb pasteboardItems] count])',
        '$m[@"aggregatedXIDs"] = @((long)[(NSArray*)[(Class)objc_getClass("BrowserController") databaseObjectXIDsOnPasteboard:$pb] count])',
        'NSString *$firstType = (NSString*)[$pb availableTypeFromArray:(NSArray*)[(Class)objc_getClass("BrowserController") DatabaseObjectXIDsPasteboardTypes]]',
        'id $firstValue = $firstType ? [$pb propertyListForType:$firstType] : nil',
        'NSArray *$firstList = (BOOL)[(NSObject*)$firstValue isKindOfClass:[NSData class]] ? (NSArray*)[NSPropertyListSerialization propertyListWithData:(NSData*)$firstValue options:0 format:NULL error:NULL] : ((BOOL)[(NSObject*)$firstValue isKindOfClass:[NSArray class]] ? (NSArray*)$firstValue : @[])',
        '$m[@"pasteboardLevelXIDs"] = @((long)[$firstList count])',
        '(void)[$pb releaseGlobally]',
    ],
    'frame': COMMON + [
        'id $first = [$series count] ? [(NSArray*)[(id)[$series objectAtIndex:SERIESINDEX] sortedImages] firstObject] : nil',
        'DCMPix *$pix = $first ? [[DCMPix alloc] initWithPath:(NSString*)[(NSObject*)$first valueForKey:@"completePath"] :0 :1 :nil :0 :0 isBonjour:NO imageObj:$first] : nil',
        'if ($pix) [$pix CheckLoad]',
        'NSData *$jpeg = $pix ? [NSBitmapImageRep representationOfImageRepsInArray:[[$pix image] representations] usingType:NSBitmapImageFileTypeJPEG properties:@{NSImageCompressionFactor: @0.9}] : nil',
        '$m[@"jpegBytes"] = @((long)[$jpeg length])',
        'id $promise = $jpeg ? (id)[$b filePromiseForJPEGData:$jpeg name:@"frame.jpg"] : nil',
        '$m[@"promise"] = @($promise != nil)',
        '$m[@"startedAt"] = @((double)[NSDate timeIntervalSinceReferenceDate])',
        'if ($promise) ' + WRITE,
    ],
    'threads': [
        'NSMutableDictionary *$m = [NSMutableDictionary dictionary]',
        'NSMutableArray *$threads = [NSMutableArray array]',
        'for (NSThread *t in (NSArray*)[(id)[(Class)objc_getClass("ThreadsManager") defaultManager] threads]) (void)[$threads addObject:@{@"name": [t name] ?: @"", @"status": (NSString*)[(NSObject*)t valueForKey:@"status"] ?: @"", @"cancelled": @((BOOL)[t isCancelled]), @"executing": @((BOOL)[t isExecuting])}]',
        '$m[@"threads"] = $threads',
        '$m[@"modal"] = (NSString*)[(NSWindow*)[(NSApplication*)NSApp modalWindow] title] ?: @"(none)"',
    ],
}
bodies['promise-cancel-after'] = bodies['promise'] + [
    # Cancel from the main run loop after the process resumes: an attach freezes
    # every thread, so a second attach can never land inside a short export.
    '(void)[NSTimer scheduledTimerWithTimeInterval:CANCELAFTER repeats:NO block:^(NSTimer *timer) { for (NSThread *t in (NSArray*)[(id)[(Class)objc_getClass("ThreadsManager") defaultManager] threads]) if ([[t name] isEqualToString:@"Exporting..."]) [t cancel]; }]',
    '$m[@"cancelScheduled"] = @YES',
]
bodies['promise-cancel'] = bodies['promise'] + [
        'long $cancelled = 0',
        'for (NSThread *t in (NSArray*)[(id)[(Class)objc_getClass("ThreadsManager") defaultManager] threads]) if ([[t name] isEqualToString:@"Exporting..."]) { [t cancel]; $cancelled++; }',
        '$m[@"cancelledThreads"] = @($cancelled)',
]

# Derived steps: the promise is built, the world changes, then the drop happens.
DELETE_IMAGES = ('NSArray *$doomed = (NSArray*)[$db objectsForEntity:(id)[$db entityForName:@"Image"] '
                 'predicate:[NSPredicate predicateWithFormat:@"series.study.patientID == %@", @"PATIENT"]]')
bodies['promise-delete'] = (bodies['promise'][:-2]
    + [DELETE_IMAGES,
       '$m[@"deletedImages"] = @((long)[$doomed count])',
       '(void)[$b proceedDeleteObjects: $doomed]',
       bodies['promise'][-2], bodies['promise'][-1]])
# The preference and the empty password are set after COMMON, which is where
# $b comes from, and before the promise captures them.
bodies['promise-encrypted'] = (COMMON
    + ['(void)[[NSUserDefaults standardUserDefaults] setBool:YES forKey:@"encryptForExport"]',
       '(void)[$b setPasswordForExportEncryption: @""]']
    + bodies['promise'][len(COMMON):]
    + ['(void)[[NSUserDefaults standardUserDefaults] setBool:NO forKey:@"encryptForExport"]',
       '$m[@"encryptRestored"] = @((BOOL)[[NSUserDefaults standardUserDefaults] boolForKey:@"encryptForExport"])'])

def substitute(line):
    return (line.replace('PATIENT', args.patient).replace('LEVEL', args.level).replace('SERIESINDEX', str(args.series_index))
            .replace('ASJPEG', 'YES' if args.mode == 'jpeg' else 'NO').replace('DEST', args.dest).replace('CANCELAFTER', repr(args.cancel_after)))


lines = [substitute(line) for line in bodies[args.step]]
lines.append('(void)[[NSJSONSerialization dataWithJSONObject:$m options:3 error:nil] writeToFile:@"%s" atomically:YES]' % staged)
commands = args.output / ('drag-' + label + '.lldb')
# One expression per statement: an exception in one leaves the rest and the record intact.
commands.write_text('expression -l objc++ -- @import AppKit\n'
                    + ''.join('expression -l objc++ -- ' + line + '\n' for line in lines) + 'process detach\n')
run = subprocess.run(['xcrun', 'lldb', '--batch', '-p', str(args.pid), '-s', str(commands)], capture_output=True, text=True)
(args.output / ('drag-' + label + '.log')).write_text(run.stdout + run.stderr)
if not staged.exists():
    print('\n'.join(sorted(set(re.findall(r'error: [^\\\n]{0,200}', run.stdout + run.stderr)))))
    raise SystemExit(1)
staged.replace(output)
print(json.dumps(json.loads(output.read_text()), indent=1, sort_keys=True))
