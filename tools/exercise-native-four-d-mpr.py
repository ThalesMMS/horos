#!/usr/bin/env python3
"""Open a synthetic 4D study as a movie viewer and drive its play control (A224, #374).

Three steps, each an LLDB attach to the development process:

    python3 tools/exercise-native-four-d-mpr.py open --pid 123 --study 'LOCAL^MPR-4D-ROI'
    python3 tools/exercise-native-four-d-mpr.py state --pid 123 --label before
    python3 tools/exercise-native-four-d-mpr.py press --pid 123 --label playing
    python3 tools/exercise-native-four-d-mpr.py press --pid 123 --label stopped

`open` fetches the study's image series from the browser's own database
context, sorted as the browser sorts them, and calls the same method the 4D
Viewer button ends in (`openViewerFromImages:movie:YES viewer:nil
keyImagesOnly:NO`). `state` reads the 2D viewer's play control (its title,
whether it is enabled, whether the movie timer exists, the phase index and
count). `press` sends the play control's own action and then reads the
state. Every snapshot is a JSON file; nothing leaves local-validation.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess
import uuid

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('step', choices=['open', 'state', 'press'])
parser.add_argument('--pid', type=int, required=True)
parser.add_argument('--study', default='LOCAL^MPR-4D-ROI')
parser.add_argument('--label', default=None)
parser.add_argument('--output', type=Path, default=Path('local-validation/issue-374-native'))
args = parser.parse_args()
label = args.label or args.step
if args.pid <= 0 or not re.fullmatch('[a-z0-9-]+', label) or not re.fullmatch(r'[A-Za-z0-9^ _-]+', args.study):
    parser.error('Use a positive PID, a lowercase label and a plain study name')
args.output.mkdir(parents=True, exist_ok=True)
output = (args.output / ('four-d-' + label + '.json')).resolve()
staged = output.with_name(output.name + '.' + uuid.uuid4().hex + '.partial')

if args.step == 'open':
    body = r'''
id m374B = (id)[(id)objc_getClass("BrowserController") currentBrowser];
NSManagedObjectContext *m374Ctx = (NSManagedObjectContext *)[(id)[m374B database] managedObjectContext];
NSFetchRequest *m374Req = [NSFetchRequest fetchRequestWithEntityName:@"Study"];
m374Req.predicate = [NSPredicate predicateWithFormat:@"name == %@", @"STUDY"];
NSArray *m374Studies = [m374Ctx executeFetchRequest:m374Req error:nil];
NSMutableDictionary *m374S = [NSMutableDictionary dictionary];
m374S[@"studies"] = @(m374Studies.count);
if (m374Studies.count == 1) {
  id m374Study = m374Studies.firstObject;
  NSArray *m374Series = [(NSArray *)[m374Study valueForKey:@"imageSeries"] sortedArrayUsingDescriptors:@[[NSSortDescriptor sortDescriptorWithKey:@"name" ascending:YES]]];
  NSMutableArray *m374Open = [NSMutableArray array];
  NSMutableArray *m374Names = [NSMutableArray array];
  for (id m374Serie in m374Series) { (void)[m374Open addObject:(id)[m374Serie sortedImages]]; (void)[m374Names addObject:(id)[m374Serie valueForKey:@"name"] ?: @""]; }
  m374S[@"series"] = m374Names;
  id m374Viewer = (id)[m374B openViewerFromImages:m374Open movie:YES viewer:nil keyImagesOnly:NO];
  m374S[@"viewer"] = [NSString stringWithFormat:@"%p", m374Viewer];
  m374S[@"maxMovieIndex"] = @((long)[m374Viewer maxMovieIndex]);
}
(void)[[NSJSONSerialization dataWithJSONObject:m374S options:3 error:nil] writeToFile:OUTPUT atomically:YES];
'''.replace('STUDY', args.study)
else:
    press = '(void)[(NSButton *)(id)[(NSObject *)m374V valueForKey:@"moviePlayStop"] performClick:nil];\n' if args.step == 'press' else ''
    body = r'''
id m374V = nil;
for (id m374C in (NSArray *)[(id)objc_getClass("ViewerController") get2DViewers]) { if ((long)[m374C maxMovieIndex] > 1) { m374V = m374C; break; } }
NSMutableDictionary *m374S = [NSMutableDictionary dictionary];
if (m374V) {
PRESS
NSButton *m374Button = (NSButton *)[(NSObject *)m374V valueForKey:@"moviePlayStop"];
m374S[@"viewer"] = [NSString stringWithFormat:@"%p", m374V];
m374S[@"title"] = m374Button.title ?: @"";
m374S[@"enabled"] = @(m374Button.isEnabled);
m374S[@"accessibilityLabel"] = (id)[m374Button accessibilityLabel] ?: @"";
m374S[@"timerRunning"] = @((id)[(NSObject *)m374V valueForKey:@"movieTimer"] != nil);
m374S[@"maxMovieIndex"] = @((long)[m374V maxMovieIndex]);
m374S[@"curMovieIndex"] = @((long)[m374V curMovieIndex]);
m374S[@"sliderEnabled"] = @(((NSSlider *)[(NSObject *)m374V valueForKey:@"moviePosSlider"]).isEnabled);
}
(void)[[NSJSONSerialization dataWithJSONObject:m374S options:3 error:nil] writeToFile:OUTPUT atomically:YES];
'''.replace('PRESS', press)
expression = body.replace('OUTPUT', '@' + json.dumps(str(staged)))
commands = args.output / ('four-d-' + label + '.lldb')
commands.write_text('expression -l objc++ -- @import AppKit\n'
                    'expression -l objc++ -- { ' + ' '.join(expression.splitlines()) + ' }\n'
                    'process detach\n')
result = subprocess.run(['xcrun', 'lldb', '--batch', '-p', str(args.pid), '-s', str(commands)],
                        capture_output=True, text=True)
(args.output / ('four-d-' + label + '.log')).write_text(result.stdout + result.stderr)
if result.returncode or not staged.exists():
    raise SystemExit('Step failed; inspect the local LLDB log')
staged.replace(output)
print(label + ': ' + json.dumps(json.loads(output.read_text())))
