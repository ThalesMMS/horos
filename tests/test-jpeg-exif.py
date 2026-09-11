#!/usr/bin/env python3
"""Exercise actual JPEGExif with real ImageIO, including destination preservation."""
from pathlib import Path
import subprocess,sys,tempfile
root=Path(__file__).resolve().parents[1]
source=(subprocess.check_output(['git','show',sys.argv[1]+':Horos/Sources/JPEGExif.m']) if len(sys.argv)>1 else (root/'Horos/Sources/JPEGExif.m').read_bytes()).decode('latin1')
program=r'''
#import <Cocoa/Cocoa.h>
#import <ImageIO/ImageIO.h>
#import "JPEGExif.h"
int main(int argc,char **argv){@autoreleasepool{
 NSString *folder=[NSString stringWithUTF8String:argv[1]];
 [[NSFileManager defaultManager] createDirectoryAtPath:folder withIntermediateDirectories:YES attributes:nil error:NULL];
 for(NSString *format in @[@"jpeg",@"tiff"]){
  NSURL *url=[NSURL fileURLWithPath:[folder stringByAppendingPathComponent:[@"image." stringByAppendingString:format]]];
  NSBitmapImageRep *bitmap=[[[NSBitmapImageRep alloc] initWithBitmapDataPlanes:NULL pixelsWide:16 pixelsHigh:16 bitsPerSample:8 samplesPerPixel:3 hasAlpha:NO isPlanar:NO colorSpaceName:NSDeviceRGBColorSpace bytesPerRow:0 bitsPerPixel:0] autorelease];
  memset(bitmap.bitmapData,100,bitmap.bytesPerRow*16);
  NSData *original=[bitmap representationUsingType:[format isEqual:@"jpeg"]?NSBitmapImageFileTypeJPEG:NSBitmapImageFileTypeTIFF properties:@{}];
  [original writeToURL:url atomically:YES];
  NSDictionary *exif=@{(NSString*)kCGImagePropertyExifUserComment:@"Synthetic test metadata",(NSString*)kCGImagePropertyExifDateTimeOriginal:@"2026:09:08 12:00:00"};
  [JPEGExif addExif:url properties:exif format:format];
  CGImageSourceRef image=CGImageSourceCreateWithURL((CFURLRef)url,NULL);
  if(!image)return 1;
  NSDictionary *properties=[(NSDictionary*)CGImageSourceCopyPropertiesAtIndex(image,0,NULL) autorelease];
  NSDictionary *stored=properties[(NSString*)kCGImagePropertyExifDictionary];
  if(![stored[(NSString*)kCGImagePropertyExifUserComment] isEqual:exif[(NSString*)kCGImagePropertyExifUserComment]] || ![stored[(NSString*)kCGImagePropertyExifDateTimeOriginal] isEqual:exif[(NSString*)kCGImagePropertyExifDateTimeOriginal]])return 2;
  CGImageRef decoded=CGImageSourceCreateImageAtIndex(image,0,NULL);
  if(!decoded || CGImageGetWidth(decoded)!=16 || CGImageGetHeight(decoded)!=16)return 3;
  CGImageRelease(decoded);CFRelease(image);
  NSData *before=[NSData dataWithContentsOfURL:url];
  [JPEGExif addExif:url properties:exif format:@"unsupported"];
  if(![[NSData dataWithContentsOfURL:url] isEqual:before])return 4;
  chmod([folder fileSystemRepresentation],0555);
  [JPEGExif addExif:url properties:@{(NSString*)kCGImagePropertyExifUserComment:@"Must not replace"} format:format];
  chmod([folder fileSystemRepresentation],0755);
  if(![[NSData dataWithContentsOfURL:url] isEqual:before])return 5;
 }
 NSArray *files=[[NSFileManager defaultManager] contentsOfDirectoryAtPath:folder error:NULL];
 if(files.count!=2)return 6;
 puts("PASS: JPEG/TIFF EXIF persisted, images readable, failed writes preserve files, no leftover temporaries");
}}
'''
with tempfile.TemporaryDirectory(prefix='horos-exif-') as folder:
 p=Path(folder);(p/'JPEGExif.m').write_text(source);(p/'test.m').write_text('#include <sys/stat.h>\n'+program)
 subprocess.run(['xcrun','clang','-include','ImageIO/ImageIO.h','-I',str(root/'Horos/Sources'),'-fsanitize=address',str(p/'JPEGExif.m'),str(p/'test.m'),'-framework','Cocoa','-framework','ImageIO','-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test'),str(p/'files')],check=True)
