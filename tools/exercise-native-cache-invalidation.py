#!/usr/bin/env python3
"""Replace a DICOM under the running development app and read what each cache serves (#603).

Steps, each an LLDB attach to the development process (a `--debug` build):

    python3 tools/exercise-native-cache-invalidation.py paths    --pid P --sops a,b,c
    python3 tools/exercise-native-cache-invalidation.py probe    --pid P --path /db/…/12.dcm --label before
    python3 tools/exercise-native-cache-invalidation.py pref     --pid P --replace-incoming YES
    python3 tools/exercise-native-cache-invalidation.py incoming --pid P --dir fixture/v2-pixels

Replacement itself is done outside the process, by this script, with no LLDB:

    python3 tools/exercise-native-cache-invalidation.py replace --path /db/…/12.dcm --with v2/01.dcm --mode rename
    python3 tools/exercise-native-cache-invalidation.py replace --path /db/…/12.dcm --with v2/01.dcm --mode inplace

`probe` reads three things for one database path: every pix an open 2D viewer
holds for that path (centre sample, size, origin, orientation, and whether it
says its file still matches the disk); a fresh `DCMPix` created for the path in
the process and decoded now; and what the browser's preview reuse returns for
the path. Every snapshot is a JSON file; nothing leaves local-validation.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import uuid

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument('step', choices=['paths', 'probe', 'pref', 'incoming', 'replace'])
parser.add_argument('--pid', type=int, default=0)
parser.add_argument('--sops', default='')
parser.add_argument('--path', default='')
parser.add_argument('--with', dest='replacement', default='')
parser.add_argument('--mode', choices=['rename', 'inplace'], default='rename')
parser.add_argument('--dir', type=Path, default=None)
parser.add_argument('--replace-incoming', choices=['YES', 'NO'], default='YES')
parser.add_argument('--skip-reuse', action='store_true', help='probe: do not ask the browser preview to reuse (its database rows may be gone)')
parser.add_argument('--label', default=None)
parser.add_argument('--output', type=Path, default=Path('local-validation/issue-603-native'))
args = parser.parse_args()
label = args.label or args.step
if not re.fullmatch('[a-z0-9-]+', label):
    parser.error('Use a lowercase label')
args.output.mkdir(parents=True, exist_ok=True)
output = (args.output / ('cache-' + label + '.json')).resolve()

if args.step == 'replace':
    if not args.path or not args.replacement:
        parser.error('replace needs --path and --with')
    target = Path(args.path)
    source = Path(args.replacement)
    before = os.stat(target)
    if args.mode == 'rename':
        staging = target.with_name('.replace-' + uuid.uuid4().hex)
        shutil.copyfile(source, staging)
        os.replace(staging, target)
    else:
        data = source.read_bytes()
        with open(target, 'r+b') as handle:
            handle.seek(0)
            handle.write(data)
            handle.truncate(len(data))
    after = os.stat(target)
    record = {'path': str(target), 'with': str(source), 'mode': args.mode,
              'inodeBefore': before.st_ino, 'inodeAfter': after.st_ino,
              'sizeBefore': before.st_size, 'sizeAfter': after.st_size,
              'mtimeChanged': before.st_mtime_ns != after.st_mtime_ns,
              'ctimeChanged': before.st_ctime_ns != after.st_ctime_ns}
    output.write_text(json.dumps(record, indent=1))
    print(json.dumps(record))
    raise SystemExit(0)

if args.pid <= 0:
    parser.error('this step needs --pid')
staged = output.with_name(output.name + '.' + uuid.uuid4().hex + '.partial')

COMMON = r'''
NSMutableDictionary *m603 = [NSMutableDictionary dictionary];
id db603 = (id)[(Class)objc_getClass("DicomDatabase") activeLocalDatabase];
'''

if args.step == 'paths':
    sops = [s for s in args.sops.split(',') if s]
    if not sops:
        parser.error('paths needs --sops')
    body = COMMON + r'''
NSArray *wanted603 = @[SOPS];
NSMutableDictionary *paths603 = [NSMutableDictionary dictionary];
for (id im603 in (NSArray*)[db603 objectsForEntity:(id)[db603 entityForName:@"Image"] predicate:[NSPredicate predicateWithFormat:@"sopInstanceUID IN %@", wanted603]])
  paths603[(NSString*)[(NSObject*)im603 valueForKey:@"sopInstanceUID"]] = @{@"path": (NSString*)[(NSObject*)im603 valueForKey:@"completePath"] ?: @"", @"pathNumber": (id)[(NSObject*)im603 valueForKey:@"pathNumber"] ?: @0, @"width": (id)[(NSObject*)im603 valueForKey:@"width"] ?: @0, @"height": (id)[(NSObject*)im603 valueForKey:@"height"] ?: @0, @"frames": (id)[(NSObject*)im603 valueForKey:@"numberOfFrames"] ?: @0};
m603[@"images"] = paths603;
m603[@"incoming"] = (NSString*)[db603 incomingDirPath] ?: @"";
'''.replace('SOPS', ', '.join('@"%s"' % s for s in sops))

elif args.step == 'probe':
    if not args.path:
        parser.error('probe needs --path')
    body = COMMON + r'''
NSString *path603 = @"PATH";
NSMutableArray *held603 = [NSMutableArray array];
for (id v603 in (NSArray*)[(Class)objc_getClass("ViewerController") get2DViewers]) {
  for (long t603 = 0; t603 < (long)[v603 maxMovieIndex]; t603++) {
    for (DCMPix *p603 in (NSArray*)[v603 pixList: t603]) {
      if ([(NSString*)[p603 srcFile] isEqualToString:path603] == NO) continue;
      float *f603 = (float*)[p603 fImage];
      long w603 = (long)[p603 pwidth], h603 = (long)[p603 pheight];
      float o603[9]; [p603 orientation: o603];
      (void)[held603 addObject:@{@"series": (NSString*)[(NSObject*)[v603 currentSeries] valueForKey:@"name"] ?: @"",
        @"width": @(w603), @"height": @(h603),
        @"centre": @((double)(f603 ? f603[(h603/2)*w603 + w603/2] : -99999)),
        @"originX": @((double)[p603 originX]), @"originY": @((double)[p603 originY]), @"originZ": @((double)[p603 originZ]),
        @"orientation": @[@((double)o603[0]), @((double)o603[1]), @((double)o603[2]), @((double)o603[3]), @((double)o603[4]), @((double)o603[5])],
        @"sliceInterval": @((double)[p603 sliceInterval]), @"frames": @((long)[p603 frameNo]),
        @"loadedFileMatchesDisk": @((BOOL)[p603 loadedFileMatchesDisk]),
        @"loadedRevision": [(NSObject*)[p603 loadedFileRevision] description] ?: @""}];
    }
  }
}
m603[@"heldByViewers"] = held603;
DCMPix *fresh603 = [[DCMPix alloc] initWithPath: path603 :0 :1 :nil :0 :0 isBonjour: NO imageObj: nil];
if (fresh603) {
  [fresh603 CheckLoad];
  float *g603 = (float*)[fresh603 fImage];
  long fw603 = (long)[fresh603 pwidth], fh603 = (long)[fresh603 pheight];
  float fo603[9]; [fresh603 orientation: fo603];
  m603[@"fresh"] = @{@"width": @(fw603), @"height": @(fh603),
    @"centre": @((double)(g603 ? g603[(fh603/2)*fw603 + fw603/2] : -99999)),
    @"originX": @((double)[fresh603 originX]), @"originY": @((double)[fresh603 originY]), @"originZ": @((double)[fresh603 originZ]),
    @"orientation": @[@((double)fo603[0]), @((double)fo603[1]), @((double)fo603[2]), @((double)fo603[3]), @((double)fo603[4]), @((double)fo603[5])],
    @"loadedFileMatchesDisk": @((BOOL)[fresh603 loadedFileMatchesDisk]),
    @"parsedFileCacheKey": (NSString*)[fresh603 parsedFileCacheKey] ?: @"",
    @"loadedRevision": [(NSObject*)[fresh603 loadedFileRevision] description] ?: @""};
} else m603[@"fresh"] = @{@"error": @"DCMPix could not be created for the path"};
DCMPix *reuse603 = SKIPREUSE ? nil : (DCMPix*)[(id)[(Class)objc_getClass("BrowserController") currentBrowser] getDCMPixFromViewerIfAvailable: path603 frameNumber: 0];
if (reuse603) {
  float *r603 = (float*)[reuse603 fImage];
  long rw603 = (long)[reuse603 pwidth], rh603 = (long)[reuse603 pheight];
  m603[@"previewReuse"] = @{@"reused": @YES, @"width": @(rw603), @"height": @(rh603), @"centre": @((double)(r603 ? r603[(rh603/2)*rw603 + rw603/2] : -99999))};
} else m603[@"previewReuse"] = @{@"reused": @NO};
m603[@"diskRevision"] = (NSString*)[(Class)objc_getClass("HorosFileRevision") cacheKeyForPath: path603] ?: @"";
'''.replace('PATH', args.path).replace('SKIPREUSE', 'YES' if args.skip_reuse else 'NO')

elif args.step == 'pref':
    body = COMMON + r'''
[[NSUserDefaults standardUserDefaults] setBool: FLAG forKey: @"REPLACE_WITH_NEW_INCOMING_FILE"];
m603[@"REPLACE_WITH_NEW_INCOMING_FILE"] = @((BOOL)[[NSUserDefaults standardUserDefaults] boolForKey: @"REPLACE_WITH_NEW_INCOMING_FILE"]);
'''.replace('FLAG', args.replace_incoming)

elif args.step == 'incoming':
    if not args.dir or not args.dir.is_dir():
        parser.error('incoming needs --dir')
    files = sorted(str(p.resolve()) for p in args.dir.glob('*.dcm'))
    body = COMMON + r'''
NSString *incoming603 = (NSString*)[db603 incomingDirPath];
long queued603 = 0;
for (NSString *file603 in @[FILES]) {
  NSString *dest603 = [incoming603 stringByAppendingPathComponent: [[[NSUUID UUID] UUIDString] stringByAppendingPathExtension: @"dcm"]];
  if ([[NSFileManager defaultManager] copyItemAtPath: file603 toPath: dest603 error: nil]) queued603++;
}
m603[@"queued"] = @(queued603);
m603[@"incoming"] = incoming603 ?: @"";
'''.replace('FILES', ', '.join('@"%s"' % f for f in files))

expr = body + '(void)[[NSJSONSerialization dataWithJSONObject:m603 options:3 error:nil] writeToFile:@"STAGED" atomically:YES];\n'
expr = expr.replace('STAGED', str(staged))
commands = args.output / ('cache-' + label + '.lldb')
commands.write_text('expression -l objc++ -- @import AppKit\n'
                    'expression -l objc++ -- { ' + ' '.join(expr.splitlines()) + ' }\nprocess detach\n')
run = subprocess.run(['xcrun', 'lldb', '--batch', '-p', str(args.pid), '-s', str(commands)],
                     capture_output=True, text=True)
(args.output / ('cache-' + label + '.log')).write_text(run.stdout + run.stderr)
if not staged.exists():
    print('\n'.join(sorted(set(re.findall(r'error: [^\\\n]{0,200}', run.stdout + run.stderr)))))
    raise SystemExit(1)
staged.replace(output)
print(json.dumps(json.loads(output.read_text()), indent=1, sort_keys=True))
