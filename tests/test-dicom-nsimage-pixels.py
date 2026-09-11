#!/usr/bin/env python3
"""Exercise the actual DICOMExport NSImage conversion with real AppKit bitmaps."""
from pathlib import Path
import subprocess, sys, tempfile
root=Path(__file__).resolve().parents[1]
s=(subprocess.check_output(['git','show',sys.argv[1]+':Horos/Sources/DICOMExport.mm']) if len(sys.argv)>1 else (root/'Horos/Sources/DICOMExport.mm').read_bytes()).decode('latin1')
a=s.index('- (long) setPixelData:');b=s.index('- (void) setDefaultWWWL:',a)
methods=s[a:b]
program=r'''
#import <Cocoa/Cocoa.h>
static int expectedRGB[3]={40,100,200};
@interface DICOMExport:NSObject {
 unsigned char *data,*localData,*imageData;long width,height,spp,bps;BOOL isSigned,freeImageData;int offset;
 NSImage *image;NSBitmapImageRep *imageRepresentation;
}
- (long)setPixelNSImage:(NSImage*)input;
- (BOOL)checkWidth:(long)w height:(long)h;
@end
@implementation DICOMExport
METHODS
- (BOOL)checkWidth:(long)w height:(long)h {
 if(width!=w || height!=h || spp!=3 || bps!=8 || !data) {fprintf(stderr,"got %ld x %ld, spp %ld bps %ld expected %ld x %ld\n",width,height,spp,bps,w,h);return NO;}
 for(long y=0;y<h;y++)for(long x=0;x<w;x++) {
 unsigned char *p=data+(y*w+x)*3;
 if(abs(p[0]-expectedRGB[0])>1 || abs(p[1]-expectedRGB[1])>1 || abs(p[2]-expectedRGB[2])>1) {fprintf(stderr,"pixel %ld %ld: %d %d %d\n",x,y,p[0],p[1],p[2]);return NO;}
 } return YES;
}
- (void)dealloc {if(localData)free(localData);if(freeImageData)free(imageData);[image release];[imageRepresentation release];[super dealloc];}
@end
NSImage *fixture(int w,int h) {
 NSBitmapImageRep *rep=[[[NSBitmapImageRep alloc] initWithBitmapDataPlanes:NULL pixelsWide:w pixelsHigh:h bitsPerSample:8 samplesPerPixel:3 hasAlpha:NO isPlanar:NO colorSpaceName:NSDeviceRGBColorSpace bytesPerRow:w*3+16 bitsPerPixel:24] autorelease];
 memset(rep.bitmapData,0xEE,rep.bytesPerRow*h);
 for(int y=0;y<h;y++)for(int x=0;x<w;x++) {unsigned char *p=rep.bitmapData+y*rep.bytesPerRow+x*3;p[0]=40;p[1]=100;p[2]=200;}
 NSImage *im=[[[NSImage alloc] initWithSize:NSMakeSize(w/2.,h/2.)] autorelease];
 [im addRepresentation:rep];[im setSize:NSMakeSize(w/2.,h/2.)];return im;
}
int main() {@autoreleasepool {
 DICOMExport *e=[[[DICOMExport alloc] init] autorelease];
 for(int i=0;i<3;i++) {
 int w=i==1?7:19,h=i==1?5:13;NSImage *im=fixture(w,h);
 NSBitmapImageRep *r=[NSBitmapImageRep imageRepWithData:[im TIFFRepresentation]];fprintf(stderr,"TIFF rep %ldx%ld bits %ld spp %ld planar %d pixelbits %ld stride %ld\n",r.pixelsWide,r.pixelsHigh,r.bitsPerSample,r.samplesPerPixel,r.isPlanar,r.bitsPerPixel,r.bytesPerRow);
 for(int repeat=0;repeat<2;repeat++) {
 if([e setPixelNSImage:im]!=0 || ![e checkWidth:w height:h]) {fprintf(stderr,"FAIL bitmap %d repeat %d\n",i,repeat);return 1;}
 }
 }

 NSBitmapImageRep *alpha=[[[NSBitmapImageRep alloc] initWithBitmapDataPlanes:NULL pixelsWide:2 pixelsHigh:2 bitsPerSample:8 samplesPerPixel:4 hasAlpha:YES isPlanar:NO colorSpaceName:NSDeviceRGBColorSpace bitmapFormat:NSBitmapFormatAlphaNonpremultiplied bytesPerRow:8 bitsPerPixel:32] autorelease];
 for(int i=0;i<4;i++) {unsigned char *p=alpha.bitmapData+i*4;p[0]=80;p[1]=160;p[2]=240;p[3]=128;}
 NSImage *alphaImage=[[[NSImage alloc] initWithSize:NSMakeSize(2,2)] autorelease];[alphaImage addRepresentation:alpha];
 expectedRGB[0]=40;expectedRGB[1]=80;expectedRGB[2]=120;
 if([e setPixelNSImage:alphaImage]!=0 || ![e checkWidth:2 height:2])return 3;

 NSBitmapImageRep *cmyk=[[[NSBitmapImageRep alloc] initWithBitmapDataPlanes:NULL pixelsWide:2 pixelsHigh:2 bitsPerSample:8 samplesPerPixel:4 hasAlpha:NO isPlanar:NO colorSpaceName:NSDeviceCMYKColorSpace bytesPerRow:8 bitsPerPixel:32] autorelease];
 for(int i=0;i<4;i++) {unsigned char *p=cmyk.bitmapData+i*4;p[0]=0;p[1]=255;p[2]=255;p[3]=0;}
 NSImage *cmykImage=[[[NSImage alloc] initWithSize:NSMakeSize(2,2)] autorelease];[cmykImage addRepresentation:cmyk];
 NSBitmapImageRep *decoded=[NSBitmapImageRep imageRepWithData:[cmykImage TIFFRepresentation]];
 NSBitmapImageRep *rgb=[decoded bitmapImageRepByConvertingToColorSpace:[NSColorSpace sRGBColorSpace] renderingIntent:NSColorRenderingIntentDefault];
 if(!rgb)return 4;
 NSUInteger reference[5]={0};[rgb getPixel:reference atX:0 y:0];
 for(int c=0;c<3;c++)expectedRGB[c]=reference[c];
 if([e setPixelNSImage:cmykImage]!=0 || ![e checkWidth:2 height:2])return 5;

 NSBitmapImageRep *wide=[[[NSBitmapImageRep alloc] initWithBitmapDataPlanes:NULL pixelsWide:2 pixelsHigh:2 bitsPerSample:8 samplesPerPixel:3 hasAlpha:NO isPlanar:NO colorSpaceName:NSDeviceRGBColorSpace bytesPerRow:6 bitsPerPixel:24] autorelease];
 for(int i=0;i<4;i++) {unsigned char *p=wide.bitmapData+i*3;p[0]=80;p[1]=160;p[2]=100;}
 wide=[wide bitmapImageRepByRetaggingWithColorSpace:[NSColorSpace displayP3ColorSpace]];
 NSImage *wideImage=[[[NSImage alloc] initWithSize:NSMakeSize(2,2)] autorelease];[wideImage addRepresentation:wide];
 decoded=[NSBitmapImageRep imageRepWithData:[wideImage TIFFRepresentation]];
 rgb=[decoded bitmapImageRepByConvertingToColorSpace:[NSColorSpace sRGBColorSpace] renderingIntent:NSColorRenderingIntentDefault];
 if(!rgb)return 6;
 [rgb getPixel:reference atX:0 y:0];for(int c=0;c<3;c++)expectedRGB[c]=reference[c];
 if([e setPixelNSImage:wideImage]!=0 || ![e checkWidth:2 height:2])return 7;
 if([e setPixelNSImage:nil]!=-1)return 2;
 puts("PASS: pixel dimensions, RGB channels, padded rows, changed size, repeated NSImage alpha compositing CMYK conversion and Display P3 normalization");
}}
'''.replace('METHODS',methods)
with tempfile.TemporaryDirectory(prefix='horos-nsimage-pixels-') as folder:
 p=Path(folder);(p/'test.m').write_text(program)
 subprocess.run(['xcrun','clang','-fsanitize=address',str(p/'test.m'),'-framework','Cocoa','-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
