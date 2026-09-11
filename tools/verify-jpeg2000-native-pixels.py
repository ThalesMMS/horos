#!/usr/bin/env python3
"""Check every loaded synthetic voxel after timing, through an isolated app's LLDB.

Only accepts the performance bundle and the generator's synthetic patient.
Attaching pauses the application; do not run during a performance measurement.
Requires a local debug entitlement, including for a Release build.
"""
import argparse
import json
from pathlib import Path
import subprocess

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--pid', type=int, required=True)
parser.add_argument('--manifest', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
manifest = json.loads(args.manifest.read_text())
if manifest['patient'] != 'SYNTHETIC-OPJ-PERF':
    parser.error('Use the synthetic performance fixture')
size, slices = manifest['size'], manifest['slices']
if not 64 <= size <= 1024 or not 1 <= slices <= 2048:
    parser.error('Unexpected synthetic dimensions')
if args.output.exists():
    parser.error('Preserve the existing result and choose another output')
expression = r'''
BOOL valid=[NSThread isMainThread] && [[NSBundle mainBundle].bundleIdentifier isEqual:@"org.horosproject.horos.openjpeg-performance"];
id viewer=nil; NSUInteger matches=0;
if(valid) for(id candidate in (NSArray*)(id)[(id)objc_getClass("ViewerController") get2DViewers]) {
 if([(NSString*)(id)[(NSObject*)candidate valueForKeyPath:@"currentSeries.seriesDICOMUID"] isEqualToString:SERIES]) {viewer=candidate; matches++;}
}
valid=valid && matches==1 && [(NSString*)(id)[(NSObject*)viewer valueForKeyPath:@"currentStudy.patientID"] isEqualToString:@"SYNTHETIC-OPJ-PERF"];
NSArray *pixels=valid ? (id)[viewer pixList:0] : nil;
valid=valid && pixels.count==SLICE_COUNT;
unsigned long long checked=0, mismatches=0;
NSMutableIndexSet *seen=[NSMutableIndexSet indexSet];
if(valid) for(id pix in pixels) {
 int w=(int)[pix pwidth], h=(int)[pix pheight];
 int index=(int)(double)[pix originZ];
 if(!(BOOL)[pix isLoaded] || (BOOL)[pix isRGB] || w!=IMAGE_SIZE || h!=IMAGE_SIZE || index<0 || index>=SLICE_COUNT || [seen containsIndex:index]) {valid=NO; break;}
 [seen addIndex:index];
 float *values=(float*)[pix fImage];
 if(!values) {valid=NO; break;}
 for(int y=0;y<h;y++) for(int x=0;x<w;x++) {
  float expected=(x*17+y*31+((x/32)^(y/32))*1024+index*113)&65535;
  if(values[y*w+x]!=expected) mismatches++;
  checked++;
 }
}
NSDictionary *result=@{@"valid":@(valid),@"slices":@(seen.count),@"voxels":@(checked),@"mismatches":@(mismatches)};
[[NSJSONSerialization dataWithJSONObject:result options:NSJSONWritingPrettyPrinted error:NULL] writeToFile:OUTPUT atomically:YES];
'''
expression = expression.replace('SERIES', '@'+json.dumps(manifest['series']))
expression = expression.replace('SLICE_COUNT', str(slices)).replace('IMAGE_SIZE', str(size))
expression = expression.replace('OUTPUT', '@'+json.dumps(str(args.output.resolve())))
commands = args.output.with_suffix('.lldb')
commands.write_text('expression -l objc++ -- @import AppKit\n'
    'expression -l objc++ -- @import ObjectiveC\n'
    'expression -l objc++ -- { '+' '.join(expression.splitlines())+' }\nprocess detach\n')
result = subprocess.run(['xcrun', 'lldb', '--batch', '-p', str(args.pid), '-s', str(commands)],
    capture_output=True, text=True, timeout=60)
args.output.with_suffix('.lldb.log').write_text(result.stdout+result.stderr)
if result.returncode or not args.output.is_file():
    raise SystemExit('Native pixel check failed; inspect the LLDB log')
actual = json.loads(args.output.read_text())
if actual != dict(valid=True, slices=slices, voxels=slices*size*size, mismatches=0):
    raise SystemExit(f'Native pixel mismatch: {actual}')
print(json.dumps(actual))
