#!/usr/bin/env python3
"""Retrieve a study with the application's own DICOMweb client, then print it (#384).

The common requirements of #384 ask that the printing improvements be tested
against "estudos recuperados pelo cliente DICOMweb local". This drives
`HorosDICOMwebClient` — the very class the Locations DICOMweb node uses — against
`tools/serve-dicomweb-fixture.py` on loopback, imports what comes back into the
private database, and then prepares print pages from a viewer of that study
through the same production methods the legacy print path uses.

No authentication is configured, so nothing touches the Keychain, and nothing
modal is called from the debugger.

    python3 tools/exercise-native-dicomweb-print.py --pid N retrieve|print --study UID
"""
import argparse
import json
from pathlib import Path
import re
import subprocess
import time
import uuid

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--pid', type=int, required=True)
parser.add_argument('step', choices=['retrieve', 'print'])
parser.add_argument('--endpoint', default='http://127.0.0.1:18044')
parser.add_argument('--study', default='', help='Study Instance UID served by the fixture')
parser.add_argument('--series-name', default='DICOMweb retrieved')
parser.add_argument('--label', default=None)
parser.add_argument('--output', type=Path, default=Path('local-validation/issue-384-native'))
args = parser.parse_args()
args.label = args.label or ('dicomweb-' + args.step)
if args.pid <= 0 or not re.fullmatch('[a-z0-9-]+', args.label):
    parser.error('positive PID and a lowercase label')
if args.step == 'retrieve' and not re.fullmatch(r'[0-9.]+', args.study or ''):
    parser.error('--study must be the Study Instance UID the fixture printed')
args.output.mkdir(parents=True, exist_ok=True)
out_dir = args.output.resolve()
report = out_dir / (args.label + '.json')
staged = report.with_name(report.name + '.' + uuid.uuid4().hex + '.partial')

