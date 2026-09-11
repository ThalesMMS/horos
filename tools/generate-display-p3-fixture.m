// Generate a synthetic 64x64 Display P3 TIFF and print the AppKit sRGB reference.
// Compile: xcrun clang tools/generate-display-p3-fixture.m -framework Cocoa -o /tmp/make-p3
#import <AppKit/AppKit.h>
int main(int argc,char **argv){@autoreleasepool{
if(argc!=2){fprintf(stderr,"usage: make-p3 NEW_OUTPUT.tiff\n");return 2;}
NSString *output=[NSString stringWithUTF8String:argv[1]];
if([[NSFileManager defaultManager] fileExistsAtPath:output])return 3;
NSBitmapImageRep *r=[[[NSBitmapImageRep alloc] initWithBitmapDataPlanes:NULL pixelsWide:64 pixelsHigh:64 bitsPerSample:8 samplesPerPixel:3 hasAlpha:NO isPlanar:NO colorSpaceName:NSDeviceRGBColorSpace bytesPerRow:192 bitsPerPixel:24] autorelease];
for(int i=0;i<4096;i++){unsigned char *p=r.bitmapData+i*3;p[0]=80;p[1]=160;p[2]=100;}
r=[r bitmapImageRepByRetaggingWithColorSpace:[NSColorSpace displayP3ColorSpace]];
if(![[r TIFFRepresentation] writeToFile:[NSString stringWithUTF8String:argv[1]] atomically:YES])return 1;
NSBitmapImageRep *rgb=[r bitmapImageRepByConvertingToColorSpace:[NSColorSpace sRGBColorSpace] renderingIntent:NSColorRenderingIntentDefault];NSUInteger p[5]={0};[rgb getPixel:p atX:0 y:0];printf("sRGB reference %lu %lu %lu\n",p[0],p[1],p[2]);
}}
