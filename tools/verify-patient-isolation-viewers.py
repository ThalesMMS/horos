#!/usr/bin/env python3
"""Exercise synthetic series through a debug Horos process and check loaded pixels.

Requires a development app launched with --debug and detached from LLDB.
This changes viewer windows, not DICOM files. Outputs are local test evidence.
It checks DCMPix buffers, not compositor pixels or hardware scroll events.
"""
import argparse
import base64
import json
from pathlib import Path
import random
import subprocess
import time

import numpy as np
import pydicom


def objc(value):
    return '@' + json.dumps(str(value))


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('pid', type=int)
parser.add_argument('fixture', type=Path)
parser.add_argument('output', type=Path)
parser.add_argument('--limit', type=int, default=80)
parser.add_argument('--start', type=int, default=0, help='Start offset in the deterministic series order')
args = parser.parse_args()
exe = subprocess.check_output(['ps', '-p', str(args.pid), '-o', 'comm='], text=True).strip()
if not exe.endswith('/HorosDevelopment.app/Contents/MacOS/Horos'):
    parser.error('PID must identify the isolated HorosDevelopment app')
args.output.mkdir(parents=True, exist_ok=True)
if any(args.output.iterdir()):
    parser.error('Use an empty output directory')
records = json.loads((args.fixture / 'manifest.json').read_text())
groups = {}
for record in records:
    assert record['patient'].startswith('LOCAL-ISOLATION-')
    groups.setdefault(record['series'], []).append(record)
series = sorted(groups)
random.Random(3).shuffle(series)
if not 0 <= args.start < len(series):
    parser.error('--start is outside the fixture series range')
if not 1 <= args.limit <= len(series):
    parser.error('--limit must be between 1 and the fixture series count')


def run_lldb(label, expressions):
    commands = args.output / (label + '.lldb')
    commands.write_text('expr -l objc++ -- @import Cocoa\nexpr -l objc++ -- @import CoreData\n' +
                        '\n'.join('expr -l objc++ -- ' + x for x in expressions) + '\n')
    # Evaluating Cocoa while stopped inside an allocator can recursively acquire
    # an internal lock. Only evaluate when the main thread is waiting for events.
    for attempt in range(10):
        wrapper = args.output / (label + f'-attempt-{attempt}.lldb')
        source = 'command source ' + json.dumps(str(commands.resolve()))
        wrapper.write_text('thread select 1\nscript import lldb\n' +
            'script lldb.debugger.HandleCommand(' + repr(source) + ') if ' +
            'lldb.debugger.GetSelectedTarget().GetProcess().GetSelectedThread().GetFrameAtIndex(0).GetFunctionName() == "mach_msg2_trap" and any("CFRunLoopServiceMachPort" in (f.GetFunctionName() or "") for f in lldb.debugger.GetSelectedTarget().GetProcess().GetSelectedThread()) ' +
            'else print("HOROS_TEST_NOT_IDLE")\ndetach\nquit\n')
        result = subprocess.run(['/usr/bin/lldb', '-b', '-p', str(args.pid), '-s', str(wrapper)],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=60)
        (args.output / (label + f'-attempt-{attempt}.log')).write_text(result.stdout)
        if 'HOROS_TEST_NOT_IDLE\n' in result.stdout:
            time.sleep(0.3)
            continue
        if result.returncode or any('error:' in line for line in result.stdout.splitlines() if not line.startswith('(lldb)')) or 'Traceback (most recent call last)' in result.stdout:
            raise RuntimeError(f'LLDB failed: see {label}-attempt-{attempt}.log')
        return
    raise RuntimeError(f'Main thread did not reach its event wait: {label}')