steps = {
    'retrieve': r'''
NSString *staged384 = STAGED;
dispatch_async(dispatch_get_global_queue(0, 0), ^{
  NSMutableDictionary *w384 = [NSMutableDictionary dictionary];
  NSError *err384 = nil;
  id client384 = (id)[(id)[(Class)objc_getClass("HorosDICOMwebClient") alloc] initWithEndpoint: ENDPOINT credentialIdentifier: @"" timeout: 30 error: &err384];
  w384[@"client"] = @(client384 != nil);
  w384[@"clientError"] = (NSString*)[err384 localizedDescription] ?: @"";
  w384[@"onMainThread"] = @((BOOL)[NSThread isMainThread]);
  if (client384) {
    NSArray *studies384 = (NSArray*)[(id)client384 queryPath: @"studies" parameters: (NSDictionary*)@{} error: &err384];
    w384[@"studies"] = @((long)[studies384 count]);
    w384[@"queryError"] = (NSString*)[err384 localizedDescription] ?: @"";
    NSArray *series384 = (NSArray*)[(id)client384 queryPath: [NSString stringWithFormat: @"studies/%@/series", STUDY] parameters: (NSDictionary*)@{} error: &err384];
    w384[@"series"] = @((long)[series384 count]);
    NSString *seriesUID384 = (NSString*)[(NSArray*)[(NSDictionary*)[(NSDictionary*)[series384 firstObject] objectForKey: @"0020000E"] objectForKey: @"Value"] firstObject] ?: @"";
    w384[@"seriesInstanceUID"] = seriesUID384;
    NSArray *inst384 = (NSArray*)[(id)client384 queryPath: [NSString stringWithFormat: @"studies/%@/series/%@/instances", STUDY, seriesUID384] parameters: (NSDictionary*)@{} error: &err384];
    w384[@"instancesListed"] = @((long)[inst384 count]);
    NSString *incoming384 = (NSString*)[(id)[(Class)objc_getClass("DicomDatabase") activeLocalDatabase] incomingDirPath];
    w384[@"incoming"] = incoming384 ?: @"";
    NSString *stagingDir384 = [incoming384 stringByAppendingPathComponent: [@".DICOMweb-" stringByAppendingString: [[NSUUID UUID] UUIDString]]];
    NSArray *files384 = (NSArray*)[(id)client384 retrievePath: [NSString stringWithFormat: @"studies/%@", STUDY] stagingDirectory: stagingDir384 error: &err384];
    w384[@"retrieved"] = @((long)[files384 count]);
    w384[@"retrieveError"] = (NSString*)[err384 localizedDescription] ?: @"";
    long queued384 = 0;
    for (NSString *file384 in files384) {
      NSString *destination384 = [incoming384 stringByAppendingPathComponent: [[[NSUUID UUID] UUIDString] stringByAppendingPathExtension: @"dcm"]];
      if ([[NSFileManager defaultManager] moveItemAtPath: file384 toPath: destination384 error: nil]) queued384++;
    }
    w384[@"queuedForImport"] = @(queued384);
    (void)[[NSFileManager defaultManager] removeItemAtPath: stagingDir384 error: nil];
    w384[@"stagingRemoved"] = @(![[NSFileManager defaultManager] fileExistsAtPath: stagingDir384]);
  }
  (void)[[NSJSONSerialization dataWithJSONObject:w384 options:3 error:nil] writeToFile: staged384 atomically:YES];
});
''',
    'print': r'''
NSMutableDictionary *w384 = [NSMutableDictionary dictionary];
id v384 = nil;
for (id c384 in (NSArray*)[(Class)objc_getClass("ViewerController") get2DViewers])
  if ([(NSString*)[(NSObject*)[c384 currentSeries] valueForKey:@"name"] isEqualToString: SERIES]) { v384 = c384; break; }
w384[@"viewer"] = @(v384 != nil);
if (v384) {
  w384[@"series"] = (NSString*)[(NSObject*)[v384 currentSeries] valueForKey:@"name"] ?: @"";
  w384[@"patientID"] = (NSString*)[(NSObject*)[v384 currentStudy] valueForKey:@"patientID"] ?: @"";
  w384[@"images"] = @((long)[(NSArray*)[v384 fileList] count]);
  w384[@"prepared"] = @((BOOL)[v384 preparePrintSpoolDirectory]);
  NSString *dir384 = (NSString*)[(NSObject*)v384 valueForKey: @"printSpoolDirectory"];
  w384[@"ownedByPolicy"] = @((BOOL)[(Class)objc_getClass("HorosPrintSelection") isSpoolDirectory: dir384]);
  NSDictionary *attrs384 = (NSDictionary*)[[NSFileManager defaultManager] attributesOfItemAtPath: dir384 error: nil];
  w384[@"permissions"] = [NSString stringWithFormat: @"%o", (unsigned)[(NSNumber*)attrs384[NSFilePosixPermissions] unsignedShortValue]];
  NSMutableArray *files384 = [NSMutableArray array];
  long pages384 = (long)[(NSArray*)[v384 fileList] count]; if (pages384 > 4) pages384 = 4;
  NSMutableArray *means384 = [NSMutableArray array];
  for (long i384 = 0; i384 < pages384; i384++) {
    (void)[v384 setImageIndex: (int)i384];
    (void)[(NSView*)[v384 imageView] display];
    NSImage *cap384 = (NSImage*)[(id)[v384 imageView] nsimage: NO];
    (void)[v384 writePrintPage: cap384 index: (int)i384 into: files384];
    CGImageRef cg384 = (CGImageRef)[(Class)objc_getClass("HorosRegisteredGIF") sRGBImageForImage: cap384];
    NSBitmapImageRep *rep384 = [[NSBitmapImageRep alloc] initWithCGImage: cg384];
    double sum384 = 0; long n384 = 0;
    for (long y384 = 0; y384 < (long)[rep384 pixelsHigh]; y384 += 4)
      for (long x384 = 0; x384 < (long)[rep384 pixelsWide]; x384 += 4) {
        NSUInteger px384[4] = {0,0,0,0};
        (void)[rep384 getPixel: px384 atX: x384 y: y384]; sum384 += (double)px384[0]; n384++; }
    (void)[means384 addObject: @(n384 ? sum384 / (double)n384 : -1)];
  }
  w384[@"pages"] = @((long)[files384 count]);
  w384[@"pageMeans"] = means384;
  NSMutableArray *names384 = [NSMutableArray array];
  for (NSString *p384 in files384) (void)[names384 addObject: [p384 lastPathComponent]];
  w384[@"pageNames"] = names384;
  long present384 = 0;
  for (NSString *p384 in files384) if ([[NSFileManager defaultManager] fileExistsAtPath: p384]) present384++;
  w384[@"pagesOnDisk"] = @(present384);
  (void)[v384 discardPrintSpoolDirectory];
  long after384 = 0;
  for (NSString *p384 in files384) if ([[NSFileManager defaultManager] fileExistsAtPath: p384]) after384++;
  w384[@"pagesAfterJob"] = @(after384);
  w384[@"directoryAfterJob"] = @((BOOL)[[NSFileManager defaultManager] fileExistsAtPath: dir384]);
}
''',
}

expression = (steps[args.step]
              .replace('ENDPOINT', '@' + json.dumps(args.endpoint))
              .replace('STUDY', '@' + json.dumps(args.study))
              .replace('SERIES', '@' + json.dumps(args.series_name)))
expression = expression.replace('STAGED', '@' + json.dumps(str(staged)))
if args.step != 'retrieve':
    expression += '(void)[[NSJSONSerialization dataWithJSONObject:w384 options:3 error:nil] writeToFile:@' + json.dumps(str(staged)) + ' atomically:YES];\n'
commands = out_dir / (args.label + '.lldb')
commands.write_text('expression -l objc++ -- @import AppKit\n'
                    'expression -l objc++ -- { ' + ' '.join(expression.splitlines()) + ' }\nprocess detach\n')
result = subprocess.run(['xcrun', 'lldb', '--batch', '-p', str(args.pid), '-s', str(commands)], capture_output=True, text=True)
(out_dir / (args.label + '.log')).write_text(result.stdout + result.stderr)
if args.step == 'retrieve':
    # The client refuses to run on the main thread, so the work is dispatched and
    # the process let go; the block writes the record when it is done.
    for _ in range(120):
        if staged.exists():
            break
        time.sleep(1)
if result.returncode or not staged.exists():
    raise SystemExit('lldb step failed or the retrieval never finished; inspect '
                     + str(out_dir / (args.label + '.log')))
staged.replace(report)
print(json.dumps(json.loads(report.read_text()), indent=1)[:1800])
