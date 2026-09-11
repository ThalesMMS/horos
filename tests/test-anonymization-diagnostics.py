#!/usr/bin/env python3
"""Run the production anonymization method with the built GDCM and generated DICOM.
Requires pydicom/numpy and a successful Debug dependency build. App model, naming,
and progress UI are doubles; GDCM reads, tag replacement, writes and files are real.
"""
from pathlib import Path
import hashlib
import subprocess
import sys
import tempfile
# Re-run under an interpreter that has pydicom when this one does not, so the
# test measures the product rather than the machine it was started on.
try:
    import pydicom  # noqa: F401
except ModuleNotFoundError:
    import os
    import subprocess as _subprocess
    from pathlib import Path as _Path
    for _candidate in _Path('/private/tmp').glob('*/*/*/scratchpad/*venv*/bin/python'):
        if _subprocess.run([str(_candidate), '-c', 'import pydicom'],
                           capture_output=True).returncode == 0:
            os.execv(str(_candidate), [str(_candidate), __file__] + sys.argv[1:])
    raise SystemExit("this test needs pydicom. Create an interpreter with it:\n"
                     "  python3 -m venv /tmp/horos-dicom-venv\n"
                     "  /tmp/horos-dicom-venv/bin/python -m pip install 'pydicom>=3,<4' numpy")
import pydicom
root = Path(__file__).resolve().parents[1]
install = root/'build/Build/Intermediates.noindex/Horos.build/Debug/GDCM.build/Install'
if not (install/'wlib/libGDCM.a').exists():
    # Not built here: a skip, not a failure. SystemExit with a string exits 1,
    # which tools/run-tests.py reads as failed; the skip code is 2.
    print('skipped: needs a built GDCM; run script/build_and_run.sh --verify first',
          file=sys.stderr)
    raise SystemExit(2)
source = (root/'Horos/Sources/Anonymization.mm').read_bytes().decode('latin1')
methods = source[source.index('+(NSDictionary*)anonymizeFiles:'):source.rindex('@end')]
# The category delegates to the one table, which lives in the framework, so the
# harness carries that table and a stand-in class to hang it on.
encoding_source = (root/'DCM Framework/DCMCharacterSet.m').read_bytes().decode('latin1')


def _method(text, signature):
    at = text.index(signature)
    opening = text.index('{', at)
    depth, index = 0, opening
    while index < len(text):
        if text[index] == '{':
            depth += 1
        elif text[index] == '}':
            depth -= 1
            if depth == 0:
                return text[at:index + 1]
        index += 1
    raise SystemExit('cannot find %s' % signature)


