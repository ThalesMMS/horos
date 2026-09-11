#!/usr/bin/env python3
"""Check which frame the database preview reuses from an open viewer (#380 D).

With the synthetic multiframe series open in a 2D viewer and selected in the
browser, this reports, from the live objects:

- the index the *old* rule would have taken (the first entry of the viewer's
  file list whose `completePath` matches, which is what `indexOfObject:` on the
  paths returns) and the frame number stored there;
- the index the current rule takes (path and frame), and the frame number of
  the `DCMPix` the browser hands back for the requested frame;
- the frame the preview view is actually showing, and its mean value, which the
  fixture makes unique per frame.

The path matched is the one the viewer holds: the database keeps its own copy of
an imported file, so the fixture's own path is not what is stored.

`--reverse` reverses the open viewer's image order first, which is the state
where the two rules disagree: the first entry for the file is then the last
frame.

    python3 tools/exercise-native-preview-identity.py --pid N --reverse
"""
import argparse
import json
from pathlib import Path
import re
import subprocess
import uuid

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--pid', type=int, required=True)
parser.add_argument('--fixture', type=Path, default=Path('../DICOM_Example/local-validation/issue-380-multiframe-2026-09-13'))
parser.add_argument('--reverse', action='store_true', help="reverse the open viewer's image order first")
parser.add_argument('--frame', type=int, default=0, help='the frame the preview asks for')
parser.add_argument('--label', default='preview-identity')
parser.add_argument('--output', type=Path, default=Path('local-validation/issue-380-native'))
args = parser.parse_args()
if args.pid <= 0 or not re.fullmatch('[a-z0-9-]+', args.label):
    parser.error('positive PID and a lowercase label')
manifest = json.loads((args.fixture / 'manifest.json').read_text())
args.output.mkdir(parents=True, exist_ok=True)
out_dir = args.output.resolve()
report = out_dir / (args.label + '.json')
staged = report.with_name(report.name + '.' + uuid.uuid4().hex + '.partial')


def s(value):
    return '@' + json.dumps(str(value))


