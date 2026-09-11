#!/usr/bin/env python3
"""Read the flip state of every open 2D viewer from a running Horos (#598).

Attaches LLDB to the development process (which needs get-task-allow) and
writes one JSON snapshot per label. Used for the workspace flip round trip;
see docs/workspace-flip-validation.md. Logs and snapshots stay local.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess
import uuid

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('label')
parser.add_argument('--pid', type=int, required=True)
parser.add_argument('--set', action='append', default=[], metavar='TITLE=X,Y',
                    help='before reading, set flips on the viewer whose title contains TITLE (X,Y in 0/1)')
parser.add_argument('--output', type=Path, default=Path('local-validation/issue-598-native'))
args = parser.parse_args()
if args.pid <= 0 or not re.fullmatch('[a-z0-9-]+', args.label):
    parser.error('Use a positive PID and a lowercase snapshot label')
args.output.mkdir(parents=True, exist_ok=True)
output = (args.output / (args.label + '.json')).resolve()
staged = output.with_name(output.name + '.' + uuid.uuid4().hex + '.partial')

setters = ''
for spec in args.set:
    title, flags = spec.split('=')
    x, y = (int(v) for v in flags.split(','))
    if not re.fullmatch('[A-Za-z0-9 ()]+', title):
        parser.error('title must be plain text')
    setters += ('for(id f598Vc in (id)[(id)objc_getClass("ViewerController") get2DViewers]) {'
                ' if([[(NSWindow*)[f598Vc window] title] containsString:@"%s"]) {'
                ' (void)[f598Vc setXFlipped:(BOOL)%d]; (void)[f598Vc setYFlipped:(BOOL)%d]; } }\n' % (title, x, y))

expression = setters + r'''
NSMutableArray *f598Viewers=[NSMutableArray array];
for(id f598Vc in (id)[(id)objc_getClass("ViewerController") get2DViewers]) {
NSWindow *f598Window=(id)[f598Vc window]; id f598Image=(id)[f598Vc imageView]; id f598Series=(id)[f598Image seriesObj];
NSMutableDictionary *f598V=[NSMutableDictionary dictionary];
f598V[@"controller"]=[NSString stringWithFormat:@"%p",f598Vc];
f598V[@"title"]=f598Window.title ?: @"";
f598V[@"seriesInstanceUID"]=(id)[f598Series valueForKey:@"seriesInstanceUID"] ?: @"";
f598V[@"xFlipped"]=@((BOOL)[f598Image xFlipped]);
f598V[@"yFlipped"]=@((BOOL)[f598Image yFlipped]);
f598V[@"seriesXFlipped"]=(id)[f598Series valueForKey:@"xFlipped"] ?: [NSNull null];
f598V[@"seriesYFlipped"]=(id)[f598Series valueForKey:@"yFlipped"] ?: [NSNull null];
f598V[@"rotation"]=@((double)[f598Image rotation]);
f598V[@"scale"]=@((double)[f598Image scaleValue]);
f598V[@"currentImage"]=@((long)[f598Image curImage]);
[f598Viewers addObject:f598V];
}
NSDictionary *f598State=@{@"viewers":f598Viewers};
[[NSJSONSerialization dataWithJSONObject:f598State options:3 error:nil]writeToFile:OUTPUT atomically:YES];
'''.replace('OUTPUT', '@' + json.dumps(str(staged)))
commands = args.output / (args.label + '.lldb')
commands.write_text('expression -l objc++ -- @import AppKit\n'
                    'expression -l objc++ -- { ' + ' '.join(expression.splitlines()) + ' }\n'
                    'process detach\n')
result = subprocess.run(['xcrun', 'lldb', '--batch', '-p', str(args.pid), '-s', str(commands)],
                        capture_output=True, text=True)
(args.output / (args.label + '.log')).write_text(result.stdout + result.stderr)
if result.returncode or not staged.exists():
    raise SystemExit('Capture failed; inspect the local LLDB log')
staged.replace(output)
state = json.loads(output.read_text())
for v in state['viewers']:
    print('%s: x=%d y=%d (series %s/%s)' % (v['title'].strip(), v['xFlipped'], v['yFlipped'],
                                          v['seriesXFlipped'], v['seriesYFlipped']))