encoding_method = ('\n'.join([
    # The template opens an @implementation around this; close it, define the
    # table, and open another for the category method the template's @end closes.
    '@end',
    '@interface DCMCharacterSet : NSObject',
    '+ (NSStringEncoding)encodingForDICOMCharacterSet:(NSString *)characterSet;',
    '+ (NSString*) characterSetWhenAbsent;',
    '@end',
    '@implementation DCMCharacterSet',
    _method(encoding_source, '+ (NSString*) characterSetWhenAbsent'),
    _method(encoding_source, '+ (NSStringEncoding)encodingForDICOMCharacterSet:'),
    '@end',
    '@implementation NSString (EncodingFixtureBody)',
    '+ (NSStringEncoding)encodingForDICOMCharacterSet:(NSString *)characterSet',
    '{ return [DCMCharacterSet encodingForDICOMCharacterSet: characterSet]; }',
]))
harness = r'''
#import <Cocoa/Cocoa.h>
#import <objc/runtime.h>
#import "Anonymization.h"
#import "HorosAnonymizationSafety.h"
#include <GDCM/gdcmReader.h>
#include <GDCM/gdcmDefs.h>
#include <GDCM/gdcmAnonymizer.h>
#include <GDCM/gdcmWriter.h>
#include <sys/stat.h>
static NSString *mode, *output;
static NSInteger polls, publications;
static void check(BOOL ok, NSString *why) { if(!ok) { NSLog(@"FAIL %@: %@",mode,why);exit(1); } }
@interface DCMAttributeTag : NSObject
@property unsigned short group, element;
@property(retain) NSString *vr;
@end
@implementation DCMAttributeTag
@end
@interface DCMCalendarDate : NSObject
+ (id)dicomDateWithDate:(id)d; + (id)dicomTimeWithDate:(id)d; + (id)dicomDateTimeWithDicomDate:(id)d dicomTime:(id)t;
@end
@implementation DCMCalendarDate
+ (id)dicomDateWithDate:(id)d { return @"20260908"; } + (id)dicomTimeWithDate:(id)d { return @"120000"; }
+ (id)dicomDateTimeWithDicomDate:(id)d dicomTime:(id)t { return @"20260908120000"; }
@end
@interface FixtureSeries : NSObject
@property(retain) NSObject *study;
@end
@implementation FixtureSeries
@end
@interface DicomImage : NSObject
@property(retain) FixtureSeries *series;
@property(retain) NSNumber *instanceNumber;
@end
@implementation DicomImage
@end
@interface DicomFile : NSObject
+ (NSArray *)getEncodingArrayForFile:(NSString *)p;
@end
@implementation DicomFile
+ (NSArray *)getEncodingArrayForFile:(NSString *)p {
 gdcm::Reader reader;reader.SetFileName(p.fileSystemRepresentation);
 if(!reader.Read()) return @[];
 const gdcm::DataSet &ds=reader.GetFile().GetDataSet();gdcm::Tag tag(8,5);
 if(!ds.FindDataElement(tag)) return @[@""];
 const gdcm::ByteValue *value=ds.GetDataElement(tag).GetByteValue();
 NSString *str=value?[[[NSString alloc] initWithBytes:value->GetPointer() length:value->GetLength() encoding:NSASCIIStringEncoding] autorelease]:@"";
 return @[str?:@""];
}
@end
@interface NSString (EncodingFixture)
+ (NSStringEncoding)encodingForDICOMCharacterSet:(NSString *)s;
@end
@implementation NSString (EncodingFixture)
ENCODING_METHOD
@end
@interface NSDictionary (FixtureLookup)
- (id)keyForObject:(id)obj;
@end
@implementation NSDictionary (FixtureLookup)
- (id)keyForObject:(id)obj { return [self allKeysForObject:obj].firstObject; }
@end
@interface NSFileManager (FixtureMove)
- (void)confirmDirectoryAtPath:(NSString *)p;
- (BOOL)fixtureMove:(NSString *)a toPath:(NSString *)b error:(NSError **)e;
@end
@implementation NSFileManager (FixtureMove)
- (void)confirmDirectoryAtPath:(NSString *)p { if(![self createDirectoryAtPath:p withIntermediateDirectories:YES attributes:nil error:NULL]) [NSException raise:@"FixtureDirectory" format:@"cannot create export folder"]; }
- (BOOL)fixtureMove:(NSString *)a toPath:(NSString *)b error:(NSError **)e {
 if([b containsString:@"/Anonymized-"] && ++publications==2 && [mode isEqual:@"publish-failure"]) {
  if(e)*e=[NSError errorWithDomain:NSPOSIXErrorDomain code:EACCES userInfo:nil];return NO;
 }
 return [self fixtureMove:a toPath:b error:e];
}
@end
@interface HorosExportFolderNaming : NSObject
+ (NSString *)anonymousPathForBatch:(NSUUID *)b studyIndex:(NSUInteger)s seriesIndex:(NSUInteger)i;
@end
@implementation HorosExportFolderNaming
+ (NSString *)anonymousPathForBatch:(NSUUID *)b studyIndex:(NSUInteger)s seriesIndex:(NSUInteger)i { return [NSString stringWithFormat:@"Anonymized-%@/Study-%lu/Series-%lu", b.UUIDString,(unsigned long)s,(unsigned long)i]; }
@end
@interface Wait : NSObject
- (id)initWithString:(NSString *)s; - (id)progress; - (void)setMaxValue:(double)n;
- (void)showWindow:(id)s; - (void)setCancel:(BOOL)b; - (void)incrementBy:(double)n;
- (BOOL)pollCancellation; - (void)close;
@end
@implementation Wait
- (id)initWithString:(NSString *)s { return [super init]; } - (id)progress { return self; }
- (void)setMaxValue:(double)n {} - (void)showWindow:(id)s {} - (void)setCancel:(BOOL)b {} - (void)incrementBy:(double)n {}
- (BOOL)pollCancellation {
 polls++;
 if([mode isEqual:@"write-failure"] && (polls==3||polls==4))
  for(NSString *name in [NSFileManager.defaultManager contentsOfDirectoryAtPath:output error:NULL])
   if([name hasPrefix:@".horos-anonymization-"]) chmod([[output stringByAppendingPathComponent:name] fileSystemRepresentation],polls==3?0500:0700);
 return ([mode isEqual:@"cancel-copy"]&&polls==2)||([mode isEqual:@"cancel-publish"]&&polls==6)||([mode isEqual:@"cancel-final"]&&polls==7);
}
- (void)close {}
@end
@implementation Anonymization
METHODS
@end
int main(int argc,char **argv) { @autoreleasepool {
 mode=[NSString stringWithUTF8String:argv[1]]; NSString *input=[NSString stringWithUTF8String:argv[2]];output=[NSString stringWithUTF8String:argv[3]];
 method_exchangeImplementations(class_getInstanceMethod(NSFileManager.class,@selector(moveItemAtPath:toPath:error:)),class_getInstanceMethod(NSFileManager.class,@selector(fixtureMove:toPath:error:)));
 NSInteger count=argc>4?atoi(argv[4]):2;
 NSMutableArray *files=[NSMutableArray array];
 for(NSInteger i=0;i<count;i++) [files addObject:[input stringByAppendingPathComponent:count==2?(i==0?@"one.dcm":@"two.dcm"):[NSString stringWithFormat:@"image-%05ld.dcm",(long)i]]];
 if([mode isEqual:@"duplicate-path"]) files[1]=files[0];
 FixtureSeries *series=[FixtureSeries new];series.study=[NSObject new];NSMutableArray *images=[NSMutableArray array];
 for(int i=0;i<count;i++){ DicomImage *im=[DicomImage new];im.series=series;im.instanceNumber=@(i+1);[images addObject:im]; }
 DCMAttributeTag *tag=[DCMAttributeTag new];tag.group=0x10;tag.element=0x10;tag.vr=@"PN";
 if([mode isEqual:@"unsupported-tag"]) {tag.group=0x28;tag.element=0x10;tag.vr=@"US";}
 NSString *value=[mode isEqual:@"encoding"]?@"QA^\u6f22":([mode isEqual:@"mixed-encoding"]?@"QA^\u00c9lodie":@"QA^Anonymous");
 NSArray *tags=[mode isEqual:@"no-tags"]?@[]:@[@[tag,value]];
 NSError *error=nil;
 NSDictionary *result=[Anonymization anonymizeFiles:files dicomImages:images toPath:output withTags:tags error:&error];
 BOOL success=[mode isEqual:@"success"]||[mode isEqual:@"mixed-encoding"]||[mode isEqual:@"duplicate-uid"]||[mode isEqual:@"large"]||[mode isEqual:@"large-mixed"];
 check((result!=nil)==success,@"result");check(success?!error:error!=nil,@"error contract");
 if(success) check(result.count==count,@"complete output mapping");
 else {
  NSArray *rows=error.userInfo[@"HorosAnonymizationFileResults"];
  check(rows.count==files.count,@"every requested input has a result");
  for(NSUInteger i=0;i<files.count;i++) check([rows[i][@"source"] isEqual:files[i]],@"result source and order");
  if([mode isEqual:@"invalid"]||[mode isEqual:@"missing"]||[mode isEqual:@"publish-failure"])
   check([rows[1][@"outcome"] isEqual:@"failed"]&&[rows[0][@"outcome"] isEqual:@"not-exported"],@"specific failed file distinguished from batch rollback");
  if([mode isEqual:@"large-invalid"])
   check([rows.lastObject[@"outcome"] isEqual:@"failed"]&&[[rows filteredArrayUsingPredicate:[NSPredicate predicateWithFormat:@"outcome == 'failed'"]] count]==1,@"only the final invalid input is marked failed in a large batch");
  if([mode hasPrefix:@"cancel-"]) check([error.domain isEqual:NSCocoaErrorDomain]&&error.code==NSUserCancelledError,@"cancellation distinguished");
  else check(error.localizedDescription.length>0,@"explicit failure");
  if([mode isEqual:@"unsupported-tag"])check([error.localizedDescription containsString:@"(0028,0010)"],@"failed tag identified");
  if([mode isEqual:@"encoding"])check([error.localizedDescription containsString:@"character set"],@"encoding failure identified");
  for(NSString *p in [NSFileManager.defaultManager subpathsAtPath:output])
   check(![p.pathExtension isEqual:@"dcm"],@"no partial export or staged DICOM left");
 }
 NSLog(@"PASS %@: %@",mode,error.localizedDescription?:[NSString stringWithFormat:@"%ld complete outputs",(long)count]);
} }
'''.replace('METHODS', methods).replace('ENCODING_METHOD', encoding_method)
with tempfile.TemporaryDirectory(prefix='horos-anonymization-gdcm-') as tmp:
    path=Path(tmp)
    (path/'test.mm').write_text(harness)
    subprocess.run(['xcrun','clang++','-std=c++17','-fblocks','-Wno-incomplete-implementation','-Wno-objc-method-access','-Wno-deprecated-declarations','-I'+str(root/'Horos/Sources'),'-I'+str(install/'include'),'-I'+str(install/'include/GDCM'),str(path/'test.mm'),str(install/'wlib/libGDCM.a'),'-lz','-framework','Cocoa','-o',str(path/'test')],check=True)
    subprocess.run([sys.executable,str(root/'tools/generate-anonymization-order-fixture.py'),str(path/'generated')],check=True)
    original=pydicom.dcmread(path/'generated/reverse-99.dcm')
    for mode in ['success','duplicate-uid','duplicate-path','invalid','missing','no-tags','unsupported-tag','encoding','mixed-encoding','write-failure','publish-failure','cancel-copy','cancel-publish','cancel-final'] + (['large'] if '--large' in sys.argv else []) + (['large-mixed','large-invalid'] if '--large-mixed' in sys.argv else []):
        case=path/mode;input_dir=case/'input';output=case/'output';input_dir.mkdir(parents=True);output.mkdir()
        count=29329 if mode.startswith('large') else 2
        expected={}
        for index,name in enumerate(['one.dcm','two.dcm'] if count==2 else [f'image-{i:05d}.dcm' for i in range(count)]):
            ds=original.copy();ds.InstanceNumber=index+1
            ds.SOPInstanceUID=ds.file_meta.MediaStorageSOPInstanceUID='1.2.826.0.1.3680043.10.543.5.1' if mode=='duplicate-uid' or (mode=='large-mixed' and index>=count-2) else pydicom.uid.generate_uid()
            ds.SpecificCharacterSet=('ISO_IR 100' if index==0 else 'ISO_IR 192') if mode=='mixed-encoding' else ''
            ds.PixelData=((index+1)%4096).to_bytes(2,'little')*(ds.Rows*ds.Columns)
            expected[(str(ds.SOPInstanceUID),int(ds.InstanceNumber))]=hashlib.sha256(ds.PixelData).hexdigest()
            ds.save_as(input_dir/name,enforce_file_format=True)
        if mode in ['invalid','large-invalid']: (input_dir/('two.dcm' if count==2 else f'image-{count-1:05d}.dcm')).write_bytes(b'synthetic invalid DICOM\n')
        if mode=='missing': (input_dir/'two.dcm').unlink()
        before={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in input_dir.iterdir()}
        subprocess.run((['/usr/bin/time','-l'] if mode.startswith('large') else [])+[str(path/'test'),mode,str(input_dir),str(output),str(count)],check=True)
        assert all(hashlib.sha256(p.read_bytes()).hexdigest()==h for p,h in before.items())
        if mode in ['success','mixed-encoding','duplicate-uid','large','large-mixed']:
            files=list(output.rglob('*.dcm'));assert len(files)==count
            actual={}
            for p in files:
                ds=pydicom.dcmread(p)
                assert str(ds.PatientName)==('QA^Élodie' if mode=='mixed-encoding' else 'QA^Anonymous')
                key=(str(ds.SOPInstanceUID),int(ds.InstanceNumber))
                assert key not in actual, 'Duplicate output instance key'
                actual[key]=hashlib.sha256(ds.PixelData).hexdigest()
            assert actual==expected, 'Input/output UID, instance and pixel manifests differ'
            print(f'PASS manifest {mode}: {len(files)} files, {len({k[0] for k in actual})} unique SOP UIDs',flush=True)
print('PASS all scenarios: original bytes preserved; successful tags and pixels verified independently')
