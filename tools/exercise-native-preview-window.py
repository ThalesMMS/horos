#!/usr/bin/env python3
"""Read the database preview's window, and what it cost, in the running app (#608).

Each step is one LLDB attach to a `--debug` development build. The attach
freezes every thread, so a step that asks the browser to change its selection
detaches and leaves the main thread to finish the work; read the result back
with a later `state`.

    python3 tools/exercise-native-preview-window.py series  --pid P
    python3 tools/exercise-native-preview-window.py select  --pid P --series mr-zero
    python3 tools/exercise-native-preview-window.py state   --pid P --label mr-zero
    python3 tools/exercise-native-preview-window.py scroll  --pid P --steps 12
    python3 tools/exercise-native-preview-window.py manual  --pid P --level 300 --width 1500
    python3 tools/exercise-native-preview-window.py decodes --pid P --reset

`state` reports the window on screen, the source the policy assigned it, the
frame being drawn, and the number of frames the process has decoded since the
counter was last reset. Every snapshot is a JSON file under local-validation;
nothing leaves the machine and no pixel values identify anyone.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess
import uuid

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument('step', choices=['series', 'select', 'state', 'scroll', 'manual', 'decodes', 'cell', 'probe'])
parser.add_argument('--pid', type=int, required=True)
parser.add_argument('--series', default='')
parser.add_argument('--steps', type=int, default=1)
parser.add_argument('--cell', type=int, default=0)
parser.add_argument('--level', type=float, default=0.0)
parser.add_argument('--width', type=float, default=0.0)
parser.add_argument('--reset', action='store_true')
parser.add_argument('--label', default=None)
parser.add_argument('--output', type=Path, default=Path('local-validation/issue-608-native'))
args = parser.parse_args()

label = args.label or args.step
if not re.fullmatch('[a-z0-9-]+', label):
    parser.error('Use a lowercase label')
args.output.mkdir(parents=True, exist_ok=True)
output = (args.output / ('preview-' + label + '.json')).resolve()
staged = output.with_name(output.name + '.' + uuid.uuid4().hex + '.partial')

COMMON = r'''
NSMutableDictionary *m608 = [NSMutableDictionary dictionary];
id br608 = (id)[(Class)objc_getClass("BrowserController") currentBrowser];
id out608 = (id)[(NSObject*)br608 valueForKey:@"databaseOutline"];
id mx608 = (id)[(NSObject*)br608 valueForKey:@"oMatrix"];
id iv608 = (id)[(NSObject*)br608 valueForKey:@"imageView"];
id sl608 = (id)[(NSObject*)br608 valueForKey:@"animationSlider"];
id pol608 = (id)[(NSObject*)br608 valueForKey:@"previewWindowPolicy"];
'''

STATE = r'''
float wl608 = 0; float ww608 = 0;
(void)[(id)iv608 getWLWW:&wl608 :&ww608];
m608[@"windowLevel"] = @((double)wl608);
m608[@"windowWidth"] = @((double)ww608);
id cur608 = (id)[(id)iv608 curDCM];
m608[@"frame"] = cur608 ? @{@"file": [(NSString*)[(id)cur608 srcFile] lastPathComponent] ?: @"", @"frameNo": @((long)[(id)cur608 frameNo]), @"isRGB": @((BOOL)[(id)cur608 isColorPreviewFrame]), @"modality": (NSString*)[(id)cur608 modalityString] ?: @"", @"savedWW": @((double)(float)[(id)cur608 savedWW]), @"savedWL": @((double)(float)[(id)cur608 savedWL]), @"pixWW": @((double)(float)[(id)cur608 ww]), @"pixWL": @((double)(float)[(id)cur608 wl]), @"revision": (NSString*)[(id)cur608 parsedFileCacheKey] ?: @""} : @{};
id applied608 = (id)[(id)pol608 appliedWindow];
id manual608 = (id)[(id)pol608 manualWindow];
m608[@"applied"] = applied608 ? @{@"level": @((double)(float)[(id)applied608 level]), @"width": @((double)(float)[(id)applied608 width]), @"source": @((long)[(id)applied608 sourceValue]), @"text": [(NSObject*)applied608 description] ?: @""} : @{};
m608[@"manual"] = manual608 ? @{@"level": @((double)(float)[(id)manual608 level]), @"width": @((double)(float)[(id)manual608 width])} : @{};
m608[@"seriesKey"] = (NSString*)[(id)pol608 seriesKey] ?: @"";
m608[@"generation"] = @((long)[(id)pol608 generation]);
m608[@"decodedFrames"] = @((unsigned long long)[(Class)objc_getClass("DCMPix") decodedFrameCount]);
m608[@"sliderValue"] = @((long)[(id)sl608 intValue]);
m608[@"sliderMax"] = @((double)(double)[(id)sl608 maxValue]);
m608[@"selectedCell"] = @((long)[(id)[(id)mx608 selectedCell] tag]);
'''

if args.step == 'series':
    body = COMMON + r'''
id db608 = (id)[(Class)objc_getClass("DicomDatabase") activeLocalDatabase];
NSMutableArray *rows608 = [NSMutableArray array];
for (id s608 in (NSArray*)[db608 objectsForEntity:(id)[db608 entityForName:@"Series"]])
  (void)[rows608 addObject:@{@"name": (NSString*)[(NSObject*)s608 valueForKey:@"name"] ?: @"", @"uid": (NSString*)[(NSObject*)s608 valueForKey:@"seriesDICOMUID"] ?: @"", @"modality": (NSString*)[(NSObject*)s608 valueForKey:@"modality"] ?: @"", @"images": (id)[(NSObject*)s608 valueForKey:@"numberOfImages"] ?: @0, @"study": (NSString*)[(NSObject*)s608 valueForKeyPath:@"study.name"] ?: @""}];
m608[@"series"] = rows608;
m608[@"outlineRows"] = @((long)[(id)out608 numberOfRows]);
''' + STATE

elif args.step == 'select':
    if not args.series:
        parser.error('select needs --series')
    body = COMMON + r'''
long found608 = -1;
for (long r608 = 0; r608 < (long)[(id)out608 numberOfRows]; r608++) {
  id item608 = (id)[(id)out608 itemAtRow: r608];
  if ((BOOL)[(id)out608 isExpandable: item608]) (void)[(id)out608 expandItem: item608];
}
for (long r608 = 0; r608 < (long)[(id)out608 numberOfRows]; r608++) {
  id item608 = (id)[(id)out608 itemAtRow: r608];
  NSString *name608 = (NSString*)[(NSObject*)item608 valueForKey:@"name"];
  if ([name608 isEqualToString: @"SERIES"]) { found608 = r608; break; }
}
m608[@"row"] = @(found608);
if (found608 >= 0) (void)[(id)out608 selectRowIndexes: [NSIndexSet indexSetWithIndex: found608] byExtendingSelection: NO];
m608[@"selectedRow"] = @((long)[(id)out608 selectedRow]);
'''.replace('SERIES', args.series) + STATE

elif args.step == 'cell':
    body = COMMON + r'''
(void)[(id)mx608 selectCellWithTag: CELL];
(void)[(id)br608 matrixPressed: mx608];
'''.replace('CELL', str(args.cell)) + STATE

elif args.step == 'scroll':
    body = COMMON + r'''
long steps608 = STEPS;
long max608 = (long)(double)[(id)sl608 maxValue];
for (long i608 = 0; i608 < steps608; i608++) {
  long next608 = ((long)[(id)sl608 intValue] + 1) % (max608 + 1);
  (void)[(id)sl608 setIntValue: (int)next608];
  (void)[(id)br608 previewSliderAction: sl608];
}
m608[@"steps"] = @(steps608);
'''.replace('STEPS', str(args.steps)) + STATE

elif args.step == 'manual':
    body = COMMON + r'''
(void)[(id)iv608 setWLWW: (float)LEVEL : (float)WIDTH];
'''.replace('LEVEL', repr(args.level)).replace('WIDTH', repr(args.width)) + STATE

elif args.step == 'probe':
    body = COMMON + r'''
id probe608 = (id)[(id)iv608 curDCM];
unsigned long long before608 = (unsigned long long)[(Class)objc_getClass("DCMPix") decodedFrameCount];
id auto608 = (id)[(id)probe608 automaticPreviewWindow];
unsigned long long afterAuto608 = (unsigned long long)[(Class)objc_getClass("DCMPix") decodedFrameCount];
id dicom608 = (id)[(id)probe608 dicomPreviewWindow];
id stored608 = (id)[(id)probe608 storedRangePreviewWindow];
unsigned long long after608 = (unsigned long long)[(Class)objc_getClass("DCMPix") decodedFrameCount];
m608[@"decodesBefore"] = @(before608);
m608[@"decodesAfterAutomatic"] = @(afterAuto608);
m608[@"decodesAfterLadder"] = @(after608);
m608[@"automatic"] = auto608 ? [(NSObject*)auto608 description] : @"";
m608[@"dicom"] = dicom608 ? [(NSObject*)dicom608 description] : @"";
m608[@"storedRange"] = stored608 ? [(NSObject*)stored608 description] : @"";
''' + STATE

elif args.step == 'state':
    body = COMMON + STATE

elif args.step == 'decodes':
    body = COMMON + STATE + (
        '(void)[(Class)objc_getClass("DCMPix") resetDecodedFrameCount];\n' if args.reset else '')

expr = body + '(void)[[NSJSONSerialization dataWithJSONObject:m608 options:3 error:nil] writeToFile:@"STAGED" atomically:YES];\n'
expr = expr.replace('STAGED', str(staged))
commands = args.output / ('preview-' + label + '.lldb')
commands.write_text('expression -l objc++ -- @import AppKit\n'
                    'expression -l objc++ -- { ' + ' '.join(expr.splitlines()) + ' }\nprocess detach\n')
run = subprocess.run(['xcrun', 'lldb', '--batch', '-p', str(args.pid), '-s', str(commands)],
                     capture_output=True, text=True)
(args.output / ('preview-' + label + '.log')).write_text(run.stdout + run.stderr)
if not staged.exists():
    print(run.stdout[-3000:])
    print(run.stderr[-3000:])
    raise SystemExit('the step produced no snapshot; see %s' % (args.output / ('preview-' + label + '.log')))
staged.replace(output)
print(output)
print(json.dumps(json.loads(output.read_text()), indent=1)[:4000])
