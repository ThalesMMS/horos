#!/usr/bin/env python3
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parent.parent
source=(root/'DICOMPrint/AYNSImageToDicom.m').read_bytes().decode('latin1')
start=source.index('- (struct rawData) _convertRGBToGrayscale:',source.index('@implementation'))
end=source.find('\n//********',start)
method=source[start:end]
program=r'''
#import <AppKit/AppKit.h>
struct rawData { long bytesWritten,height,width; };
@interface Converter:NSObject { NSMutableData *m_ImageDataBytes; }
- (struct rawData)_convertRGBToGrayscale:(NSImage*)image;
- (NSData*)data;
@end
@implementation Converter
- (NSData*)data { return m_ImageDataBytes; }
METHOD
@end
#define check(v) NSCAssert((v),@"failed: %s",#v)
int main(void) { @autoreleasepool {
 for(int channels=3;channels<=4;channels++) {
  NSBitmapImageRep *rep=[[NSBitmapImageRep alloc] initWithBitmapDataPlanes:NULL pixelsWide:64 pixelsHigh:32 bitsPerSample:8 samplesPerPixel:channels hasAlpha:channels==4 isPlanar:NO colorSpaceName:NSDeviceRGBColorSpace bytesPerRow:64*channels+16 bitsPerPixel:channels*8];
  for(int y=0;y<32;y++)for(int x=0;x<64;x++){NSUInteger pixel[]={40,100,180,255};[rep setPixel:pixel atX:x y:y];}
  NSImage *image=[[NSImage alloc] initWithSize:NSMakeSize(32,16)];[image addRepresentation:rep];
  Converter *converter=[Converter new];struct rawData raw=[converter _convertRGBToGrayscale:image];
  check(raw.width==64 && raw.height==32 && raw.bytesWritten==2048);
  const unsigned char *bytes=converter.data.bytes;
  for(int i=0;i<2048;i++) check(bytes[i]==91);
 }
 NSLog(@"PASS: RGB/RGBA, row padding, grayscale weights and pixel dimensions independent of logical image size");
} }
'''.replace('METHOD',method)
with tempfile.TemporaryDirectory(prefix='horos-print-gray-') as directory:
 p=Path(directory);(p/'test.m').write_text(program)
 subprocess.run(['xcrun','clang','-fsanitize=address','-framework','AppKit',str(p/'test.m'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