expression = r'''
NSMutableDictionary *p380 = [NSMutableDictionary dictionary];
id br380 = (id)[(id)objc_getClass("BrowserController") currentBrowser];
id vc380 = nil;
for (id c in (NSArray*)[(id)objc_getClass("ViewerController") get2DViewers]) {
  NSString *uid380 = (NSString*)[(NSObject*)[c currentSeries] valueForKey:@"seriesDICOMUID"];
  if (uid380 && [uid380 isKindOfClass:(Class)objc_getClass("NSString")] && [uid380 isEqualToString:SERIES]) vc380 = c;
}
p380[@"viewer"] = @(vc380 != nil);
if (vc380) {
  REVERSE
  NSArray *files380 = (NSArray*)[vc380 fileList];
  p380[@"fileCount"] = @((long)[files380 count]);
  NSString *PATHVAR = (NSString*)[(NSObject*)[files380 objectAtIndex:0] valueForKey:@"completePath"] ?: @"";
  p380[@"path"] = PATHVAR;
  long old380 = -1, new380 = -1, oldFrame380 = -1;
  for (long i380 = 0; i380 < (long)[files380 count]; i380++) {
    id im380 = (id)[files380 objectAtIndex:i380];
    NSString *path380 = (NSString*)[(NSObject*)im380 valueForKey:@"completePath"];
    if (!path380 || ![path380 isEqualToString:PATHVAR]) continue;
    if (old380 < 0) { old380 = i380; oldFrame380 = (long)[(NSNumber*)[(NSObject*)im380 valueForKey:@"frameID"] intValue]; }
    if ((long)[(NSNumber*)[(NSObject*)im380 valueForKey:@"frameID"] intValue] == FRAME && new380 < 0) new380 = i380;
  }
  p380[@"firstPathMatchIndex"] = @(old380);
  p380[@"firstPathMatchFrame"] = @(oldFrame380);
  p380[@"pathAndFrameMatchIndex"] = @(new380);
  id first380 = nil;
  for (id im380 in files380) if ([(NSString*)[(NSObject*)im380 valueForKey:@"completePath"] isEqualToString:PATHVAR] && (long)[(NSNumber*)[(NSObject*)im380 valueForKey:@"frameID"] intValue] == FRAME) { first380 = im380; break; }
  if (first380) {
    id expected380 = (id)[(id)[(Class)objc_getClass("HorosPreviewFrame") alloc] initWithPath:PATHVAR
      sopInstanceUID:(NSString*)[(NSObject*)first380 valueForKey:@"sopInstanceUID"] ?: @""
      seriesInstanceUID:SERIES sopClassUID:@"1.2.840.10008.5.1.4.1.1.2.1" modality:@"CT"
      frameNumber:(long)FRAME frameCount:(long)[(NSNumber*)[(NSObject*)first380 valueForKey:@"numberOfFrames"] intValue]
      rows:(long)[(NSNumber*)[(NSObject*)first380 valueForKey:@"height"] intValue]
      columns:(long)[(NSNumber*)[(NSObject*)first380 valueForKey:@"width"] intValue]
      seriesID:(long)[(NSNumber*)[(NSObject*)first380 valueForKeyPath:@"series.id"] intValue]];
    id pix380 = (id)[br380 getDCMPixFromViewerIfAvailable:PATHVAR frameNumber:(int)FRAME expectedFrame:expected380];
    p380[@"reusedFrame"] = @(pix380 ? (long)[pix380 frameNo] : -1);
    if (pix380) {
      float *f380 = (float*)[pix380 fImage];
      long n380 = (long)[pix380 pwidth] * (long)[pix380 pheight];
      double sum380 = 0; if (f380) for (long i380 = 0; i380 < n380; i380++) sum380 += f380[i380];
      p380[@"reusedMean"] = @(n380 ? sum380 / n380 : -1);
    }
  }
  id preview380 = (id)[(NSObject*)br380 valueForKey:@"imageView"];
  id cur380 = (id)[preview380 curDCM];
  p380[@"previewFrame"] = @(cur380 ? (long)[cur380 frameNo] : -1);
  p380[@"previewSource"] = (NSString*)[cur380 srcFile] ?: @"";
  if (cur380) {
    float *f380 = (float*)[cur380 fImage];
    long n380 = (long)[cur380 pwidth] * (long)[cur380 pheight];
    double sum380 = 0; if (f380) for (long i380 = 0; i380 < n380; i380++) sum380 += f380[i380];
    p380[@"previewMean"] = @(n380 ? sum380 / n380 : -1);
  }
}
'''
reverse = r'''
{ NSMutableArray *list380 = (NSMutableArray*)[vc380 fileList];
  NSArray *reversed380 = [[list380 reverseObjectEnumerator] allObjects];
  (void)[list380 removeAllObjects]; (void)[list380 addObjectsFromArray:reversed380];
  NSMutableArray *pixes380 = (NSMutableArray*)[vc380 pixList];
  NSArray *rpix380 = [[pixes380 reverseObjectEnumerator] allObjects];
  (void)[pixes380 removeAllObjects]; (void)[pixes380 addObjectsFromArray:rpix380];
  p380[@"reversed"] = @YES; }
'''
expression = (expression.replace('PATHVAR', 'path380x')
              .replace('SERIES', s(manifest['seriesInstanceUID']))
              .replace('FRAME', str(args.frame))
              .replace('REVERSE', reverse if args.reverse else ''))
expression += '(void)[[NSJSONSerialization dataWithJSONObject:p380 options:3 error:nil] writeToFile:' + s(staged) + ' atomically:YES];\n'
commands = out_dir / (args.label + '.lldb')
commands.write_text('expression -l objc++ -- @import AppKit\n'
                    'expression -l objc++ -- { ' + ' '.join(expression.splitlines()) + ' }\nprocess detach\n')
result = subprocess.run(['xcrun', 'lldb', '--batch', '-p', str(args.pid), '-s', str(commands)], capture_output=True, text=True)
(out_dir / (args.label + '.log')).write_text(result.stdout + result.stderr)
if result.returncode or not staged.exists():
    raise SystemExit('lldb step failed; inspect ' + str(out_dir / (args.label + '.log')))
staged.replace(report)
data = json.loads(report.read_text())
data['frameMeanValue'] = manifest['frameMeanValue']
report.write_text(json.dumps(data, indent=1) + '\n')
print(json.dumps({k: v for k, v in data.items() if k != 'frameMeanValue'}, sort_keys=True))
