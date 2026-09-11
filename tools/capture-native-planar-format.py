#!/usr/bin/env python3
"""Read loaded synthetic buffers and presentation after real UI/XML-RPC actions.

LLDB never changes viewer state; it saves/restores the GL readback state. The
manifest, captures and debugger logs must remain local. The optional scroll
catalog guard permits complete synthetic volumes after timing has finished;
LLDB readback must never run inside a measured performance interval.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess
import uuid

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('label')
p.add_argument('--pid', type=int, required=True)
p.add_argument('--series', required=True)
p.add_argument('--manifest', type=Path, required=True)
p.add_argument('--output', type=Path, required=True)
p.add_argument('--scroll-catalog', action='store_true', help='allow up to 1300 synthetic LOCAL-SCROLL frames')
a = p.parse_args()
manifest = json.loads(a.manifest.read_text())
allowed = {'PAL-97', 'LOCAL-TOMO', 'MPR-4D-226', 'S373-FORMATS'}
if a.scroll_catalog:
    allowed = {'LOCAL-SCROLL-CT', 'LOCAL-SCROLL-MR'}
if (a.pid <= 0 or not re.fullmatch('[a-z0-9-]+', a.label)
        or a.series not in {f['series'] for f in manifest['files']}
        or any(f['patient'] not in allowed for f in manifest['files'])):
    p.error('invalid label, PID or synthetic fixture manifest')
a.output.mkdir(parents=True, exist_ok=True)
prefix = (a.output/a.label).resolve()
if any(a.output.glob(a.label+'.*')):
    p.error('capture prefix exists; preserve it and choose a new label')
partial = prefix.with_suffix('.'+uuid.uuid4().hex+'.partial')
expression = r'''
id s373Owner=nil; int s373Matches=0;
for (id s373Candidate in (NSArray*)(id)[(id)objc_getClass("ViewerController") get2DViewers]) {
 if ([(NSString*)(id)[(NSObject*)s373Candidate valueForKeyPath:@"currentSeries.seriesDICOMUID"] isEqualToString:SERIES]) { s373Owner=s373Candidate; s373Matches++; }
}
BOOL s373Valid=s373Matches==1 && [NSThread isMainThread] && [[NSBundle mainBundle].bundleIdentifier isEqual:@"org.horosproject.horos.planar-performance"];
NSArray *s373AllowedPatients=PATIENTS, *s373AllowedSOPs=SOPS;
if (s373Valid && ![s373AllowedPatients containsObject:[(NSObject*)s373Owner valueForKeyPath:@"currentStudy.patientID"]]) s373Valid=NO;
NSMutableArray *s373Frames=[NSMutableArray array];
id s373View=s373Valid ? (id)[s373Owner imageView] : nil;
NSInteger s373Movies=s373Valid ? (NSInteger)[s373Owner maxMovieIndex] : 0;
if(s373Movies<1 || s373Movies>16) s373Valid=NO;
for(NSInteger s373Movie=0;s373Valid && s373Movie<s373Movies;s373Movie++) {
 NSArray *s373Pixes=(id)[s373Owner pixList:(int)s373Movie];
 if(s373Pixes.count>SLICE_LIMIT || s373Frames.count+s373Pixes.count>FRAME_LIMIT) { s373Valid=NO; break; }
 for(NSUInteger s373Index=0;s373Index<s373Pixes.count;s373Index++) {
  id s373Pix=s373Pixes[s373Index];
  NSString *s373Sop=[(NSObject*)s373Pix valueForKeyPath:@"imageObj.sopInstanceUID"];
  NSInteger s373W=(NSInteger)[s373Pix pwidth],s373H=(NSInteger)[s373Pix pheight];
  if(![s373AllowedSOPs containsObject:s373Sop] || !(BOOL)[s373Pix isLoaded] || s373W<1 || s373H<1 || s373W>1024 || s373H>1024) { s373Valid=NO; break; }
  NSString *s373File=[NSString stringWithFormat:@"%@-t%ld-i%lu.bin",PREFIX,(long)s373Movie,(unsigned long)s373Index];
  if(![[NSData dataWithBytes:(void*)[s373Pix fImage] length:s373W*s373H*4] writeToFile:s373File atomically:YES]) { s373Valid=NO; break; }
  float s373Orientation[9]={0}; (void)[s373Pix orientation:s373Orientation];
  NSMutableArray *s373O=[NSMutableArray array];for(int s373J=0;s373J<6;s373J++)[s373O addObject:@(s373Orientation[s373J])];
  NSMutableArray *s373Rois=[NSMutableArray array];
  NSArray *s373AllROIs=(id)[s373Owner roiList:(int)s373Movie];
  for(NSObject *s373Roi in (NSArray*)s373AllROIs[s373Index]) {
   NSMutableDictionary *s373R=[NSMutableDictionary dictionary];
   for(NSString *s373Key in @[@"name",@"type",@"mean",@"min",@"max"]) s373R[s373Key]=[s373Roi valueForKey:s373Key] ?: @"";
   [s373Rois addObject:s373R];
  }
  [s373Frames addObject:@{@"movie":@(s373Movie),@"index":@(s373Index),@"sop":s373Sop,@"frame":@((NSInteger)[s373Pix frameNo]),
   @"file":s373File.lastPathComponent,@"width":@(s373W),@"height":@(s373H),@"isRGB":@((BOOL)[s373Pix isRGB]),@"displayInverted":@((BOOL)[s373Pix displayInverted]),
   @"spacing":@[@((double)[s373Pix pixelSpacingX]),@((double)[s373Pix pixelSpacingY])],
   @"position":@[@((double)[s373Pix originX]),@((double)[s373Pix originY]),@((double)[s373Pix originZ])],
   @"orientation":s373O,@"rois":s373Rois,
   @"storedImageLevel":[(NSObject*)s373Pix valueForKeyPath:@"imageObj.windowLevel"] ?: [NSNull null],
   @"storedImageWidth":[(NSObject*)s373Pix valueForKeyPath:@"imageObj.windowWidth"] ?: [NSNull null]}];
 }
}
if(s373Valid) {
 NSRect s373Bounds=[(NSView*)s373View bounds], s373Backing=[(NSView*)s373View convertRectToBacking:s373Bounds];
 NSMutableArray *s373Map=[NSMutableArray array];
 for(int s373Corner=0;s373Corner<3;s373Corner++) {
  NSPoint s373Point={s373Corner==1 ? NSMaxX(s373Bounds) : NSMinX(s373Bounds),s373Corner==2 ? NSMinY(s373Bounds) : NSMaxY(s373Bounds)};
  NSPoint s373Mapped=(NSPoint)[s373View ConvertFromNSView2GL:s373Point];[s373Map addObject:@(s373Mapped.x)];[s373Map addObject:@(s373Mapped.y)];
 }
 unsigned char *s373R,*s373G,*s373B,s373Rgba[1024];(void)[s373View getCLUT:&s373R :&s373G :&s373B];
 for(int s373J=0;s373J<256;s373J++){s373Rgba[4*s373J]=s373R[s373J];s373Rgba[4*s373J+1]=s373G[s373J];s373Rgba[4*s373J+2]=s373B[s373J];s373Rgba[4*s373J+3]=255;}
 [[NSData dataWithBytes:s373Rgba length:1024]writeToFile:[PREFIX stringByAppendingString:@".clut"] atomically:YES];
 NSOpenGLContext *s373Previous=[NSOpenGLContext currentContext],*s373Context=(id)[s373View openGLContext];[s373Context makeCurrentContext];
 glPushClientAttrib(GL_CLIENT_PIXEL_STORE_BIT);glPushAttrib(GL_PIXEL_MODE_BIT);
 GLint s373ReadBuffer;glGetIntegerv(GL_READ_BUFFER,&s373ReadBuffer);glReadBuffer(GL_FRONT);
 glPixelStorei(GL_PACK_ALIGNMENT,1);glPixelStorei(GL_PACK_ROW_LENGTH,0);glPixelStorei(GL_PACK_SKIP_PIXELS,0);glPixelStorei(GL_PACK_SKIP_ROWS,0);
 GLenum s373Scales[4]={GL_RED_SCALE,GL_GREEN_SCALE,GL_BLUE_SCALE,GL_ALPHA_SCALE},s373Biases[4]={GL_RED_BIAS,GL_GREEN_BIAS,GL_BLUE_BIAS,GL_ALPHA_BIAS};
 for(int s373J=0;s373J<4;s373J++){glPixelTransferf(s373Scales[s373J],1);glPixelTransferf(s373Biases[s373J],0);}
 NSMutableData *s373Pixels=[NSMutableData dataWithLength:(NSUInteger)s373Backing.size.width*(NSUInteger)s373Backing.size.height*4];
 glReadPixels(0,0,(int)s373Backing.size.width,(int)s373Backing.size.height,GL_BGRA,GL_UNSIGNED_BYTE,s373Pixels.mutableBytes);
 GLenum s373GlError=glGetError();glReadBuffer(s373ReadBuffer);glPopAttrib();glPopClientAttrib();
 if(s373Previous)[s373Previous makeCurrentContext];else[NSOpenGLContext clearCurrentContext];
 [s373Pixels writeToFile:[PREFIX stringByAppendingString:@".bgra"] atomically:YES];
 NSDictionary *s373State=@{@"series":SERIES,@"viewer":[NSString stringWithFormat:@"%p",s373Owner],@"frames":s373Frames,@"movies":@(s373Movies),
  @"currentMovie":@((NSInteger)[s373Owner curMovieIndex]),@"currentImage":@((NSInteger)[s373View curImage]),
  @"metalEnabled":@((BOOL)[s373Owner horosPlanarMetalEnabled]),@"fallback":(id)[s373View horosPlanarFallbackReason] ?: @"",
  @"applicationActive":@([(NSApplication*)NSApp isActive]),@"glError":@(s373GlError),
  @"storedSeriesLevel":[(NSObject*)s373Owner valueForKeyPath:@"currentSeries.windowLevel"] ?: [NSNull null],
  @"storedSeriesWidth":[(NSObject*)s373Owner valueForKeyPath:@"currentSeries.windowWidth"] ?: [NSNull null],
  @"copySettingsInSeries":[(NSObject*)s373View valueForKey:@"COPYSETTINGSINSERIES"],
  @"level":[(NSObject*)s373View valueForKey:@"curWL"],@"widthWindow":[(NSObject*)s373View valueForKey:@"curWW"],
  @"screenToPixel":s373Map,@"viewSize":@[@(s373Backing.size.width),@(s373Backing.size.height)],
  @"softwareInterpolation":@((BOOL)[s373View softwareInterpolation]),
  @"nearest":@([[NSUserDefaults standardUserDefaults] boolForKey:@"NOINTERPOLATION"])};
 [[NSJSONSerialization dataWithJSONObject:s373State options:3 error:nil]writeToFile:OUTPUT atomically:YES];
}
'''
def objc_array(values):
    return '@['+','.join('@'+json.dumps(v) for v in sorted(set(values)))+']'
for token, value in {'SERIES':'@'+json.dumps(a.series), 'PREFIX':'@'+json.dumps(str(prefix)),
                     'OUTPUT':'@'+json.dumps(str(partial)), 'PATIENTS':objc_array(allowed),
                     'SOPS':objc_array(f['sop'] for f in manifest['files'] if not a.scroll_catalog or f['series']==a.series),
                     'SLICE_LIMIT':'1300' if a.scroll_catalog else '128',
                     'FRAME_LIMIT':'1300' if a.scroll_catalog else '256'}.items():
    expression = re.sub(r'\b'+token+r'\b', lambda _: value, expression)
commands = prefix.with_suffix('.lldb')
commands.write_text('expression -l objc++ -- @import AppKit\nexpression -l objc++ -- @import OpenGL.GL\n'
                    'expression -l objc++ -- @import ObjectiveC\nexpression -l objc++ -- { '
                    +' '.join(expression.splitlines())+' }\nprocess detach\n')
result = subprocess.run(['xcrun','lldb','--batch','-p',str(a.pid),'-s',str(commands)],capture_output=True,text=True)
prefix.with_suffix('.lldb.log').write_text(result.stdout+result.stderr)
if result.returncode or not partial.exists():
    raise SystemExit('Capture failed or synthetic guard refused it; inspect the local LLDB log')
state = json.loads(partial.read_text())
partial.replace(prefix.with_suffix('.json'))
print(a.label, len(state['frames']), 'frames;', state['movies'], 'times;',
      'Metal',state['metalEnabled'],'fallback',bool(state['fallback']))