results = []
for index, uid in enumerate(series[args.start:args.start + args.limit], start=args.start):
    group = groups[uid]
    label = f'{index:03}'
    run_lldb(label + '-open', [
        'id b = (id)[NSClassFromString(@"BrowserController") currentBrowser]; '
        'NSManagedObjectContext *c = (NSManagedObjectContext*)[(id)[b database] managedObjectContext]; '
        'NSFetchRequest *r = [NSFetchRequest fetchRequestWithEntityName:@"Series"]; '
        f'[r setPredicate:[NSPredicate predicateWithFormat:@"seriesDICOMUID == %@", {objc(uid)}]]; '
        'NSArray *a = [c executeFetchRequest:r error:NULL]; '
        f'if ([a count] != 1 || ![(NSString*)[(NSManagedObject*)[a firstObject] valueForKeyPath:@"study.patientID"] isEqualToString:{objc(group[0]["patient"])}]) '
        '{ printf("error: synthetic series not uniquely found\\n"); } '
        'else { NSManagedObject *s = (NSManagedObject*)[a firstObject]; '
        '[[NSOperationQueue mainQueue] addOperationWithBlock:^{ '
        'NSArray *old = (NSArray*)[(NSArray*)[NSClassFromString(@"ViewerController") getDisplayed2DViewers] copy]; '
        'NSUInteger kept = 0; for (id viewer in old) { '
        'NSManagedObject *image = (NSManagedObject*)[(NSArray*)[viewer fileList] firstObject]; '
        'NSString *patient = (NSString*)[image valueForKeyPath:@"series.study.patientID"]; '
        'if ([patient hasPrefix:@"LOCAL-ISOLATION-"] && kept++ >= 1) [(NSWindow*)[viewer window] performClose:nil]; } '
        '(void)[b displayStudy:[s valueForKey:@"study"] object:s command:@"Open"]; }]; }'
    ])
    time.sleep(0.3)  # Let the application's event loop load and present the series.
    snapshot = (args.output / (label + '.json')).resolve()
    run_lldb(label + '-capture', [
        'id v = (id)[NSClassFromString(@"ViewerController") frontMostDisplayed2DViewer]; '
        'NSArray *p = (NSArray*)[v pixList], *f = (NSArray*)[v fileList]; '
        'NSMutableArray *rows = [NSMutableArray array]; '
        'if ([p count] != [f count]) { printf("error: image/pixel count mismatch\\n"); } '
        'else { for (NSUInteger i = 0; i < [p count]; ++i) { '
        'id pix = [p objectAtIndex:i]; NSManagedObject *file = (NSManagedObject*)[f objectAtIndex:i]; '
        f'if (![(NSString*)[file valueForKeyPath:@"series.study.patientID"] isEqualToString:{objc(group[0]["patient"])}]) '
        '{ printf("error: unexpected patient\\n"); break; } '
        'long w = (long)[pix pwidth], h = (long)[pix pheight]; '
        'if (w != 128 || h != 128) { printf("error: unexpected dimensions\\n"); break; } '
        'NSData *bytes = [NSData dataWithBytes:(float*)[pix fImage] length:w*h*sizeof(float)]; '
        '[rows addObject:@{@"path":(NSString*)[pix srcFile], @"patient":[file valueForKeyPath:@"series.study.patientID"], '
        '@"series":[file valueForKeyPath:@"series.seriesDICOMUID"], @"pixels":[bytes base64EncodedStringWithOptions:0]}]; } '
        f'[[NSJSONSerialization dataWithJSONObject:rows options:0 error:NULL] writeToFile:{objc(snapshot)} atomically:YES]; }}'
    ])
    captured = json.loads(snapshot.read_text())
    expected = {r['sop']: r for r in group}
    assert len(captured) == len(expected)
    seen = set()
    for row in captured:
        ds = pydicom.dcmread(row['path'])
        sop = str(ds.SOPInstanceUID)
        assert sop in expected and sop not in seen
        seen.add(sop)
        assert row['patient'] == expected[sop]['patient'] and row['series'] == uid
        original = pydicom.dcmread(args.fixture / expected[sop]['path'])
        actual = np.frombuffer(base64.b64decode(row['pixels']), dtype=np.float32).reshape(128, 128)
        np.testing.assert_array_equal(actual, original.pixel_array.astype(np.float32))
    results.append(dict(patient=group[0]['patient'], series=uid, instances=len(seen)))
    (args.output / 'results.json').write_text(json.dumps(results, indent=2) + '\n')
    print(f'PASS {index + 1}/{min(args.start + args.limit, len(series))}: {group[0]["patient"]}, {len(seen)} complete pixel buffers', flush=True)
print('All requested viewer buffers match the synthetic originals')
